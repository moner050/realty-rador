# Map-First Search Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the map the primary apartment-search workspace while keeping compact search inputs, detailed filters, applied conditions, and map-area listings readable and directly usable.

**Architecture:** Keep `ListingSearchFilter`, search routes, HTMX targets, and map endpoints unchanged. Reorganize the existing single form and `#search-results` so compact controls precede the map, detailed controls appear in a right-side drawer, and cards follow the map. Add a small client controller only for drawer state and condition-chip removal; retain existing slider, tab, HTMX, and map logic.

**Tech Stack:** Jinja2 templates, Tailwind utility classes, vanilla JavaScript, HTMX, NAVER Maps V3, FastAPI integration tests, Node built-in test runner.

## Global Constraints

- Preserve all `ListingSearchFilter` names, saved-filter persistence, URL serialization, SQL predicates, and map endpoint responses.
- Preserve map's 1.5-second post-gesture refresh, abort/stale-response rules, hierarchical aggregation, card replacement, focus, and complex modal.
- Keep `map_*` bounds nonpersistent: map movement must not save a filter or push a URL.
- Use one `#listing-search-form`; do not duplicate controls or add a second parser.
- Use `python -m pytest`, not bare `pytest`.
- Do not add migrations, indexes, external APIs, a view switcher, or a left fixed filter column.

---

## File Structure

- Modify `src/realty_radar/web/templates/listings/index.html`: compact map-adjacent toolbar, right detailed-filter drawer, actionable condition chips within the existing form.
- Modify `src/realty_radar/web/templates/listings/_map_sidebar.html`: concise map header with a filter trigger while retaining all map data attributes.
- Modify `src/realty_radar/web/templates/listings/_listing_collection.html`: map-area listing heading and concise refresh context while retaining card/pager IDs.
- Create `src/realty_radar/web/static/listing-filter-panel.js`: drawer state and named-control clearing before form submission.
- Modify `src/realty_radar/web/templates/base.html`: load the new controller.
- Modify `tests/integration/test_listing_map_ui.py`: map-first layout/accessibility contracts.
- Create `tests/web/test_listing_filter_panel.mjs`: drawer and condition-chip interaction tests.

## Task 1: Rendered Map-First Workspace Contract

**Files:**
- Modify: `tests/integration/test_listing_map_ui.py`
- Modify: `src/realty_radar/web/templates/listings/index.html`
- Modify: `src/realty_radar/web/templates/listings/_map_sidebar.html`
- Modify: `src/realty_radar/web/templates/listings/_listing_collection.html`

**Interfaces:**
- Consumes: rendered filter context, `data-listing-map-root`, map URL attributes, and `#listing-collection`.
- Produces: `data-search-workspace` with `#listing-search-form`, `data-search-toolbar`, `data-applied-filter-summary`, `data-listing-map-root`, and `#listing-collection` in visual order. The map header has `data-map-filter-trigger`.

- [ ] **Step 1: Write the failing template contract test**

Add this test beside `test_search_result_exposes_public_map_urls_without_marker_payload`:

```python
def test_search_result_renders_one_map_first_workspace(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.text.count('id="listing-search-form"') == 1
    assert 'data-search-workspace' in response.text
    assert 'data-search-toolbar' in response.text
    assert 'data-applied-filter-summary' in response.text
    assert 'data-map-filter-trigger' in response.text
    assert response.text.index('data-search-toolbar') < response.text.index('data-listing-map-root')
    assert response.text.index('data-listing-map-root') < response.text.index('id="listing-collection"')
    assert 'data-map-data-url=' in response.text
    assert 'data-map-cards-url=' in response.text
    assert 'data-map-complex-url-template=' in response.text
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest tests/integration/test_listing_map_ui.py::test_search_result_renders_one_map_first_workspace -q`

Expected: FAIL because workspace and trigger attributes are absent.

- [ ] **Step 3: Implement the minimal template layout**

Keep all current named inputs, slider/tab attributes, and form HTMX attributes. Change only surrounding markup to this order:

```html
<main data-search-workspace class="mx-auto w-full max-w-7xl space-y-4">
  <form id="listing-search-form" ...>
    <section data-search-toolbar>...existing compact controls...</section>
    <section data-applied-filter-summary>...existing condition summary...</section>
    <dialog id="detailed-filter-modal" data-filter-panel>...existing detailed controls...</dialog>
  </form>
  <div id="search-results">...result toolbar, map, listing collection...</div>
</main>
```

In `_map_sidebar.html`, add:

```html
<button type="button" data-map-filter-trigger aria-controls="detailed-filter-modal" aria-expanded="false">
  상세 필터
</button>
```

Do not rename `data-listing-map-root`, map URL/count attributes, `#listing-collection`, `#listing-cards`, or `#listing-pager`.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python -m pytest tests/integration/test_listing_map_ui.py::test_search_result_renders_one_map_first_workspace -q`

Expected: PASS.

- [ ] **Step 5: Run adjacent regression tests**

Run: `python -m pytest tests/integration/test_listing_map_ui.py -q`

Expected: PASS; map URL attributes, map-card fragment targeting, and map-bounds nonpersistence remain intact.

- [ ] **Step 6: Commit the rendered layout contract**

```bash
git add tests/integration/test_listing_map_ui.py src/realty_radar/web/templates/listings/index.html src/realty_radar/web/templates/listings/_map_sidebar.html src/realty_radar/web/templates/listings/_listing_collection.html
git commit -m "feat: arrange map-first search workspace"
```

## Task 2: Detailed Filter Drawer and Applied-Condition Controls

**Files:**
- Create: `tests/web/test_listing_filter_panel.mjs`
- Create: `src/realty_radar/web/static/listing-filter-panel.js`
- Modify: `src/realty_radar/web/templates/base.html`
- Modify: `src/realty_radar/web/templates/listings/index.html`

**Interfaces:**
- Consumes: `#listing-search-form`, `#detailed-filter-modal`, `[data-map-filter-trigger]`, `[data-filter-panel-open]`, `[data-filter-panel-apply]`, and `[data-applied-filter-clear]`.
- Produces: `window.RealtyRadarListingFilterPanel = { mount }`; clear chips declare source controls with `data-filter-clear-names="name1,name2"`.

- [ ] **Step 1: Write the failing browser-controller tests**

Create `tests/web/test_listing_filter_panel.mjs` with a fake document, form, dialog, and named controls:

```javascript
test('filter triggers open the drawer and announce expanded state', () => {
  const state = loadFilterPanel();
  state.click(state.mapTrigger);
  assert.equal(state.modal.showModalCalls, 1);
  assert.equal(state.mapTrigger.getAttribute('aria-expanded'), 'true');
});

test('apply submits the existing form once and closes the drawer', () => {
  const state = loadFilterPanel();
  state.modal.open = true;
  state.click(state.applyButton);
  assert.equal(state.form.requestSubmitCalls, 1);
  assert.equal(state.modal.closeCalls, 1);
});

test('applied-condition clear resets matching controls before one submit', () => {
  const state = loadFilterPanel({ controls: { min_price_eok: '4', max_price_eok: '7' } });
  state.click(state.clearPriceChip);
  assert.equal(state.controls.min_price_eok.value, '');
  assert.equal(state.controls.max_price_eok.value, '');
  assert.equal(state.form.requestSubmitCalls, 1);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/web/test_listing_filter_panel.mjs`

Expected: FAIL because `listing-filter-panel.js` does not exist.

- [ ] **Step 3: Implement the small drawer controller**

Create `listing-filter-panel.js` with this required behavior:

```javascript
function namedControls(form, names) {
  return names.flatMap((name) => Array.from(form.querySelectorAll('[name="' + escapeName(name) + '"]')));
}

function resetControl(control) {
  if (control.type === 'checkbox' || control.type === 'radio') control.checked = false;
  else control.value = '';
}

function mount(source = document) {
  const form = source.querySelector('#listing-search-form');
  const panel = source.querySelector('#detailed-filter-modal');
  if (!form || !panel || panel.dataset.filterPanelMounted === 'true') return;
  panel.dataset.filterPanelMounted = 'true';
  source.addEventListener('click', (event) => {
    const opener = event.target.closest('[data-map-filter-trigger], [data-filter-panel-open]');
    if (opener) { panel.showModal(); opener.setAttribute('aria-expanded', 'true'); return; }
    if (event.target.closest('[data-filter-panel-apply]')) { form.requestSubmit(); panel.close(); return; }
    const chip = event.target.closest('[data-applied-filter-clear]');
    if (chip) { namedControls(form, chip.dataset.filterClearNames.split(',')).forEach(resetControl); form.requestSubmit(); }
  });
  panel.addEventListener('close', () => source.querySelectorAll('[data-map-filter-trigger], [data-filter-panel-open]').forEach(
    (button) => button.setAttribute('aria-expanded', 'false'),
  ));
}
```

Use a fallback that returns the name unchanged when `CSS.escape` is unavailable. The controller must not create map requests, alter `map_*` fields, or bind duplicate listeners.

In `base.html`, add `<script src="/static/listing-filter-panel.js" defer></script>`. In `index.html`, mark the existing opener with `data-filter-panel-open`, the existing apply button with `data-filter-panel-apply`, and remove their old duplicated click listeners. Render clearable compact chips as buttons:

```html
<button type="button" data-applied-filter-clear data-filter-clear-names="complex_keyword">
  단지명: {{ filters.complex_keyword }} ×
</button>
<button type="button" data-applied-filter-clear data-filter-clear-names="min_price_eok,max_price_eok">
  가격: ... ×
</button>
```

Use the existing region-clear control for selected regions. Keep all other detailed-condition chips visible even when informational.

- [ ] **Step 4: Run the controller tests to verify they pass**

Run: `node --test tests/web/test_listing_filter_panel.mjs`

Expected: PASS.

- [ ] **Step 5: Run map controller regression tests**

Run: `node --test tests/web/test_listing_map_controller.mjs`

Expected: PASS; drawer events do not affect map refresh, cards, marker modal, or listener cleanup.

- [ ] **Step 6: Commit the drawer controller**

```bash
git add tests/web/test_listing_filter_panel.mjs src/realty_radar/web/static/listing-filter-panel.js src/realty_radar/web/templates/base.html src/realty_radar/web/templates/listings/index.html
git commit -m "feat: add map search filter drawer controls"
```

## Task 3: Accessibility, Responsive Readability, and Final Verification

**Files:**
- Modify: `tests/integration/test_listing_map_ui.py`
- Modify: `src/realty_radar/web/templates/listings/index.html`
- Modify: `src/realty_radar/web/templates/listings/_map_sidebar.html`
- Modify: `src/realty_radar/web/templates/listings/_listing_collection.html`

**Interfaces:**
- Consumes: Task 1 workspace attributes and Task 2 drawer controls.
- Produces: an accessible drawer with `aria-expanded`, scrollable body, and visible `적용` / `전체 초기화` footer on narrow screens.

- [ ] **Step 1: Write the failing accessibility markup test**

```python
def test_map_first_workspace_exposes_accessible_filter_drawer(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'id="detailed-filter-modal"' in response.text
    assert 'data-filter-panel' in response.text
    assert 'data-filter-panel-apply' in response.text
    assert 'aria-controls="detailed-filter-modal"' in response.text
    assert 'aria-expanded="false"' in response.text
    assert 'data-map-loading hidden' in response.text
    assert 'data-card-loading hidden' in response.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/integration/test_listing_map_ui.py::test_map_first_workspace_exposes_accessible_filter_drawer -q`

Expected: FAIL because the accessible drawer contract is incomplete.

- [ ] **Step 3: Implement responsive and accessible refinements**

Use existing Tailwind utilities:

```html
<dialog id="detailed-filter-modal" data-filter-panel class="fixed inset-y-0 right-0 m-0 h-dvh w-full max-w-[28rem] ...">
  <div class="flex h-full flex-col">
    <header class="shrink-0 ...">...</header>
    <div class="min-h-0 flex-1 overflow-y-auto ...">...</div>
    <footer class="shrink-0 border-t ...">
      <button type="button" data-filter-panel-apply>적용</button>
      <a href="/">전체 초기화</a>
    </footer>
  </div>
</dialog>
```

At compact widths, wrap the toolbar into two rows, keep controls at least `min-h-10`, allow chips to wrap without page overflow, and fill the narrow screen with the drawer. Preserve the existing `data-map-loading` and `data-card-loading` indicators; do not add a map overlay.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python -m pytest tests/integration/test_listing_map_ui.py::test_map_first_workspace_exposes_accessible_filter_drawer -q`

Expected: PASS.

- [ ] **Step 5: Run complete automated verification**

```bash
python -m pytest -q
node --test tests/web/test_listing_filter_panel.mjs
node --test tests/web/test_listing_map_controller.mjs
git diff --check
```

Expected: all tests pass and no whitespace errors are reported.

- [ ] **Step 6: Manually verify the live page on a temporary port**

Do not stop or replace a user-owned `localhost:8000` process. Check desktop light/dark and mobile widths:

1. Compact controls, applied conditions, map, and cards appear in order.
2. Either filter trigger opens the drawer; focus reaches close/apply; apply closes it; unsubmitted values persist.
3. Map movement still waits 1.5 seconds and changes neither URL nor saved filters.
4. The mobile drawer scrolls while its footer remains visible.
5. Helper text, chips, and controls maintain readable contrast.

- [ ] **Step 7: Commit verification refinements**

```bash
git add tests/integration/test_listing_map_ui.py src/realty_radar/web/templates/listings/index.html src/realty_radar/web/templates/listings/_map_sidebar.html src/realty_radar/web/templates/listings/_listing_collection.html
git commit -m "fix: refine map search workspace accessibility"
```

## Plan Self-Review

- Spec coverage: Task 1 implements the map-first layout and preserves map/data contracts. Task 2 adds drawer and clearable compact conditions through the existing form. Task 3 covers accessibility, responsive layout, loading continuity, and browser checks.
- Scope: no route, schema, query, map API, or migration task is present.
- Interface consistency: every attribute consumed by `listing-filter-panel.js` is defined in Task 2; existing map `data-map-*` attributes remain owned by `listing-map.js`.
- Placeholder check: each production change has a failing test and exact verification command.
