# Map-first Listing UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make map exploration the default listing flow while making selected-listing comparison faster and keeping saved filters, pagination, and coordinate truthfulness safe.

**Architecture:** Keep `ListingSearchFilter` as the sole backend search contract and add four transient coordinate bounds to it. `ListingSearchService` joins `ComplexCurrent` only when all bounds are present and only accepts verified coordinates; the browser debounces Naver map `idle` after an explicit user viewport interaction, fetches an HTMX partial without changing history, and discards stale responses. The existing favorites store remains the selection source for a compact comparison tray and the existing modal.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, HTMX, Alpine.js, Naver Maps JavaScript API, pytest, Node.js built-in test runner.

## Global Constraints

- Bounds are `map_west`, `map_south`, `map_east`, and `map_north` `Decimal` values; all four are required together, longitude is west/east, latitude is south/north, and both edges are inclusive.
- Bounds are transient: `ListingSearchFilter.to_dict()` must omit them, map requests must not use `hx-push-url`, and a bound update resets the cursor.
- Verified-coordinate search uses `ComplexCurrent.geocode_status == GEOCODE_STATUS_OK` and non-null latitude/longitude only. No geocoding may run in `/listings/search`.
- Do not add a coordinate index until a representative MySQL `EXPLAIN ANALYZE` has been captured. This plan initially uses the existing listing-complex relationship.
- Preserve existing user worktree changes: do not reset, stage, commit, or reformat unrelated files.
- Use `python -m pytest`, not bare `pytest`.

---

## File Structure

- `src/realty_radar/domain/listing/filters.py` — transient bounds fields, persistence exclusion, and deserialization normalization.
- `src/realty_radar/application/listing_search_service.py` — bounds validation and the verified-coordinate join/predicates.
- `src/realty_radar/web/routes/home.py` — query parsing, ephemeral map request URL, and template state.
- `src/realty_radar/web/static/listing-map.js` — explicit viewport interaction, 300 ms debounced request, broad-view guard, and stale-response protection.
- `src/realty_radar/web/templates/listings/list_partial.html` / `_map_sidebar.html` — map-first order, loading feedback, responsive surface, and map search data attributes.
- `src/realty_radar/web/templates/listings/_listing_cards.html` / `index.html` — card decision hierarchy and favorites-backed comparison tray.
- `tests/integration/test_listing_search_v2.py`, `tests/integration/test_listing_map_ui.py`, and `tests/web/test_listing_map_controller.mjs` — backend, rendered HTML, and map-controller behavior.

### Task 1: Comparison-first listing cards

**Files:**
- Modify: `src/realty_radar/web/templates/listings/_listing_cards.html`
- Modify: `src/realty_radar/web/templates/listings/index.html`
- Modify: `src/realty_radar/web/routes/home.py`
- Test: `tests/integration/test_listing_map_ui.py`

**Interfaces:**
- Consumes: existing `favorite_listing_payloads[article_id]` and `FavoritesManager.listings`.
- Produces: `#favorite-compare-tray`, `[data-favorite-compare-count]`, and a stable favorite payload with `commute_label`.

- [ ] **Step 1: Write the failing rendered-HTML test**

```python
def test_search_result_has_a_hidden_until_two_selected_comparison_tray(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert 'id="favorite-compare-tray"' in response.text
    assert 'data-favorite-compare-count' in response.text
    assert 'data-favorite-compare-button' in response.text
    assert '확인 대기' in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/test_listing_map_ui.py::test_search_result_has_a_hidden_until_two_selected_comparison_tray -q`

Expected: FAIL because the tray data attributes do not exist.

- [ ] **Step 3: Implement the smallest comparison UI**

```html
<aside id="favorite-compare-tray" hidden class="fixed inset-x-4 bottom-4 z-40 mx-auto flex w-[min(34rem,calc(100vw-2rem))] items-center justify-between gap-3 rounded-2xl border border-indigo-200 bg-white p-3 shadow-2xl dark:border-indigo-800 dark:bg-slate-950">
  <span><strong data-favorite-compare-count>0</strong>개 선택</span>
  <button data-favorite-compare-button type="button" onclick="openFavoriteCompareModal()">비교하기</button>
</aside>
```

```javascript
const tray = document.getElementById("favorite-compare-tray");
const compareCount = document.querySelector("[data-favorite-compare-count]");
if (tray) tray.hidden = count < 2;
if (compareCount) compareCount.textContent = count;
```

In `_favorite_listing_payload`, add `commute_label` as the explicit current search condition (`"강남 N분 이내 검색"`) or `"확인 대기"`; label the existing comparison-table row `통근 검색 조건` so it cannot be mistaken for a calculated journey time. In card tags, render zero/absent construction year, household count, direction, and loan data as `확인 대기` instead of `-` or an omitted decision factor.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/integration/test_listing_map_ui.py::test_search_result_has_a_hidden_until_two_selected_comparison_tray -q`

Expected: PASS.

### Task 2: Verified coordinate bounds contract and search

**Files:**
- Modify: `src/realty_radar/domain/listing/filters.py`
- Modify: `src/realty_radar/application/listing_search_service.py`
- Modify: `src/realty_radar/web/routes/home.py`
- Test: `tests/integration/test_listing_search_v2.py`
- Test: `tests/integration/test_listing_map_ui.py`

**Interfaces:**
- Consumes: `ListingSearchFilter(map_west, map_south, map_east, map_north)`.
- Produces: a bound result containing only active listings joined to verified `ComplexCurrent` coordinates, and `map_search_url` with no bounds or cursor.

- [ ] **Step 1: Write failing database and cursor tests**

```python
def test_map_bounds_include_edges_but_exclude_unverified_and_outside_listings():
    session = _session()
    _seed(session)
    complexes = {row.complex_id: row for row in session.query(ComplexCurrent).all()}
    complexes[1001].latitude, complexes[1001].longitude, complexes[1001].geocode_status = (Decimal("37.50"), Decimal("126.80"), 1)
    complexes[1002].latitude, complexes[1002].longitude, complexes[1002].geocode_status = (Decimal("37.60"), Decimal("126.90"), 1)
    session.commit()

    result = ListingSearchService(session, cursor_secret="test-secret").search_listings(
        ListingSearchFilter(map_west=Decimal("126.80"), map_south=Decimal("37.50"), map_east=Decimal("126.85"), map_north=Decimal("37.55"))
    )
    assert [row.article_id for row in result.items] == [2001, 2002]

def test_cursor_cannot_be_reused_for_another_map_viewport():
    session = _session()
    _seed(session)
    for complex in session.query(ComplexCurrent).all():
        complex.latitude, complex.longitude, complex.geocode_status = Decimal("37.50"), Decimal("126.80"), 1
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")
    first = service.search_listings(ListingSearchFilter(
        map_west=Decimal("126.79"), map_south=Decimal("37.49"),
        map_east=Decimal("126.85"), map_north=Decimal("37.55"), page_size=1,
    ))
    with pytest.raises(ValueError, match="cursor"):
        service.search_listings(ListingSearchFilter(
            map_west=Decimal("126.79"), map_south=Decimal("37.49"),
            map_east=Decimal("126.86"), map_north=Decimal("37.55"),
            page_size=1, cursor=first.next_cursor,
        ))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/integration/test_listing_search_v2.py -k "map_bounds or map_viewport" -q`

Expected: FAIL because `ListingSearchFilter` has no map bounds.

- [ ] **Step 3: Add the minimal contract and predicate**

```python
map_west: Decimal | None = None
map_south: Decimal | None = None
map_east: Decimal | None = None
map_north: Decimal | None = None

@property
def has_map_bounds(self) -> bool:
    return all(value is not None for value in (self.map_west, self.map_south, self.map_east, self.map_north))
```

```python
if filters.has_map_bounds:
    statement = statement.join(ComplexCurrent, ComplexCurrent.complex_id == ListingCurrent.complex_id).where(
        ComplexCurrent.geocode_status == GEOCODE_STATUS_OK,
        ComplexCurrent.latitude.is_not(None),
        ComplexCurrent.longitude.is_not(None),
        ComplexCurrent.longitude >= filters.map_west,
        ComplexCurrent.longitude <= filters.map_east,
        ComplexCurrent.latitude >= filters.map_south,
        ComplexCurrent.latitude <= filters.map_north,
    )
```

Validate that the values are all absent or all present, finite, in geographic range, and west `<` east / south `<` north. Keep bounds in `fingerprint_values()` but remove all four from `to_dict()`. Parse the four query parameters in `parse_search_filter`; include them in `_filter_query_items`; create `_map_search_url()` from a `replace(filters, cursor=None, map_west=None, map_south=None, map_east=None, map_north=None)` clone. Do not call the geocoder in this flow.

- [ ] **Step 4: Run focused backend tests**

Run: `python -m pytest tests/integration/test_listing_search_v2.py -k "map_bounds or map_viewport or cursor" -q`

Expected: PASS.

- [ ] **Step 5: Write and run the HTTP contract test**

```python
def test_map_bound_search_renders_matching_cards_and_a_bounds_free_map_request(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    def override_db():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/listings/search?map_west=126.80&map_south=37.50&map_east=126.85&map_north=37.55")
    finally:
        app.dependency_overrides.clear()
    assert "지도 테스트 아파트" in response.text
    assert 'data-map-search-url="http://testserver/listings/search?' in response.text
    url = re.search(r'data-map-search-url="([^"]+)"', response.text).group(1)
    assert "map_west" not in url
```

Run: `python -m pytest tests/integration/test_listing_map_ui.py -q`

Expected: PASS.

### Task 3: Map-first layout and safe viewport requests

**Files:**
- Modify: `src/realty_radar/web/templates/listings/list_partial.html`
- Modify: `src/realty_radar/web/templates/listings/_map_sidebar.html`
- Modify: `src/realty_radar/web/static/listing-map.js`
- Test: `tests/web/test_listing_map_controller.mjs`
- Test: `tests/integration/test_listing_map_ui.py`

**Interfaces:**
- Consumes: `data-map-search-url`, a Naver `Map` with `getBounds()`/`getZoom()`, and an HTMX result target `#search-results`.
- Produces: a central `data-listing-map-root` surface, a `data-map-loading` state, and one bounds request per settled valid interaction.

- [ ] **Step 1: Write the failing map-controller test**

```javascript
test('a settled user map interaction requests bounds without cursor or history mutation', async () => {
  const { controller, state } = loadController();
  const root = createRoot([{
    complex_id: 1, complex_name: '테스트 단지', address: '서울',
    latitude: 37.55, longitude: 126.85, listing_count: 1,
    min_price: 500000000, max_price: 500000000,
  }], { mapSearchUrl: '/listings/search?sort_by=price_asc' });
  controller.mount(root);
  state.emitMap('dragstart');
  state.emitMap('idle');
  await state.advanceDebounce();

  assert.match(state.fetches[0], /map_west=126\.8/);
  assert.match(state.fetches[0], /map_north=37\.6/);
  assert.doesNotMatch(state.fetches[0], /cursor=/);
  assert.equal(state.swaps, 1);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/web/test_listing_map_controller.mjs`

Expected: FAIL because map idle does not issue a bounds request.

- [ ] **Step 3: Implement central map and request control**

```javascript
const VIEWPORT_DEBOUNCE_MS = 300;
const MIN_SEARCH_ZOOM = 11;

function scheduleViewportSearch(root, map, instance) {
  clearTimeout(instance.viewportTimer);
  instance.viewportTimer = setTimeout(() => requestViewport(root, map, instance), VIEWPORT_DEBOUNCE_MS);
}
```

Attach `dragstart`, `zoom_changed`, and `idle` listeners after initial `fitBounds`; set a `viewportDirty` flag on interaction and only schedule on `idle` when it is set. Build a URL from `root.dataset.mapSearchUrl`, delete `cursor`, set the four bounds, reject zoom below 11 or spans over the documented maximum with a status message, and fetch with `HX-Request: true`. Increment a request token before each fetch; only the latest token may call `htmx.swap(target, html, {swapStyle: "outerHTML"})`. On a valid request, toggle `[data-map-loading]`; on failure, leave the current result in place and set an explanatory status.

In `list_partial.html`, change the desktop two-column sidebar grid to a single flow: map root first, then result summary/cards/pager; add `data-map-search-url="{{ map_search_url }}"` and `data-map-loading` feedback. In `_map_sidebar.html`, use `h-[56vh] min-h-[360px] max-h-[680px]` and retain the missing-configuration/coordinate-pending messages. Set map-bounded pager links to `hx-push-url="false"`.

- [ ] **Step 4: Run JS and rendered layout tests**

Run: `node --test tests/web/test_listing_map_controller.mjs; python -m pytest tests/integration/test_listing_map_ui.py -q`

Expected: both commands PASS.

### Task 4: Focused polish and end-to-end verification

**Files:**
- Modify: only files changed by Tasks 1–3 when verification exposes a direct requirement failure.
- Test: `tests/integration/test_listing_search_v2.py`
- Test: `tests/integration/test_listing_map_ui.py`
- Test: `tests/web/test_listing_map_controller.mjs`

**Interfaces:**
- Consumes: the completed card, bounds, and map-controller interfaces.
- Produces: verified desktop/mobile map-first UX with no newly required index.

- [ ] **Step 1: Run static and focused automated verification**

Run: `git diff --check -- src/realty_radar/domain/listing/filters.py src/realty_radar/application/listing_search_service.py src/realty_radar/web/routes/home.py src/realty_radar/web/static/listing-map.js src/realty_radar/web/templates/listings/list_partial.html src/realty_radar/web/templates/listings/_map_sidebar.html src/realty_radar/web/templates/listings/_listing_cards.html src/realty_radar/web/templates/listings/index.html; python -m pytest tests/integration/test_listing_search_v2.py tests/integration/test_listing_map_ui.py -q; node --test tests/web/test_listing_map_controller.mjs`

Expected: no whitespace errors in the listed files and all tests PASS.

- [ ] **Step 2: Capture query-plan evidence without creating an index**

Run: `python -c "from realty_radar.config import settings; print(settings.database_url)"`

Then, against the configured MySQL database only, run an `EXPLAIN ANALYZE` for the actual bound SQL emitted by `ListingSearchService._filtered_rows(...)`, recording the plan in the task result. If the configured database is SQLite or unavailable, record that production index evidence is unavailable and make no migration.

- [ ] **Step 3: Browser verification**

Run the local server and verify with agent-browser:

```text
open / → map appears above cards → favorite two cards → comparison tray appears → open modal
drag or zoom map → wait 300 ms → cards update only for current bounds
zoom out below the guard → current cards remain and broad-view message appears
set a mobile viewport → map remains before a one-column card list
toggle light/dark → primary labels remain readable
```

- [ ] **Step 4: Run the full regression suite**

Run: `python -m pytest -q; node --test tests/web/test_listing_map_controller.mjs`

Expected: all existing tests pass. Do not stage or commit because this checkout contains user-owned uncommitted changes.
