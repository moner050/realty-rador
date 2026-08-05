# Unified Search Panel and Map Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Present filtering and result status in one control panel while keeping the active NAVER map visible and positioned during HTMX filter searches.

**Architecture:** The search form stays static in the page. An out-of-band response swaps the result summary and a hidden map-query configuration, while the normal response swaps only #listing-collection. The map controller observes a changed configuration, preserves its existing NAVER map instance, aborts stale requests, and refreshes the current viewport immediately.

**Tech Stack:** FastAPI, Jinja2, HTMX 1.9.10, NAVER Maps V3, browser JavaScript, pytest, Node.js test runner.

## Global Constraints

- Preserve ListingSearchFilter parsing, saved-filter behavior, URL parameters, search SQL, map aggregation rules, and the 1.5-second delay for user-driven map movement.
- Do not replace, unmount, or recreate data-listing-map-root during a filter search.
- Keep prior map overlays and cards visible if a refreshed map configuration fails.
- Use python -m pytest, never bare pytest.
- Do not edit unrelated user changes under docs/.

---

### Task 1: Split static controls from HTMX search fragments

**Files:**
- Create: src/realty_radar/web/templates/listings/_search_result_summary.html
- Create: src/realty_radar/web/templates/listings/_map_search_config.html
- Modify: src/realty_radar/web/templates/listings/index.html:258-470
- Modify: src/realty_radar/web/templates/listings/list_partial.html:1-70
- Modify: src/realty_radar/web/routes/home.py:668-820
- Test: tests/integration/test_listing_map_ui.py, tests/integration/test_web_v2.py

**Interfaces:**
- Consumes: _render_result() context keys result, filters, sort_options, labels, map_data_url, map_cards_url, and map_complex_url_template.
- Produces: static data-search-control-panel, stable data-listing-map-root, #search-result-summary, #map-search-config, and HTMX response fragments for #listing-collection.

- [ ] **Step 1: Write the failing static-layout test**

~~~python
def test_map_workspace_keeps_controls_and_result_summary_in_one_panel(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert 'data-search-control-panel' in response.text
    assert 'id="listing-search-form"' in response.text
    assert 'id="search-result-summary"' in response.text
    assert response.text.index('id="listing-search-form"') < response.text.index('id="search-result-summary"')
    assert response.text.index('id="search-result-summary"') < response.text.index('data-listing-map-root')
~~~

- [ ] **Step 2: Run the test and verify RED**

Run:

~~~powershell
$taskPythonPath = Join-Path (Get-Location) 'src'; $env:PYTHONPATH = $taskPythonPath; python -m pytest tests/integration/test_listing_map_ui.py::test_map_workspace_keeps_controls_and_result_summary_in_one_panel -q
~~~

Expected: FAIL because neither the unified panel nor the standalone summary fragment exists.

- [ ] **Step 3: Extract the static components**

Move the existing title, result mode, page-size text, sort select, detailed-filter trigger, and applied condition chips into _search_result_summary.html:

~~~jinja2
<section id="search-result-summary" data-search-result-summary>
    {# current result title, sort select, trigger, and chips #}
</section>
~~~

Create _map_search_config.html with no visible content:

~~~jinja2
<div id="map-search-config" hidden
     data-map-query-key="{{ map_data_url }}"
     data-map-data-url="{{ map_data_url }}"
     data-map-cards-url="{{ map_cards_url }}"
     data-map-complex-url-template="{{ map_complex_url_template }}"></div>
~~~

In index.html, put the existing form and summary inside one data-search-control-panel card. Set the form target to #listing-collection with outerHTML; render map config, map sidebar, and collection after the panel. Remove duplicate card/shadow chrome around the summary and the anchor-only “필터 변경” control.

- [ ] **Step 4: Run the static-layout test and verify GREEN**

Run the command from Step 2.

Expected: PASS; the static control panel precedes the stable map root.

- [ ] **Step 5: Write the failing HTMX response contract test**

~~~python
def test_htmx_search_returns_collection_and_oob_search_updates(monkeypatch):
    response = TestClient(app).get(
        "/listings/search?trade_types=SALE",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert 'id="listing-collection"' in response.text
    assert 'id="search-result-summary" hx-swap-oob="outerHTML"' in response.text
    assert 'id="map-search-config" hx-swap-oob="outerHTML"' in response.text
    assert "trade_types=SALE" in response.text
    assert "data-listing-map-root" not in response.text
~~~

- [ ] **Step 6: Run the response contract test and verify RED**

Run:

~~~powershell
$taskPythonPath = Join-Path (Get-Location) 'src'; $env:PYTHONPATH = $taskPythonPath; python -m pytest tests/integration/test_listing_map_ui.py::test_htmx_search_returns_collection_and_oob_search_updates -q
~~~

Expected: FAIL because the current response replaces #search-results and includes the map root.

- [ ] **Step 7: Return out-of-band updates and a collection-only primary response**

Keep list_partial.html as the HTMX search response. Render summary and map configuration first with hx-swap-oob="outerHTML", then render _listing_collection.html as the primary response:

~~~jinja2
{% include "listings/_search_result_summary.html" with context %}
{% include "listings/_map_search_config.html" with context %}
{% include "listings/_listing_collection.html" with context %}
~~~

Pass is_htmx_search=is_htmx and not append from _render_result(). Apply the OOB attribute only for that value. Change the HTMX validation-error target to #listing-collection; retain pager target #listing-collection.

- [ ] **Step 8: Run the focused server regressions**

~~~powershell
$taskPythonPath = Join-Path (Get-Location) 'src'; $env:PYTHONPATH = $taskPythonPath; python -m pytest tests/integration/test_listing_map_ui.py tests/integration/test_web_v2.py -q
~~~

Expected: PASS. Searches update collection, summary, and map configuration without returning a map root.

- [ ] **Step 9: Commit the server/template slice**

~~~powershell
git add -- src/realty_radar/web/routes/home.py src/realty_radar/web/templates/listings/index.html src/realty_radar/web/templates/listings/list_partial.html src/realty_radar/web/templates/listings/_search_result_summary.html src/realty_radar/web/templates/listings/_map_search_config.html tests/integration/test_listing_map_ui.py tests/integration/test_web_v2.py
git commit -m "feat: unify search controls and result summary"
~~~

### Task 2: Refresh the stable map for a changed filter configuration

**Files:**
- Modify: src/realty_radar/web/static/listing-map.js:107-498
- Test: tests/web/test_listing_map_controller.mjs

**Interfaces:**
- Consumes: #map-search-config data attributes from Task 1.
- Produces: RealtyRadarListingMap.refreshSearchConfig(root, config) and an htmx:afterSettle listener that refreshes map URLs without creating a new NAVER map.

- [ ] **Step 1: Write the failing controller test**

Extend the real harness with a map-config fixture, then add:

~~~javascript
test('a changed filter configuration preserves the mounted map and refreshes its current viewport immediately', async () => {
  const { controller, state } = loadController({ zoom: 12 });
  const root = createRoot({
    mapDataUrl: '/api/listings/map-data?trade_types=JEONSE',
    mapCardsUrl: '/listings/map-cards?trade_types=JEONSE',
  });
  controller.mount(root);
  const mapBefore = state.maps[0];

  controller.refreshSearchConfig(root, {
    queryKey: 'sale',
    mapDataUrl: '/api/listings/map-data?trade_types=SALE',
    mapCardsUrl: '/listings/map-cards?trade_types=SALE',
    mapComplexUrlTemplate: '/listings/complex/__complex_id__?trade_types=SALE',
  });
  await state.flushFetches();

  assert.equal(state.maps[0], mapBefore);
  assert.match(state.mapFetches.at(-1).url, /trade_types=SALE/);
  assert.match(state.cardFetches.at(-1).url, /trade_types=SALE/);
});
~~~

- [ ] **Step 2: Run the controller test and verify RED**

~~~powershell
node --test tests/web/test_listing_map_controller.mjs --test-name-pattern "changed filter configuration"
~~~

Expected: FAIL because refreshSearchConfig is not exposed.

- [ ] **Step 3: Implement the minimal refresh operation**

Add this map-controller operation:

~~~javascript
function refreshSearchConfig(root, config) {
    const instance = instances.get(root);
    if (!instance || !config || config.queryKey === instance.mapQueryKey) return;
    root.dataset.mapDataUrl = config.mapDataUrl;
    root.dataset.mapCardsUrl = config.mapCardsUrl;
    root.dataset.mapComplexUrlTemplate = config.mapComplexUrlTemplate;
    instance.mapQueryKey = config.queryKey;
    instance.lastMapViewportKey = null;
    instance.lastCardsViewportKey = null;
    cancelMapRequest(root, instance);
    cancelCardsRequest(root, instance);
    const viewport = viewportFromMap(instance.map);
    const key = viewportKey(instance.map, viewport);
    if (!viewport || !key) return;
    requestMapData(root, instance.map, instance, { key });
    requestCards(root, instance.map, instance, key);
}
~~~

Export refreshSearchConfig. Add an htmx:afterSettle listener that reads #map-search-config, ensures the map is mounted, and calls this operation. Make beforeSwap and afterSwap unmount only a target that actually contains a map root, so collection, summary, and config swaps leave the map instance intact.

- [ ] **Step 4: Run the map suite and verify GREEN**

~~~powershell
node --test tests/web/test_listing_map_controller.mjs
~~~

Expected: PASS. The filter URL changes, the map object identity does not, and existing debounce, cancellation, stale-response, modal, focus, and card-replacement tests remain green.

- [ ] **Step 5: Commit the map lifecycle slice**

~~~powershell
git add -- src/realty_radar/web/static/listing-map.js tests/web/test_listing_map_controller.mjs
git commit -m "fix: preserve map across filter refreshes"
~~~

### Task 3: Verify readability and the full user flow

**Files:**
- Modify only if a test exposes a concrete issue: Task 1 templates or src/realty_radar/web/static/listing-map.js
- Test: tests/integration/test_listing_map_ui.py
- Test: tests/web/test_listing_filter_panel.mjs
- Test: tests/web/test_listing_map_controller.mjs

**Interfaces:**
- Consumes: stable map root and OOB search response from Tasks 1-2.
- Produces: a verified desktop/mobile panel with no filter-driven blank map.

- [ ] **Step 1: Write the duplicate-control regression test**

~~~python
def test_search_control_panel_has_one_detail_filter_entry_point(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.text.count('data-filter-panel-open') == 1
    assert 'href="#listing-search-form"' not in response.text
~~~

- [ ] **Step 2: Run it and verify RED**

~~~powershell
$taskPythonPath = Join-Path (Get-Location) 'src'; $env:PYTHONPATH = $taskPythonPath; python -m pytest tests/integration/test_listing_map_ui.py::test_search_control_panel_has_one_detail_filter_entry_point -q
~~~

Expected: FAIL if the duplicate anchor-only control remains; otherwise keep the test only when it protects the observable single-entry-point requirement.

- [ ] **Step 3: Apply the smallest visual cleanup**

Keep one explicit “상세 필터” trigger in the unified panel. Retain the map header count and loading state; remove redundant anchor-only filter navigation. Reuse existing theme tokens and do not add broad light-theme overrides.

- [ ] **Step 4: Run focused verification**

~~~powershell
$taskPythonPath = Join-Path (Get-Location) 'src'; $env:PYTHONPATH = $taskPythonPath; python -m pytest tests/integration/test_listing_map_ui.py tests/integration/test_listing_detail_ui.py tests/integration/test_web_v2.py -q
node --test tests/web/test_listing_filter_panel.mjs
node --test tests/web/test_listing_map_controller.mjs
git diff --check
~~~

Expected: all selected tests pass with no whitespace errors.

- [ ] **Step 5: Browser verification**

Use the local app with a valid NAVER client ID. Verify:

1. Basic filters and the result summary form one panel above the map.
2. On an enlarged map, apply a transaction or price filter and verify tiles remain visible at the same center and zoom.
3. Once the filter response settles, markers and the below-map collection reflect the filter without a full-screen overlay.
4. At mobile width, controls wrap without overlap and the detailed-filter drawer opens from its single trigger.

- [ ] **Step 6: Run complete regression verification**

~~~powershell
$taskPythonPath = Join-Path (Get-Location) 'src'; $env:PYTHONPATH = $taskPythonPath; python -m pytest -q
node --test tests/web/test_listing_filter_panel.mjs
node --test tests/web/test_listing_map_controller.mjs
git diff --check
~~~

Expected: full Python suite and both JavaScript suites pass.

- [ ] **Step 7: Commit final verification fixes, if any**

~~~powershell
git add -- src/realty_radar/web/templates/listings src/realty_radar/web/static/listing-map.js tests/integration/test_listing_map_ui.py tests/integration/test_listing_detail_ui.py tests/integration/test_web_v2.py tests/web/test_listing_filter_panel.mjs tests/web/test_listing_map_controller.mjs
git commit -m "test: cover stable map filter refresh"
~~~
