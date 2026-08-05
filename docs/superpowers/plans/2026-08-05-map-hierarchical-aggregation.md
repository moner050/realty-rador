# Map Hierarchical Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render only a small, meaningful set of map circles at each zoom level and defer complex markers until the user is sufficiently zoomed in.

**Architecture:** `ListingMapService` will select the response mode from the map zoom and aggregate verified, filter-matching complex summaries by `sido_code`, `sigungu_code`, grid cell, or complex. The browser will render every non-marker aggregate as a count circle that zooms to its reported bounds, while a marker opens the existing complex modal. The client keeps the approved 1.5-second settled-viewport delay and cancels obsolete map/card work.

**Tech Stack:** FastAPI, SQLAlchemy, MySQL/SQLite-compatible aggregate SQL, Jinja, NAVER Maps V3, vanilla JavaScript, pytest, Node test runner.

## Global Constraints

- Keep the first map at `(37.55, 126.9)`, zoom `8`, and do not request map/card APIs before a user map action.
- Wait exactly 1.5 seconds after the latest settled movement or zoom before requesting the map; cancel stale timers and in-flight requests.
- Use verified `ComplexCurrent` coordinates only, apply current filters and map bounds in every aggregate, and make no geocoding, collection, schema, or migration change.
- Use response modes `sido` for zoom 0-8, `sigungu` for zoom 9-12, `clusters` for zoom 13-14, and `markers` at zoom 15 or higher.
- Render count circles as `N건`, `N.N천 건`, or `N.N만 건`; group-circle clicks fit the exact reported bounds and complex-marker clicks open the existing modal.
- Keep the old visible map/card content while replacement data loads. Do not introduce a map-wide blur, blocking overlay, or a new database index without live `EXPLAIN ANALYZE` evidence.
- Existing changes in this worktree are user-owned approved work. Do not reset, clean, stage, or commit implementation files during these tasks; leave integration/commit choice to the user.

---

## File Structure

- `src/realty_radar/application/listing_map_service.py`: zoom-to-mode selection, static Korean region labels, SQL and stream aggregation, and viewport JSON contract.
- `src/realty_radar/web/static/listing-map.js`: abbreviated-count formatter, aggregate-circle rendering, marker threshold, and non-blocking viewport refresh.
- `src/realty_radar/web/templates/listings/_map_sidebar.html`: concise legend/status copy only if required by the new modes.
- `tests/unit/test_listing_map_service.py`: response mode, region label, count, and bounds coverage against SQLite fixtures.
- `tests/integration/test_listing_map_ui.py`: `/api/listings/map-data` contract and map UI contract coverage.
- `tests/web/test_listing_map_controller.mjs`: browser-controller behavior for 1.5-second refresh, tier rendering, click-to-fit, and card request guards.

### Task 1: Define and test the hierarchical viewport contract

**Files:**
- Modify: `tests/unit/test_listing_map_service.py: map viewport tests`
- Modify: `src/realty_radar/application/listing_map_service.py: ListingMapCluster, ListingMapViewport, map helpers`

**Interfaces:**
- Produces `map_viewport_mode(zoom: int) -> Literal["sido", "sigungu", "clusters", "markers"]`.
- Produces `aggregate_map_regions(complexes: tuple[ListingMapMarker, ...], level: Literal["sido", "sigungu"]) -> tuple[ListingMapCluster, ...]`.
- Extends `ListingMapCluster` with optional `label: str | None`; `to_dict()` omits `label` when it is absent to preserve normal grid-cluster compatibility.

- [ ] **Step 1: Write the failing unit tests for mode boundaries and region circles**

```python
def test_map_viewport_mode_uses_the_four_zoom_tiers():
    assert map_viewport_mode(8) == "sido"
    assert map_viewport_mode(9) == "sigungu"
    assert map_viewport_mode(13) == "clusters"
    assert map_viewport_mode(15) == "markers"


def test_sido_circle_sums_matching_listings_and_keeps_click_bounds():
    clusters = aggregate_map_regions(
        (
            ListingMapMarker(
                complex_id=1, complex_name="one", address="서울특별시 강남구 one",
                latitude=37.50, longitude=126.80, listing_count=2,
                min_price=500_000_000, max_price=500_000_000, sido_code=11,
            ),
            ListingMapMarker(
                complex_id=2, complex_name="two", address="서울특별시 강남구 two",
                latitude=37.60, longitude=126.90, listing_count=3,
                min_price=600_000_000, max_price=610_000_000, sido_code=11,
            ),
        ),
        "sido",
    )

    assert clusters[0].label == "서울특별시"
    assert (clusters[0].listing_count, clusters[0].complex_count) == (5, 2)
    assert (clusters[0].west, clusters[0].south, clusters[0].east, clusters[0].north) == (126.8, 37.5, 126.9, 37.6)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/unit/test_listing_map_service.py -k "four_zoom_tiers or sido_circle" -q`

Expected: FAIL because the mode helper, marker region fields, and region aggregation do not yet exist.

- [ ] **Step 3: Implement the smallest shared map-contract helpers**

```python
def map_viewport_mode(zoom: int) -> Literal["sido", "sigungu", "clusters", "markers"]:
    if zoom <= 8:
        return "sido"
    if zoom <= 12:
        return "sigungu"
    if zoom <= 14:
        return "clusters"
    return "markers"
```

Add defaulted `sido_code` and `sigungu_code` fields to `ListingMapMarker` so existing marker construction remains valid. Build labels from the existing `SIDO_CODES` and `SIGUNGU_CODES` catalog; calculate group counts, prices, average point, and min/max bounds from the member markers.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `python -m pytest tests/unit/test_listing_map_service.py -k "four_zoom_tiers or sido_circle" -q`

Expected: PASS.

### Task 2: Aggregate SQL and stream viewports before transferring complex rows

**Files:**
- Modify: `tests/unit/test_listing_map_service.py: SQL and policy-stream viewport tests`
- Modify: `src/realty_radar/application/listing_map_service.py: _build_sql_viewport, _build_stream_viewport`

**Interfaces:**
- Consumes Task 1's `map_viewport_mode` and `aggregate_map_regions`.
- Produces `ListingMapViewport.mode` plus either labelled aggregate `clusters` or complex `markers`.

- [ ] **Step 1: Write failing service tests for each data path**

```python
def test_sql_viewport_groups_verified_bound_results_by_sigungu_at_zoom_twelve():
    viewport = ListingMapService(session).build_viewport(filters_with_bounds, applicant=None, zoom=12)
    assert viewport.mode == "sigungu"
    assert [(cluster.label, cluster.listing_count) for cluster in viewport.clusters] == [("서울특별시 강남구", 3)]
    assert viewport.markers == ()


def test_policy_stream_viewport_uses_the_same_sido_contract():
    viewport = ListingMapService(session).build_viewport(
        ListingSearchFilter(only_eligible_loans=True), applicant, zoom=8
    )
    assert viewport.mode == "sido"
    assert viewport.clusters[0].label == "서울특별시"


def test_zoom_fifteen_returns_complex_markers_without_grid_clustering():
    viewport = ListingMapService(session).build_viewport(ListingSearchFilter(), applicant=None, zoom=15)
    assert [marker.complex_id for marker in viewport.markers] == [1, 2]
    assert viewport.clusters == ()
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/unit/test_listing_map_service.py -k "sigungu_at_zoom_twelve or same_sido_contract or zoom_fifteen" -q`

Expected: FAIL because the current service emits `summary` below zoom 11 and grid clusters at zoom 15.

- [ ] **Step 3: Implement SQL-first and stream-compatible aggregation**

For ordinary filters, branch from the existing `aggregates` CTE before `first_text`/full marker construction. Join verified `ComplexCurrent` rows, group by `sido_code` or `sigungu_code`, and select `count`, `sum(listing_count)`, min/max price, `avg(latitude/longitude)`, and min/max bounds. Build labelled `ListingMapCluster` instances from the rows.

For policy-stream filters, include the computed region codes while loading the existing verified coordinate rows, construct markers with those codes, then use the Task 1 helper. At zoom 13-14 retain `cluster_map_complexes`; at zoom 15 return all complex markers directly instead of grid grouping.

- [ ] **Step 4: Run focused and full map-service tests**

Run: `python -m pytest tests/unit/test_listing_map_service.py -q`

Expected: PASS, including existing filter, bounds, summary-replacement, and complex marker coverage updated to the four-mode contract.

### Task 3: Preserve the API/UI contract and map-card guard

**Files:**
- Modify: `tests/integration/test_listing_map_ui.py: map-data and map-cards tests`
- Modify: `src/realty_radar/web/routes/home.py: map_data only if response serialization needs adjustment`
- Modify: `src/realty_radar/web/templates/listings/_map_sidebar.html: mode-neutral copy only if needed`

**Interfaces:**
- Consumes Task 2 `ListingMapViewport.to_dict()`.
- Preserves `/api/listings/map-data` URL and `markers`, `clusters`, and count fields.

- [ ] **Step 1: Write failing route/UI tests**

```python
def test_map_data_returns_a_labelled_sido_circle_for_a_zoomed_out_view(monkeypatch):
    response = TestClient(app).get("/api/listings/map-data?map_zoom=8")
    payload = response.json()
    assert payload["mode"] == "sido"
    assert payload["clusters"][0]["label"] == "서울특별시"


```

- [ ] **Step 2: Run the focused integration test and verify RED**

Run: `python -m pytest tests/integration/test_listing_map_ui.py -k "labelled_sido_circle" -q`

Expected: FAIL because the previous route response reports `summary`.

- [ ] **Step 3: Keep response serialization backward-compatible**

Do not change route parameters or filter persistence. Ensure `JSONResponse(viewport.to_dict())` exposes the four mode strings and optional circle labels. Keep map bounds transient and keep `/listings/map-cards` unchanged; only the client guard decides whether to request it.

- [ ] **Step 4: Run map integration tests**

Run: `python -m pytest tests/integration/test_listing_map_ui.py -q`

Expected: PASS.

### Task 4: Render labelled circles without a blocking map reload

**Files:**
- Modify: `tests/web/test_listing_map_controller.mjs`
- Modify: `src/realty_radar/web/static/listing-map.js`
- Modify: `src/realty_radar/web/templates/listings/_map_sidebar.html` only if a concise tier legend/status target is required

**Interfaces:**
- Consumes payloads such as `{ mode: "sido", clusters: [{ label: "서울특별시", listing_count: 12500, complex_count: 120, latitude: 37.55, longitude: 126.98, west: 126.70, south: 37.40, east: 127.20, north: 37.70 }] }`.
- Uses existing `map.fitBounds()` for group circles and existing `openComplexModal()` for true complex markers.

- [ ] **Step 1: Write failing controller tests**

```javascript
test('sido and sigungu payloads render labelled count circles that fit their bounds on click', async () => {
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });
  mount(root);
  await settleUserViewport(state, { zoom: 8 });
  state.resolveMap({
    mode: 'sido', markers: [],
    clusters: [{ label: '서울특별시', listing_count: 12500, complex_count: 120,
      latitude: 37.55, longitude: 126.98, west: 126.70, south: 37.40, east: 127.20, north: 37.70 }],
  });
  assert.match(state.markerIcons[0], /서울특별시/);
  assert.match(state.markerIcons[0], /1\.3만 건/);
  state.clickMarker(0);
  assert.equal(state.fitBoundsCalls.length, 1);
});

test('zoom twelve renders sigungu circles while cards update independently', async () => {
  // After the shared 1500 ms delay, assert the circle response can render before the card response completes.
});

test('zoom fifteen renders complex marker and opens the existing modal', async () => {
  // Existing modal assertion remains the marker-level behavior.
});
```

- [ ] **Step 2: Run the controller tests and verify RED**

Run: `node --test tests/web/test_listing_map_controller.mjs`

Expected: FAIL because circles currently display only complex counts, no Korean abbreviated listing counts, and cards begin at zoom 11.

- [ ] **Step 3: Implement the smallest renderer change**

Add `formatListingCount(count)` with Korean `천`/`만` thresholds. Make aggregate circles display `label` when supplied and otherwise retain compact cluster wording. Use a mode-aware status message, hide the old summary overlay for aggregate modes, and keep true markers as the sole path to `openComplexModal()`.

Keep the card guard at `zoom >= 11`, as specified, but render the map aggregate as soon as its own response arrives. Keep the existing 1.5-second map timer, `AbortController`, request token, and visible previous content; loading remains limited to the existing small header/title indicators.

- [ ] **Step 4: Run the controller test suite and verify GREEN**

Run: `node --test tests/web/test_listing_map_controller.mjs`

Expected: PASS with the initial no-fetch/zoom-8 test, stale-request tests, circle-fit tests, card guard, and complex-modal tests.

### Task 5: Verify the worktree runtime and performance boundary

**Files:**
- Modify: none unless a failed verification identifies a test-supported defect

**Interfaces:**
- Verifies the application code from Tasks 1-4 without database migrations or collection work.

- [ ] **Step 1: Run repository regression suites and whitespace check**

Run:

```powershell
python -m pytest -q
node --test tests/web/test_listing_map_controller.mjs
git diff --check
```

Expected: all Python and Node tests pass; no whitespace errors.

- [ ] **Step 2: Run the worktree server, not the main-worktree server**

Start a temporary server from `C:\workspace\personal\real-estate-search\.worktrees\map-exploration-interactions` with the existing parent `.env` loaded only into the child process. Use a free port other than the user's `8000`, and stop it and remove only its own logs afterwards.

- [ ] **Step 3: Browser-check the observable behavior**

Verify at the temporary-server URL:

1. The first tiles are zoom 8 around Seoul/Gyeonggi/Incheon and status says the user must move or zoom; no map/card request is made before interaction.
2. A settled interaction waits 1.5 seconds, then renders a small set of labelled circles with no full-map blur.
3. Circle clicks fit bounds; at zoom 15, complex marker click opens the existing modal.
4. At zoom 8, no card request is made. At zooms 12 and 15, cards reflect the map bounds while the old cards remain visible until replacement and do not block the circle/marker response.

- [ ] **Step 4: Record the performance outcome without guessing**

Make repeated read-only requests against the temporary server for `/api/listings/map-data` at zooms 8, 12, and 15 with the same representative bounds. Report response time and payload size by mode. If zoom-15 server latency remains materially high, stop after collecting the exact SQL/path evidence; do not add an index or migration in this task.
