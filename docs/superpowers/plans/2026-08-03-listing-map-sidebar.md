# Listing Map Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep results as a fixed list-and-map-sidebar layout and populate the sidebar map for each current result page without delaying listing search.

**Architecture:** The ordinary listing response keeps its existing verified markers and starts an HTMX request for a map-only fragment. The fragment reuses the same filter, calls `ComplexGeocodeBackfill` only for the result page's complex IDs, then builds the public marker payload from persisted verified coordinates.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, HTMX, Naver Maps JavaScript SDK, pytest, Node.js test runner.

## Global Constraints

- Do not expose `NAVER_MAP_CLIENT_SECRET` in HTML or JavaScript.
- Never fabricate map coordinates; render markers only from verified database coordinates.
- Limit on-demand geocoding to the current page's distinct result complex IDs.
- Preserve the user’s existing uncommitted work; stage or commit no implementation files in this dirty worktree.
- Use `python -m pytest`, not bare `pytest`.

---

### Task 1: Make result complex IDs available to the map route

**Files:**
- Modify: `src/realty_radar/application/listing_map_service.py`
- Modify: `tests/unit/test_listing_map_service.py`

**Interfaces:**
- Consumes: `SearchResult` in normal or `is_grouped=True` form.
- Produces: `ListingMapService.complex_ids(result: SearchResult) -> list[int]`, in search-result order with duplicates removed.

- [ ] **Step 1: Write the failing test**

```python
def test_complex_ids_returns_each_normal_result_complex_once_in_result_order():
    result = SearchResult(items=[item(7), item(3), item(7)], next_cursor=None, has_more=False)

    assert ListingMapService(session).complex_ids(result) == [7, 3]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_listing_map_service.py::test_complex_ids_returns_each_normal_result_complex_once_in_result_order -q`

Expected: FAIL because `complex_ids` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def complex_ids(self, result: SearchResult) -> list[int]:
    return list(self._summaries(result))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_listing_map_service.py::test_complex_ids_returns_each_normal_result_complex_once_in_result_order -q`

Expected: PASS.

### Task 2: Serve an independently refreshable map sidebar

**Files:**
- Create: `src/realty_radar/web/templates/listings/_map_sidebar.html`
- Modify: `src/realty_radar/web/routes/home.py`
- Modify: `src/realty_radar/web/templates/listings/list_partial.html`
- Modify: `tests/integration/test_listing_map_ui.py`

**Interfaces:**
- Consumes: `GET /listings/map` with `parse_search_filter` query values.
- Produces: a map-sidebar fragment containing either the Naver marker payload or a concrete map status.

- [ ] **Step 1: Write the failing integration test**

```python
def test_map_sidebar_geocodes_only_the_current_pending_result_and_returns_a_marker(monkeypatch):
    monkeypatch.setattr(home, "NaverGeocoder", StaticGeocoderReturning(37.55, 126.85))

    response = TestClient(app).get("/listings/map")

    assert response.status_code == 200
    assert json.loads(extract_payload(response.text))[0]["complex_id"] == 1
    assert "server-secret" not in response.text
    assert refreshed_complex().geocode_status == GEOCODE_STATUS_OK
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/test_listing_map_ui.py::test_map_sidebar_geocodes_only_the_current_pending_result_and_returns_a_marker -q`

Expected: FAIL with HTTP 404 because `/listings/map` is absent.

- [ ] **Step 3: Add the minimal route and fragment**

```python
@router.get("/listings/map", response_class=HTMLResponse, name="listing_map")
def listing_map(request: Request, db: Session, filters: ListingSearchFilter):
    result = ListingSearchService(db).search_listings(filters, applicant=get_request_user_profile(request))
    service = ListingMapService(db)
    ComplexGeocodeBackfill(db, NaverGeocoder()).run(
        batch_size=len(service.complex_ids(result)), now=datetime.now(timezone.utc).replace(tzinfo=None),
        complex_ids=service.complex_ids(result),
    )
    db.commit()
    return templates.TemplateResponse(request, "listings/_map_sidebar.html", _listing_map_context(db, result))
```

The real implementation must skip the backfill when no public map key or no result complex exists, roll back on an unexpected exception, and put a user-visible failure message in the fragment.

- [ ] **Step 4: Put the fragment behind an HTMX load trigger**

```html
<div id="map-sticky-wrapper" data-listing-map-root
     hx-get="{{ map_sidebar_url }}" hx-trigger="load" hx-swap="innerHTML">
  {% include "listings/_map_sidebar.html" %}
</div>
```

The initial response uses existing markers immediately when present; otherwise it says that coordinates are being prepared. The sidebar fragment replaces only inner content so the listing cards never reload.

- [ ] **Step 5: Run the focused integration tests**

Run: `python -m pytest tests/integration/test_listing_map_ui.py -q`

Expected: PASS, including the public-key/secret boundary and map route backfill.

### Task 3: Remove alternate view modes while retaining the right sidebar

**Files:**
- Modify: `src/realty_radar/web/templates/listings/index.html`
- Modify: `tests/integration/test_listing_map_ui.py`
- Test: `tests/web/test_listing_map_controller.mjs`

**Interfaces:**
- Consumes: normal search response and HTMX map-sidebar replacement.
- Produces: one permanent result layout, and a map controller that mounts after the replacement.

- [ ] **Step 1: Write the failing observable-layout test**

```python
def test_search_response_has_a_map_sidebar_loader_but_no_alternate_view_controls(monkeypatch):
    response = TestClient(app).get("/")

    assert 'data-listing-map-root' in response.text
    assert 'hx-get="/listings/map?' in response.text
    assert 'data-view-mode=' not in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/test_listing_map_ui.py::test_search_response_has_a_map_sidebar_loader_but_no_alternate_view_controls -q`

Expected: FAIL because the current template renders `data-view-mode` buttons.

- [ ] **Step 3: Remove the controls and their handler**

Delete the `view-mode-switcher` element and the `setViewMode` script. Keep `#search-main-container` as the existing desktop two-column grid and leave the sidebar visible at every desktop width.

- [ ] **Step 4: Run all map-focused checks**

Run: `python -m pytest tests/unit/test_listing_map_service.py tests/integration/test_listing_map_ui.py -q`

Expected: PASS.

Run: `node --test tests/web/test_listing_map_controller.mjs`

Expected: PASS.

### Task 4: Verify the full vertical slice

**Files:**
- Verify only: modified source, templates, and tests from Tasks 1-3.

- [ ] **Step 1: Static integrity checks**

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 2: Run the full test suite**

Run: `python -m pytest -q`

Expected: all tests pass.

- [ ] **Step 3: Verify local response contracts without exposing secrets**

Run a local request for `/` and `/listings/map`, confirming the root has a map sidebar, the map endpoint returns either a marker payload or a concrete status, and neither response includes the NCP secret.
