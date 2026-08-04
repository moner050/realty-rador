# Map Query Aggregation Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return equivalent map counts and overlays without transferring every matching listing row to Python, and prove normal-filter p95 is at or below one second before declaring the map ready.

**Architecture:** Keep `ListingSearchService.map_candidate_rows()` as the single source of filter predicates. For ordinary SQL-only filters, project those candidates into a narrow CTE, count distinct complexes, then join verified `ComplexCurrent` rows and aggregate prices/listing counts in MySQL. Keep policy filters that require Python loan/purchase evaluation on the existing stream path.

**Tech Stack:** Python 3, SQLAlchemy, MySQL 8, SQLite unit tests, pytest, existing NAVER map UI and Node controller tests.

## Global Constraints

- Preserve current map candidate semantics, including the existing verified-coordinate map-bounds behavior.
- `matching_complex_count`, `mapped_complex_count`, `unmapped_complex_count`, per-complex listing count, min/max price, and cluster inputs must match the previous stream result for ordinary filters.
- Page requests remain read-only: no Naver geocoder, commit, migration, index, cache, coordinate table, or schema change.
- `only_eligible_loans` and `only_purchase_affordable` retain their existing Python-policy candidate stream.
- Do not add an index unless measured post-change normal-filter p95 exceeds one second and `EXPLAIN FORMAT=JSON` identifies a focused bottleneck.
- Use `python -m pytest`, never bare `pytest`; do not print `.env` values or database URLs.

---

### Task 1: Replace ordinary map row streaming with SQL complex aggregates

**Files:**
- Modify: `src/realty_radar/application/listing_map_service.py:139-205`
- Test: `tests/unit/test_listing_map_service.py`
- Test: `tests/integration/test_listing_search_v2.py`

**Interfaces:**
- Consumes: `ListingSearchService.map_candidate_rows(filters, applicant) -> (statement, row_matcher)`.
- Produces: unchanged `ListingMapService.build_viewport(filters, applicant, zoom) -> ListingMapViewport`.
- Adds private helpers only: `_build_sql_viewport(statement, filters, zoom)` and `_build_stream_viewport(filters, applicant, zoom)`.

- [ ] **Step 1: Write failing equivalence and projection tests**

Add a fixture with two verified complexes (multiple listings/different prices), one pending-coordinate complex, and one out-of-bounds verified complex. Add tests equivalent to:

```python
def test_sql_map_viewport_matches_reference_stream_for_ordinary_filters():
    session = _session()
    session.add_all([
        _complex(1, latitude=Decimal("37.5000000"), longitude=Decimal("126.8000000"), status=GEOCODE_STATUS_OK),
        _complex(2, latitude=Decimal("37.5100000"), longitude=Decimal("126.8100000"), status=GEOCODE_STATUS_OK),
        _complex(3),
    _listing(1, 1, 510_000_000), _listing(2, 1, 500_000_000),
        _listing(3, 2, 600_000_000), _listing(4, 3, 700_000_000),
    ])
    session.commit()
    service = ListingMapService(session)
    expected = service._build_stream_viewport(ListingSearchFilter(), None, zoom=14)

    assert service.build_viewport(ListingSearchFilter(), None, zoom=14) == expected


def test_ordinary_map_viewport_does_not_stream_listing_entities(monkeypatch):
    session = _session()
    session.add_all([
        _complex(1, latitude=Decimal("37.5000000"), longitude=Decimal("126.8000000"), status=GEOCODE_STATUS_OK),
        _complex(2, latitude=Decimal("37.5100000"), longitude=Decimal("126.8100000"), status=GEOCODE_STATUS_OK),
        _complex(3),
        _listing(1, 1, 510_000_000), _listing(2, 2, 600_000_000), _listing(3, 3, 700_000_000),
    ])
    session.commit()
    monkeypatch.setattr(
        ListingSearchService,
        "stream_map_matching_rows",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not stream entities")),
    )

    assert ListingMapService(session).build_viewport(ListingSearchFilter(), None, zoom=14).matching_complex_count == 3
```

Attach a SQLAlchemy `before_cursor_execute` listener in a separate test and assert normal-map SQL does not select `listing_current.description` or other full-entity-only columns. Cover the existing bounds example and assert its current counts remain `(1, 1, 0)`. Run the new tests and confirm the stream guard fails before implementation.

Set one complex's later listing to a deliberately different `complex_name` and `address`; assert the viewport retains the text from its lowest-`article_id` listing, exactly as the former article-ordered stream did.

- [ ] **Step 2: Build a narrow candidate CTE and SQL aggregates**

Call `ListingSearchService(self.session).map_candidate_rows(filters, applicant)` once in `build_viewport`. For ordinary filters, pass the statement to `_build_sql_viewport`. It must retain the original FROM/JOIN/WHERE clauses while projecting only needed columns:

```python
candidates = statement.with_only_columns(
    ListingCurrent.complex_id,
    ListingCurrent.article_id,
    ListingCurrent.complex_name,
    ListingCurrent.address,
    ListingCurrent.primary_price,
    maintain_column_froms=True,
).cte("map_candidates")

matching_complex_count = self.session.scalar(
    select(func.count(func.distinct(candidates.c.complex_id)))
) or 0
```

Build a grouped CTE and a first-article text CTE from that same candidate CTE. Do not use `MIN(complex_name)` or `MIN(address)`: those can change existing visible text when listings in one complex disagree.

```python
aggregates = (
    select(
        candidates.c.complex_id,
        func.min(candidates.c.article_id).label("first_article_id"),
        func.count().label("listing_count"),
        func.min(candidates.c.primary_price).label("min_price"),
        func.max(candidates.c.primary_price).label("max_price"),
    )
    .group_by(candidates.c.complex_id)
    .cte("map_complex_aggregates")
)
first_text = (
    select(
        candidates.c.complex_id,
        candidates.c.complex_name,
        candidates.c.address,
    )
    .join(
        aggregates,
        and_(
            aggregates.c.complex_id == candidates.c.complex_id,
            aggregates.c.first_article_id == candidates.c.article_id,
        ),
    )
    .cte("map_first_listing_text")
)

aggregate_statement = (
    select(
        aggregates.c.complex_id,
        first_text.c.complex_name,
        first_text.c.address,
        ComplexCurrent.latitude,
        ComplexCurrent.longitude,
        aggregates.c.listing_count,
        aggregates.c.min_price,
        aggregates.c.max_price,
    )
    .join(first_text, first_text.c.complex_id == aggregates.c.complex_id)
    .join(ComplexCurrent, ComplexCurrent.complex_id == aggregates.c.complex_id)
    .where(
        ComplexCurrent.geocode_status == GEOCODE_STATUS_OK,
        ComplexCurrent.latitude.is_not(None),
        ComplexCurrent.longitude.is_not(None),
    )
    .order_by(aggregates.c.complex_id)
)
```

Turn only aggregate rows into `ListingMapMarker` values, call the existing `cluster_map_complexes`, and compute `unmapped_complex_count = matching_complex_count - len(complexes)`. Preserve `ListingMapViewport.bounds`. Do not alter routes, map JavaScript, or coordinate state.

- [ ] **Step 3: Preserve Python-policy fallback explicitly**

Move the existing Python summary loop and coordinate `IN` lookup into `_build_stream_viewport`. Invoke it only for `filters.only_eligible_loans` or `filters.only_purchase_affordable`. Add a test that spies on `stream_map_matching_rows` for one policy flag and proves ordinary filters do not use it.

- [ ] **Step 4: Verify Task 1**

Run:

```powershell
python -m pytest tests/unit/test_listing_map_service.py tests/integration/test_listing_search_v2.py -q
python -m pytest -q
git diff --check
```

Expected: all tests pass; normal-map SQL selects CTE/aggregate columns only; policy paths retain prior semantics.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- src/realty_radar/application/listing_map_service.py tests/unit/test_listing_map_service.py tests/integration/test_listing_search_v2.py
git commit -m "perf: aggregate map complexes in SQL"
```

### Task 2: Add bounded, repeatable map performance evidence command

**Files:**
- Create: `scripts/benchmark_map_viewport.py`
- Test: `tests/unit/test_listing_map_service.py`

**Interfaces:**
- Consumes: configured app database, `ListingSearchFilter()`, and `ListingMapService.build_viewport`.
- Produces: credential-free JSON with run count, min/p50/p95/max latency, map counts, and `EXPLAIN FORMAT=JSON` output.

- [ ] **Step 1: Write the failing percentile test**

Add this module loader to the existing unit test:

```python
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_benchmark_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_map_viewport.py"
    spec = spec_from_file_location("benchmark_map_viewport", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
```

Then add:

```python
def test_map_benchmark_p95_uses_nearest_rank():
    module = _load_benchmark_module()
    assert module.nearest_rank_p95([1.0, 2.0, 3.0, 4.0, 5.0]) == 5.0
```

Run it and confirm failure because the script/helper does not exist.

- [ ] **Step 2: Implement the bounded command**

Create `scripts/benchmark_map_viewport.py` with `--runs` (default `30`, positive) and `--timeout-seconds` (default `10`, positive). It must:

1. open app-configured sessions without printing the database URL;
2. perform one warm-up and exactly `--runs` fresh-session `build_viewport(ListingSearchFilter(), None, 7)` calls;
3. calculate nearest-rank p95;
4. capture SELECT statements and bound parameters during one optimized call via `before_cursor_execute`, then replay them as `EXPLAIN FORMAT=JSON` with the same parameters;
5. set a bounded database read timeout and emit a structured timeout/error record without retrying;
6. make no write, schema, Naver, or `EXPLAIN ANALYZE` call.

- [ ] **Step 3: Verify Task 2**

```powershell
python -m pytest tests/unit/test_listing_map_service.py -q
python scripts/benchmark_map_viewport.py --runs 1 --timeout-seconds 10
```

Expected: the test passes and the command emits one JSON evidence record or an explicit bounded connection/query error without secrets.

- [ ] **Step 4: Commit Task 2**

```powershell
git add -- scripts/benchmark_map_viewport.py tests/unit/test_listing_map_service.py
git commit -m "test: add bounded map viewport benchmark"
```

### Task 3: Measure optimized path and complete map verification

**Files:**
- Modify: Task 1-2 files if a direct verification failure requires a focused correction; additionally `src/realty_radar/web/static/listing-map.js` only for the user-approved HTMX 1.9 card-swap remediation below.
- Test: `tests/unit/test_listing_map_service.py`
- Test: `tests/integration/test_listing_search_v2.py`
- Test: `tests/integration/test_listing_map_ui.py`
- Test: `tests/web/test_listing_map_controller.mjs`

**Interfaces:**
- Consumes: optimized map service, benchmark command, configured MySQL, and existing map/card endpoints.
- Produces: evidence that normal map performance meets the gate or an explicit blocker for a separately approved index/read-model design.

- [ ] **Step 1: Run exact regression checks**

```powershell
git diff --check -- src/realty_radar/application/listing_map_service.py src/realty_radar/application/listing_search_service.py src/realty_radar/web/routes/home.py src/realty_radar/web/static/listing-map.js
python -m pytest tests/unit/test_listing_map_service.py tests/integration/test_listing_search_v2.py tests/integration/test_listing_map_ui.py -q
node --test tests/web/test_listing_map_controller.mjs
```

- [ ] **Step 2: Capture actual optimized DB evidence once**

```powershell
python scripts/benchmark_map_viewport.py --runs 30 --timeout-seconds 10
```

Record JSON output in the task report. If p95 is at most 1,000ms, record plan summaries and continue. If it times out or p95 exceeds 1,000ms, stop: do not add an index, cache, or read model; report the statement/plan evidence needed for a new approved design.

- [ ] **Step 3: Browser smoke test only after p95 passes**

Start the local worktree app in a hidden background process. Use `agent-browser` to verify home loading, successful map-data response, reconciled counts, and zoom/drag updates limited to overlays and `#listing-collection`; check content, overlay errors, console, and a mobile viewport. Close the browser and stop only this task's process. If p95 failed, record that a long live interaction is blocked rather than treating it as passed.

- [ ] **Step 4: User-approved HTMX 1.9 card-swap remediation when browser evidence requires it**

The live diagnosis established that `base.html` loads HTMX 1.9.10 and its `window.htmx` object has no public `swap` function. Therefore successful map-card responses must not depend on `window.htmx.swap`.

First add a controller regression that sets `window.htmx = {}`, resolves a valid cards response, and asserts that the old `#listing-collection` element is replaced by a new element from the response HTML while the map root reference is unchanged. Also assert that a stale response cannot replace the current collection and that malformed HTML without `#listing-collection` keeps existing cards visible and sets the existing map-card error message. Run `node --test tests/web/test_listing_map_controller.mjs` and confirm the valid-response test fails because the current code silently skips the response.

Then replace the HTMX-only block in `requestCards` with a small DOM helper. Parse the response in a detached `template`, select exactly one `#listing-collection`, and call `target.replaceWith(replacement)`. Return without changing current cards when the response has no collection, and let the caller show the existing map-card error status. Do not replace `#search-results`, recreate the map, change history, or upgrade HTMX.

Update the Node fake DOM only as needed to exercise this actual DOM helper; it must not inject a fake `htmx.swap`. Add an integration assertion that the map-cards fragment still has a single `#listing-collection` root. Run a single hidden-server `agent-browser` drag at valid zoom: it must show changed-bounds map-data/map-cards 200, unchanged map-root reference, replaced collection reference, and visible cards. Close browser and stop only this task server.

- [ ] **Step 5: Final suites and direct-fix commit only**

```powershell
python -m pytest -q
node --test tests/web/test_listing_map_controller.mjs
```

Make no empty commit. If this user-approved direct verification requires a fix:

```powershell
git add -- src/realty_radar/web/static/listing-map.js tests/web/test_listing_map_controller.mjs tests/integration/test_listing_map_ui.py
git commit -m "fix: replace map cards without HTMX swap"
```

## Plan Self-Review

- Spec coverage: Task 1 removes the proven full-row ORM transfer while retaining filters and policy fallbacks; Task 2 creates durable bounded DB evidence; Task 3 enforces the one-second gate before browser readiness.
- No placeholders: every task has concrete files, helper names, query shapes, commands, thresholds, and stop conditions.
- Type consistency: `build_viewport` and `ListingMapViewport` stay public and unchanged; aggregate/stream helpers are private to `ListingMapService`; the benchmark calls the same public method as the route.
