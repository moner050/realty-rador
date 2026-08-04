# Full Map Aggregation and Clustering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show every complex matching the active search as a cluster or individual map marker, independently of the 20-card listing page.

**Architecture:** A read-only JSON endpoint asks a map-query service for all exact matching complex aggregates and groups verified coordinates into zoom-dependent cells. The map JavaScript replaces only overlays when the viewport changes; a separate card-fragment endpoint updates the list after the existing safe zoom threshold so the live map is never remounted by a card refresh.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, HTMX, NAVER Maps JavaScript API, pytest, Node.js built-in test runner.

## Global Constraints

- Map aggregation and card pagination must use the same persistent search filters, but map data must never use a listing cursor or page-size limit.
- Every matching, verified complex is represented exactly once, either by an individual marker or by exactly one cluster membership.
- Coordinates with `geocode_status == GEOCODE_STATUS_OK` and non-null latitude/longitude are the only mappable coordinates.
- The map JSON endpoint is read-only and must not construct `NaverGeocoder`, commit a session, or change saved filters.
- Bounds remain transient `Decimal` filters and continue to affect the cursor fingerprint without being persisted.
- At zoom below 11, update clusters but preserve current cards. At zoom 11 or higher and a span at most 1.5 degrees, refresh cards for the visible bounds after 300ms idle.
- Preserve latest-request-wins behavior for both map data and card data. Do not add an index before recording a representative MySQL `EXPLAIN ANALYZE`.
- Use `python -m pytest`, not bare `pytest`, and preserve unrelated dirty worktree changes.

---

## File Structure

- `src/realty_radar/application/listing_map_service.py` — exact complex aggregation DTOs, clustering, and aggregate counters.
- `src/realty_radar/application/listing_search_service.py` — public read-only candidate statement and exact runtime-filter adapter shared with map aggregation.
- `src/realty_radar/web/routes/home.py` — map JSON and card-fragment routes plus URL builders.
- `src/realty_radar/web/templates/listings/_map_sidebar.html` — count targets and map-data URL, with no serialized page-only marker payload.
- `src/realty_radar/web/templates/listings/_listing_collection.html` — swappable cards and pager without the map root.
- `src/realty_radar/web/templates/listings/list_partial.html` — includes the extracted listing collection below a stable map root.
- `src/realty_radar/web/static/listing-map.js` — cluster overlays, individual overlays, independent map/card fetches, cleanup, and response guards.
- `tests/unit/test_listing_map_service.py` — aggregate, bounds, and cluster invariants.
- `tests/integration/test_listing_search_v2.py` — shared exact-filter contract.
- `tests/integration/test_listing_map_ui.py` — JSON/HTML/route behavior.
- `tests/web/test_listing_map_controller.mjs` — browser-controller behavior without a real Maps network call.

### Task 1: Define exact map aggregate and clustering contracts

**Files:**
- Modify: `src/realty_radar/application/listing_search_service.py`
- Modify: `src/realty_radar/application/listing_map_service.py`
- Modify: `tests/unit/test_listing_map_service.py`
- Modify: `tests/integration/test_listing_search_v2.py`

**Interfaces:**
- Consumes: `ListingSearchFilter`, applicant profile, and `ListingCurrent`/`ComplexCurrent` rows.
- Produces: `ListingMapService.build_viewport(filters, applicant, zoom) -> ListingMapViewport`.

```python
@dataclass(frozen=True, slots=True)
class ListingMapViewport:
    markers: tuple[ListingMapMarker, ...]
    clusters: tuple[ListingMapCluster, ...]
    matching_complex_count: int
    mapped_complex_count: int
    unmapped_complex_count: int
    bounds: tuple[float, float, float, float] | None

    def to_dict(self) -> dict[str, object]: ...
```

- [ ] **Step 1: Write failing aggregate and membership tests**

```python
def test_map_viewport_groups_all_matching_complexes_even_when_listing_page_size_is_one(session):
    _seed_complexes(session, coordinates=[(1, 37.50, 126.80), (2, 37.51, 126.81), (3, None, None)])
    _seed_active_listings(session, complex_ids=[1, 2, 3])
    viewport = ListingMapService(session).build_viewport(
        ListingSearchFilter(page_size=1), applicant=None, zoom=7,
    )

    assert viewport.matching_complex_count == 3
    assert viewport.mapped_complex_count == 2
    assert viewport.unmapped_complex_count == 1
    assert sum(cluster.complex_count for cluster in viewport.clusters) + len(viewport.markers) == 2


def test_map_viewport_returns_single_markers_after_zoomed_in_cell_split(session):
    _seed_complexes(session, coordinates=[(1, 37.5000, 126.8000), (2, 37.5100, 126.8100)])
    _seed_active_listings(session, complex_ids=[1, 2])

    viewport = ListingMapService(session).build_viewport(ListingSearchFilter(), applicant=None, zoom=14)

    assert [marker.complex_id for marker in viewport.markers] == [1, 2]
    assert viewport.clusters == ()
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `python -m pytest tests/unit/test_listing_map_service.py -q`

Expected: FAIL because the current service accepts a page `SearchResult` and can only create page markers.

- [ ] **Step 3: Expose the exact matching-row source and implement aggregate DTOs**

Add these public methods to `ListingSearchService` without changing cursor behavior:

```python
def map_candidate_rows(self, filters: ListingSearchFilter, applicant: Any):
    self._validate(filters)
    self._validate_purchase_affordability_profile(filters, applicant)
    if filters.only_purchase_affordable:
        return self._purchase_candidate_rows(filters, applicant), lambda row: self._is_purchase_affordable(row, filters, applicant)
    if filters.only_eligible_loans:
        return self._eligible_candidate_rows(filters, applicant), lambda row: self._is_loan_eligible(row, applicant)
    return self._filtered_rows(filters), lambda row: True

def stream_map_matching_rows(self, filters: ListingSearchFilter, applicant: Any):
    statement, matches = self.map_candidate_rows(filters, applicant)
    for row in self.db.scalars(statement.order_by(ListingCurrent.article_id).execution_options(yield_per=1000)):
        if matches(row):
            yield row
```

`ListingMapService.build_viewport` must stream all matching rows, aggregate them by `complex_id` in a dictionary, and then load all required `ComplexCurrent` rows in one query. Use the exact matched listing count and `min`/`max` primary price per complex. Count a complex without a verified coordinate as `unmapped_complex_count`; never manufacture a coordinate.

Implement pure helper `cluster_map_complexes(complexes, zoom) -> tuple[tuple[ListingMapMarker, ...], tuple[ListingMapCluster, ...]]`. It assigns every verified complex to a `(floor(latitude / cell_size), floor(longitude / cell_size))` key using the exact sizes below. A one-member cell returns a marker; a multi-member cell returns a cluster whose center is the arithmetic mean and whose bounds are the min/max member coordinates.

```python
def map_cell_size(zoom: int) -> Decimal:
    if zoom <= 7: return Decimal("0.50")
    if zoom <= 9: return Decimal("0.10")
    if zoom <= 11: return Decimal("0.02")
    return Decimal("0.005")
```

Use a `ListingMapCluster` DTO with `latitude`, `longitude`, `west`, `south`, `east`, `north`, `complex_count`, `listing_count`, `min_price`, and `max_price`. Its `to_dict()` must include `kind: "cluster"`; marker dictionaries must include `kind: "marker"`.

- [ ] **Step 4: Add the shared-filter integration test and run Task 1 tests**

```python
def test_map_candidate_rows_obey_the_same_price_and_bounds_predicates_as_listing_search(session):
    filters = ListingSearchFilter(min_price=500_000_000, map_west=Decimal("126.80"), map_south=Decimal("37.50"), map_east=Decimal("126.90"), map_north=Decimal("37.60"))
    search_rows = ListingSearchService(session).search_listings(filters).items
    map_rows = list(ListingSearchService(session).stream_map_matching_rows(filters, applicant=None))
    assert {row.article_id for row in map_rows} == {row.article_id for row in search_rows}
```

Run: `python -m pytest tests/unit/test_listing_map_service.py tests/integration/test_listing_search_v2.py -k "map or candidate" -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 1 only**

```powershell
git add -- src/realty_radar/application/listing_search_service.py src/realty_radar/application/listing_map_service.py tests/unit/test_listing_map_service.py tests/integration/test_listing_search_v2.py
git commit -m "feat: aggregate all matching complexes for maps"
```

### Task 2: Serve stable map JSON and a cards-only fragment

**Files:**
- Modify: `src/realty_radar/web/routes/home.py`
- Create: `src/realty_radar/web/templates/listings/_listing_collection.html`
- Modify: `src/realty_radar/web/templates/listings/list_partial.html`
- Modify: `src/realty_radar/web/templates/listings/_map_sidebar.html`
- Modify: `tests/integration/test_listing_map_ui.py`

**Interfaces:**
- Consumes: `GET /api/listings/map-data` query filters plus `map_zoom` and `map_initial`, and `GET /listings/map-cards` query filters with optional bounds.
- Produces: a `JSONResponse` from the first route and an outer-swappable `<section id="listing-collection">` from the second.

- [ ] **Step 1: Write the failing endpoint and fragment tests**

```python
def test_map_data_endpoint_returns_all_aggregate_counts_without_geocoding(monkeypatch):
    factory = _factory_with_three_complexes(two_verified=True)
    monkeypatch.setattr(home, "NaverGeocoder", lambda: (_ for _ in ()).throw(AssertionError("read-only endpoint")))
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/api/listings/map-data?map_zoom=7")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["matching_complex_count"] == 3
    assert payload["mapped_complex_count"] == 2
    assert payload["unmapped_complex_count"] == 1


def test_map_cards_endpoint_returns_collection_without_a_second_map_root(monkeypatch):
    response = _client_with_verified_factory(monkeypatch).get(
        "/listings/map-cards?map_west=126.80&map_south=37.50&map_east=126.90&map_north=37.60",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert 'id="listing-collection"' in response.text
    assert "data-listing-map-root" not in response.text
```

- [ ] **Step 2: Run the endpoint tests to verify failure**

Run: `python -m pytest tests/integration/test_listing_map_ui.py -k "map_data or map_cards" -q`

Expected: FAIL because neither route nor the extracted collection template exists.

- [ ] **Step 3: Add routes, URL builders, and templates**

Add `map_zoom: int = Query(ge=0, le=21)` and `map_initial: bool = Query(False)` to `map_data`. When `map_initial` is true, clear all four map-bound fields with `replace()` before calling `ListingMapService(db).build_viewport(filters, applicant, map_zoom)`; this returns clusters for the entire active search rather than only an arbitrary default map viewport. Return `JSONResponse(viewport.to_dict())`. Add `_map_data_url(request, filters)` that clears cursor and all four bounds, then points to `map_data`.

Extract the existing `#listing-collection` section, cards macro call, and pager from `list_partial.html` unchanged into `_listing_collection.html`. Add `GET /listings/map-cards` that calls `_render_result`-equivalent search work and renders this template with the same `listings`, `complex_urls`, `favorite_listing_payloads`, `previous_url`, and `next_url` context. Its validation error response must target `#listing-collection` and leave the map root untouched.

Replace page-only `map_markers` payload in `_map_sidebar.html` with:

```html
<section data-listing-map-root data-map-data-url="{{ map_data_url }}" data-map-cards-url="{{ map_cards_url }}">
  <span data-map-matching-count>0</span>
  <span data-map-mapped-count>0</span>
  <span data-map-unmapped-count>0</span>
  <div data-listings-map></div>
  <p data-listing-map-status></p>
</section>
```

Keep the public client ID only in the Maps script URL. Do not serialize server credentials or invoke a geocoder.

- [ ] **Step 4: Run route and rendered HTML tests**

Run: `python -m pytest tests/integration/test_listing_map_ui.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 2 only**

```powershell
git add -- src/realty_radar/web/routes/home.py src/realty_radar/web/templates/listings/_listing_collection.html src/realty_radar/web/templates/listings/list_partial.html src/realty_radar/web/templates/listings/_map_sidebar.html tests/integration/test_listing_map_ui.py
git commit -m "feat: add independent map and card responses"
```

### Task 3: Render clusters and independently refresh map and cards

**Files:**
- Modify: `src/realty_radar/web/static/listing-map.js`
- Modify: `tests/web/test_listing_map_controller.mjs`

**Interfaces:**
- Consumes: map JSON `{markers, clusters, matching_complex_count, mapped_complex_count, unmapped_complex_count, bounds}` and `data-map-data-url`/`data-map-cards-url`.
- Produces: current map overlays, status counts, and cards constrained only after a valid settled viewport.

- [ ] **Step 1: Write the failing controller tests**

```javascript
test('map data renders a count cluster and does not swap cards while zoomed out', async () => {
  const { controller, state } = loadController({ mapData: {
    markers: [], clusters: [{ kind: 'cluster', latitude: 37.55, longitude: 126.85, west: 126.8, south: 37.5, east: 126.9, north: 37.6, complex_count: 12, listing_count: 35, min_price: 500000000, max_price: 700000000 }],
    matching_complex_count: 12, mapped_complex_count: 12, unmapped_complex_count: 0,
  }});
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.flushFetches();

  assert.equal(state.overlays.length, 1);
  assert.match(state.overlays[0].options.icon.content, /12개 단지/);
  assert.equal(state.cardFetches.length, 0);
});

test('cluster click fits its stored bounds and a valid idle later refreshes cards only', async () => {
  const { controller, state } = loadController({ zoom: 12, mapData: singleClusterPayload });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });
  controller.mount(root);
  await state.clickOverlay(0);
  state.emitMap('idle');
  await state.advanceDebounce();

  assert.deepEqual(state.maps[0].fitBoundsCalls[0], { west: 126.8, south: 37.5, east: 126.9, north: 37.6 });
  assert.equal(state.cardSwaps, 1);
  assert.equal(state.mapSwaps, 0);
});
```

- [ ] **Step 2: Run the controller tests to verify failure**

Run: `node --test tests/web/test_listing_map_controller.mjs`

Expected: FAIL because the controller only accepts a marker array and replaces the entire search result on viewport changes.

- [ ] **Step 3: Replace overlay and request responsibilities**

Create `requestMapData(root, map, instance, { initial = false } = {})` and `requestCards(root, map, instance)` with independent incrementing IDs. Both derive the four bounds from `viewportFromMap`; `requestMapData` always runs after initial mount and settled user movement, while `requestCards` returns early unless the existing zoom/span guard passes. `requestMapData` includes `map_initial=true` only for the first call.

```javascript
function clearOverlays(instance) {
  instance.overlays.forEach((overlay) => overlay.setMap(null));
  instance.overlays = [];
}

function renderViewport(root, map, instance, payload) {
  clearOverlays(instance);
  payload.clusters.forEach((cluster) => instance.overlays.push(makeClusterOverlay(map, cluster)));
  payload.markers.forEach((marker) => instance.overlays.push(makeMarkerOverlay(map, marker)));
  root.querySelector('[data-map-matching-count]').textContent = String(payload.matching_complex_count);
  root.querySelector('[data-map-mapped-count]').textContent = String(payload.mapped_complex_count);
  root.querySelector('[data-map-unmapped-count]').textContent = String(payload.unmapped_complex_count);
}
```

`makeClusterOverlay` creates a NAVER marker with an HTML `icon.content` containing the escaped `complex_count + "개 단지"`; its click listener builds `LatLngBounds` from cluster west/south/east/north and calls `map.fitBounds`. `makeMarkerOverlay` retains the existing escaped information window and adds a compact lowest-price/listing-count HTML marker. Track every overlay listener in `instance.listeners` and remove it in `unmount`.

Mount even when the initial payload has no markers: create `new naver.maps.Map(container, { center: new naver.maps.LatLng(36.5, 127.8), zoom: 7 })`, then call `requestMapData(root, map, instance, { initial: true })`. After the first successful response only, if `payload.bounds` is present, call `map.fitBounds` for that all-results extent and set `instance.initialBoundsApplied = true`; do not mark that programmatic fit as user interaction. Later map-data requests use the actual viewport bounds.

For card refresh, fetch `data-map-cards-url` with `HX-Request: true`, then call `window.htmx.swap(document.querySelector('#listing-collection'), html, {swapStyle: 'outerHTML'})`. Never swap `#search-results`, never call `history.pushState`, and never recreate the map after a cards response.

- [ ] **Step 4: Run JavaScript tests**

Run: `node --test tests/web/test_listing_map_controller.mjs`

Expected: PASS.

- [ ] **Step 5: Commit Task 3 only**

```powershell
git add -- src/realty_radar/web/static/listing-map.js tests/web/test_listing_map_controller.mjs
git commit -m "feat: cluster matching complexes on map"
```

### Task 4: Verify exactness, query cost, and browser flow

**Files:**
- Modify: only a file from Tasks 1-3 when a direct test or benchmark failure requires it.
- Test: `tests/unit/test_listing_map_service.py`
- Test: `tests/integration/test_listing_search_v2.py`
- Test: `tests/integration/test_listing_map_ui.py`
- Test: `tests/web/test_listing_map_controller.mjs`

**Interfaces:**
- Consumes: completed map and card endpoints.
- Produces: measured, responsive map behavior without an unproven new index.

- [ ] **Step 1: Run automated regression and whitespace checks**

Run: `git diff --check -- src/realty_radar/application/listing_map_service.py src/realty_radar/application/listing_search_service.py src/realty_radar/web/routes/home.py src/realty_radar/web/static/listing-map.js src/realty_radar/web/templates/listings/_map_sidebar.html src/realty_radar/web/templates/listings/_listing_collection.html src/realty_radar/web/templates/listings/list_partial.html; python -m pytest tests/unit/test_listing_map_service.py tests/integration/test_listing_search_v2.py tests/integration/test_listing_map_ui.py -q; node --test tests/web/test_listing_map_controller.mjs`

Expected: no whitespace errors and all tests pass.

- [ ] **Step 2: Capture actual MySQL query-plan evidence**

Create the exact normal-filter map aggregate statement through `ListingMapService.build_viewport(ListingSearchFilter(), None, 7)` with SQLAlchemy engine echo temporarily disabled. Run `EXPLAIN ANALYZE` for its SQL on the configured MySQL database and record the plan and duration. If p95 across 30 representative calls exceeds 1 second, stop before adding an index and report the plan; only an observed bottleneck authorizes a focused index or materialized read-model design.

- [ ] **Step 3: Browser verification**

Run the local server and verify:

```text
Open / -> wait for clusters -> header counts equal markers plus cluster membership plus unmapped count.
Click a cluster -> map zooms to stored bounds -> individual price markers appear when cells split.
Drag at zoom 12 -> wait 300 ms -> only #listing-collection changes and cards lie inside viewport.
Zoom out -> clusters update but the existing cards remain.
Disable map script or return 500 from map-data -> cards remain visible and status explains the map error.
Use a mobile viewport -> map remains above a single-column card collection.
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q; node --test tests/web/test_listing_map_controller.mjs`

Expected: all existing tests pass.

- [ ] **Step 5: Commit direct verification fixes only**

```powershell
git add -- <only files changed by direct verification failures>
git commit -m "test: verify map aggregation flow"
```
