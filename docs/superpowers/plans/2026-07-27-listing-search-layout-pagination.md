# Listing Search Layout and Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the listing search layout wider and easier to scan, show 20 results per keyset-backed page, and keep result controls available while scrolling.

**Architecture:** Retain the existing signed keyset cursor so filtering stays bounded and does not introduce a full `COUNT`/`OFFSET` query. The search response exposes a previous cursor alongside the existing next cursor, and the result partial renders a 20-result previous/next pager. Template-only layout changes keep the profile sidebar at a narrower left column and use semantic, coloured information chips for repeated property facts.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, HTMX, Alpine.js, Tailwind CSS, pytest.

## Global Constraints

- Keep `page_size` fixed at 20 in the search form and pager links.
- Do not add a full result-count query or SQL `OFFSET`; retain signed keyset cursors.
- Treat a grouped result page as 20 complexes, matching the existing grouping search semantics.
- Preserve query parameters and HTMX replacement behavior when switching pages, filters, or sorting.
- The fixed result-control bar must remain below the application header and above result cards.

---

### Task 1: Add bidirectional keyset page metadata

**Files:**
- Modify: `src/realty_radar/domain/listing/models.py`
- Modify: `src/realty_radar/application/listing_search_service.py`
- Test: `tests/integration/test_listing_detail_ui.py`

**Interfaces:**
- Produces: `SearchResult.previous_cursor: str | None`.
- Produces: `ListingSearchService.search_listings()` results with a cursor for the preceding 20-row/complex page when the request has a current cursor.

- [ ] **Step 1: Write the failing test**

```python
def test_search_result_exposes_previous_page_cursor_for_a_cursor_page():
    first = service.search_listings(ListingSearchFilter(page_size=20))
    second = service.search_listings(ListingSearchFilter(page_size=20, cursor=first.next_cursor))

    assert second.previous_cursor is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/test_listing_detail_ui.py::test_search_result_exposes_previous_page_cursor_for_a_cursor_page -q`

Expected: FAIL because `SearchResult` does not expose `previous_cursor`.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(slots=True)
class SearchResult:
    items: list[Any]
    next_cursor: str | None
    has_more: bool
    previous_cursor: str | None = None
```

Build the prior-page cursor from the first selected row or complex by querying the immediately preceding keyset boundary, then encode the row before that boundary. Keep eligibility scanning on the existing evaluator path.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/integration/test_listing_detail_ui.py::test_search_result_exposes_previous_page_cursor_for_a_cursor_page -q`

Expected: PASS.

### Task 2: Render fixed 20-result pager and result controls

**Files:**
- Modify: `src/realty_radar/web/routes/home.py`
- Modify: `src/realty_radar/web/templates/listings/_listing_cards.html`
- Modify: `src/realty_radar/web/templates/listings/list_partial.html`
- Test: `tests/integration/test_listing_detail_ui.py`

**Interfaces:**
- Consumes: `SearchResult.previous_cursor`, `next_cursor`, and `has_more`.
- Produces: previous/next page links that retain filters and replace `#search-results` through HTMX.

- [ ] **Step 1: Write the failing test**

```python
assert 'data-result-controls' in response.text
assert '이전 페이지' in response.text
assert '다음 페이지' in response.text
assert '페이지당 20개' in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/test_listing_detail_ui.py -q`

Expected: FAIL because the result partial still has only the `더 보기` control.

- [ ] **Step 3: Write minimal implementation**

```jinja2
<div data-result-controls class="sticky top-20 z-30 ...">
  <a href="#listing-search-form">필터 변경</a>
  <select data-result-sort form="listing-search-form" name="sort_by">...</select>
</div>
```

Construct previous and next URLs in `home.py` using the preserved request URL and each cursor. Replace the append-only pager with a 20-item previous/next pager; omit unavailable directions rather than emitting inactive links.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/integration/test_listing_detail_ui.py -q`

Expected: PASS.

### Task 3: Widen the search pane and improve property-card scanning

**Files:**
- Modify: `src/realty_radar/web/templates/listings/index.html`
- Modify: `src/realty_radar/web/templates/listings/_listing_cards.html`
- Test: `tests/integration/test_listing_detail_ui.py`

**Interfaces:**
- Produces: a `15rem` sidebar and a full `max-w-7xl` centred search grid.
- Produces: coloured, no-wrap fact chips for area, household count, construction year, price, and key listing facts.

- [ ] **Step 1: Write the failing test**

```python
assert 'max-w-7xl' in response.text
assert 'lg:grid-cols-[15rem_minmax(0,1fr)]' in response.text
assert 'text-sky-300' in response.text
assert 'text-amber-300' in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/test_listing_detail_ui.py -q`

Expected: FAIL because the sidebar is 17rem and facts are uncoloured inline text.

- [ ] **Step 3: Write minimal implementation**

```jinja2
<div class="mx-auto grid w-full max-w-7xl gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
```

Render compact `inline-flex whitespace-nowrap` fact chips. Use sky for household counts, amber for construction years, emerald for loan availability, and indigo for price/area. Keep long address and complex name text truncatable while allowing the card’s main content column to grow.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/integration/test_listing_detail_ui.py -q`

Expected: PASS.

### Task 4: Verify the complete search experience

**Files:**
- Test: `tests/integration/test_listing_detail_ui.py`

- [ ] **Step 1: Run focused integration tests**

Run: `python -m pytest tests/integration/test_listing_detail_ui.py -q`

Expected: PASS.

- [ ] **Step 2: Run full test suite and compilation**

Run: `python -m pytest -q; python -m compileall -q src tests`

Expected: all tests pass and compilation exits with status 0.

- [ ] **Step 3: Inspect patch scope**

Run: `git diff --check; git diff -- src/realty_radar/application/listing_search_service.py src/realty_radar/domain/listing/models.py src/realty_radar/web/routes/home.py src/realty_radar/web/templates/listings/index.html src/realty_radar/web/templates/listings/list_partial.html src/realty_radar/web/templates/listings/_listing_cards.html tests/integration/test_listing_detail_ui.py`

Expected: only the planned pagination and readability changes are present; any pre-existing whitespace issue is reported separately.
