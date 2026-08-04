# Listing Detail Preload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely pre-enrich active listings with source-provided parking, management-fee, move-in, and subway-walk data, then make each field’s known, pending, or unavailable state visible in cards.

**Architecture:** Extend the existing `MortgageEnrichmentRunner` with short-lived database claims so the current crawl-priority run and a daily catchup worker cannot fetch the same pending article. A daily bounded worker reuses the existing authenticated detail endpoint and writes the existing detail fields; cards distinguish unqueried from queried-but-not-provided values without inventing data.

**Tech Stack:** Python 3, SQLAlchemy/Alembic, FastAPI/Jinja2, existing SITE_A browser client, APScheduler, pytest.

## Global Constraints

- The source of parking, management fee, move-in, and nearest subway-walk fields remains the existing SITE_A detail endpoint, not NAVER Maps APIs.
- Process only active listings with `detail_checked_at IS NULL`; do not recrawl rows already checked in this scope.
- A candidate claim expires after 15 minutes. A successful detail write clears the claim and sets `detail_checked_at`; a failed fetch clears the claim and leaves `detail_checked_at` null.
- Current crawl jobs retain their 100-detail priority enrichment. Daily catchup is capped at 5,000 listings, batch size 100, concurrency 2, and one scheduler instance.
- Detail changes continue to create append-only `ListingHistory` events using a real completed crawl job ID; do not introduce a fake job ID.
- Card copy is exact: no fetch yet is `확인 대기`; fetched but missing in the source is `원본 미제공`; numeric values retain their existing units.
- Reuse existing authenticated browser/bootstrap behavior and fail closed before browser actions if it is unavailable.
- Use `python -m pytest`, not bare `pytest`, and preserve unrelated dirty worktree changes.

## User ruling — 2026-08-04

The Goal and Global Constraints govern the earlier three-field Task 3 detail. Include `move_in_date` in the same truthful card-state treatment as parking, management fee, and nearest subway-walk data: render `확인 대기` before a detail fetch, `원본 미제공` after a completed fetch without a value, and preserve the existing populated move-in format. Apply this in both the visible tag row and expanded detail grid, add rendered-card coverage for all three move-in states, and include non-null move-in coverage in Task 4 reporting.

---

## File Structure

- `migrations/versions/2026_08_04_0010_detail_enrichment_claim.py` — adds claim token and time to `listing_current`.
- `src/realty_radar/infrastructure/database/models/v2.py` — models `detail_claim_token` and `detail_claimed_at`.
- `src/realty_radar/application/mortgage_enrichment_service.py` — atomically claims batches, releases failures, and writes only its own claims.
- `scripts/enrich_listing_details.py` — manual bounded catchup command using an explicit completed job ID.
- `src/realty_radar/scheduler/schedules.py` — finds the latest completed crawl job and launches one bounded daily catchup.
- `src/realty_radar/scheduler/scheduler.py` — registers the non-overlapping daily detail job.
- `src/realty_radar/web/templates/listings/_listing_cards.html` — renders pending versus source-unavailable detail values.
- `tests/integration/test_mortgage_enrichment.py` — existing enrichment behavior plus detail failure and success state transitions.
- `tests/integration/test_detail_enrichment_claims.py` — migration/model/claim concurrency behavior.
- `tests/unit/test_listing_detail_preload_script.py` — script argument contract.
- `tests/unit/test_scheduler.py` — bounded scheduled catchup contract.
- `tests/integration/test_listing_detail_ui.py` — rendered card-state labels.

### Task 1: Add durable detail-enrichment claims

**Files:**
- Create: `migrations/versions/2026_08_04_0010_detail_enrichment_claim.py`
- Modify: `src/realty_radar/infrastructure/database/models/v2.py`
- Modify: `src/realty_radar/application/mortgage_enrichment_service.py`
- Create: `tests/integration/test_detail_enrichment_claims.py`
- Modify: `tests/integration/test_mortgage_enrichment.py`

**Interfaces:**
- Consumes: active `ListingCurrent` rows with `detail_checked_at IS NULL`.
- Produces: `MortgageEnrichmentRunner._claim_batch(batch_size, priority_job_id=None) -> list[tuple[int, int]]`, using one runner-specific claim token.

- [ ] **Step 1: Write failing claim lifecycle tests**

```python
def test_two_runners_claim_disjoint_pending_articles(session_factory):
    _seed_pending_details(session_factory, article_ids=[10, 20])
    first = MortgageEnrichmentRunner(session_factory, detail_fetcher=async_detail_fetcher, job_id=1)
    second = MortgageEnrichmentRunner(session_factory, detail_fetcher=async_detail_fetcher, job_id=1)

    first_claim = first._claim_batch(batch_size=1)
    second_claim = second._claim_batch(batch_size=1)

    assert {first_claim[0][0], second_claim[0][0]} == {10, 20}


@pytest.mark.asyncio
async def test_failed_detail_fetch_releases_claim_without_marking_checked(session_factory):
    _seed_pending_details(session_factory, article_ids=[10])
    runner = MortgageEnrichmentRunner(session_factory, detail_fetcher=raising_detail_fetcher, job_id=1)

    checked = await runner.run_once(batch_size=1)

    assert checked == 0
    with session_factory() as session:
        listing = session.get(ListingCurrent, 10)
        assert listing.detail_checked_at is None
        assert listing.detail_claim_token is None


def test_expired_claim_is_claimable_again(session_factory):
    _seed_pending_details(session_factory, article_ids=[10], claimed_at=utc_now() - timedelta(minutes=16))
    runner = MortgageEnrichmentRunner(session_factory, detail_fetcher=async_detail_fetcher, job_id=1)
    assert runner._claim_batch(batch_size=1) == [(10, _complex_id_for(10))]
```

- [ ] **Step 2: Run the new tests to verify failure**

Run: `python -m pytest tests/integration/test_detail_enrichment_claims.py tests/integration/test_mortgage_enrichment.py -q`

Expected: FAIL because no claim columns or claim selection exist.

- [ ] **Step 3: Add the migration, model fields, and token-owned writes**

The Alembic migration adds nullable `CHAR(32)` `detail_claim_token` and nullable `DATETIME(6)` `detail_claimed_at` to `listing_current`, plus index `ix_listing_detail_claim` on `(lifecycle, detail_checked_at, detail_claimed_at, article_id)`. Its downgrade drops that index then both columns.

```python
detail_claim_token = Column(String(32), nullable=True)
detail_claimed_at = Column(DateTime6, nullable=True)
```

In `MortgageEnrichmentRunner.__init__`, set `self._claim_token = uuid4().hex`. `_claim_batch` opens a session, selects only active, unchecked rows whose claim is null or older than `utc_now() - timedelta(minutes=15)`, preserving `priority_job_id` as a first query. It updates each selected row with this token and timestamp, commits, and returns `(article_id, complex_id)` tuples. The select is ordered by `article_id` and uses `with_for_update(skip_locked=True)` only when the dialect is MySQL; SQLite tests use the same optimistic token update without that clause.

In the write phase, update a row only if `listing.detail_claim_token == self._claim_token`. For a resolved response, set all existing detail fields, `detail_checked_at=now`, `detail_claim_token=None`, and `detail_claimed_at=None`. For a failed/non-dict response, clear only the matching claim fields. Create history records only for successful writes, retaining `self._job_id`.

- [ ] **Step 4: Run migration and enrichment tests**

Run: `python -m pytest tests/integration/test_detail_enrichment_claims.py tests/integration/test_mortgage_enrichment.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 1 only**

```powershell
git add -- migrations/versions/2026_08_04_0010_detail_enrichment_claim.py src/realty_radar/infrastructure/database/models/v2.py src/realty_radar/application/mortgage_enrichment_service.py tests/integration/test_detail_enrichment_claims.py tests/integration/test_mortgage_enrichment.py
git commit -m "feat: claim pending listing detail enrichment"
```

### Task 2: Add explicit and scheduled bounded detail catchup

**Files:**
- Create: `scripts/enrich_listing_details.py`
- Modify: `src/realty_radar/scheduler/schedules.py`
- Modify: `src/realty_radar/scheduler/scheduler.py`
- Modify: `tests/unit/test_scheduler.py`
- Create: `tests/unit/test_listing_detail_preload_script.py`

**Interfaces:**
- Consumes: `run_site_a_mortgage_enrichment(SessionFactory, job_id, batch_size=100, concurrency=2, max_batches=50)`.
- Produces: a manual command with an explicit job ID and `schedule_listing_detail_backfill() -> None` using the most recent successful crawl job.

- [ ] **Step 1: Write the failing script and scheduler tests**

```python
def test_detail_preload_script_requires_an_explicit_job_id():
    workspace = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, "scripts/enrich_listing_details.py", "--help"], cwd=workspace, capture_output=True, text=True)
    assert result.returncode == 0
    assert "--job-id" in result.stdout
    assert "--max-batches" in result.stdout


def test_schedule_listing_detail_backfill_uses_latest_successful_job(monkeypatch):
    monkeypatch.setattr(schedules, "_latest_successful_crawl_job_id", lambda db: 77)
    observed = {}
    monkeypatch.setattr(schedules, "run_site_a_mortgage_enrichment", lambda *args, **kwargs: observed.update(kwargs) or 5000)

    schedules.schedule_listing_detail_backfill()

    assert observed == {"job_id": 77, "batch_size": 100, "concurrency": 2, "max_batches": 50}


def test_schedule_listing_detail_backfill_skips_when_no_successful_job(monkeypatch):
    monkeypatch.setattr(schedules, "_latest_successful_crawl_job_id", lambda db: None)
    monkeypatch.setattr(schedules, "run_site_a_mortgage_enrichment", lambda *_args, **_kwargs: pytest.fail("must not fetch"))
    schedules.schedule_listing_detail_backfill()
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `python -m pytest tests/unit/test_listing_detail_preload_script.py tests/unit/test_scheduler.py -q`

Expected: FAIL because no dedicated command or scheduled catchup exists.

- [ ] **Step 3: Implement explicit and scheduled entrypoints**

The script parses required `--job-id`, optional `--batch-size` (default 100), `--max-batches` (default 50), and `--concurrency` (default 2). Validate `job_id > 0`, `1 <= batch_size <= 500`, `max_batches > 0`, and `concurrency > 0`. Call `asyncio.run(run_site_a_mortgage_enrichment(...))` and print `checked=<count>`.

Import `JOB_SUCCESS` from `realty_radar.application.crawl_job_service`. Implement `_latest_successful_crawl_job_id(db) -> int | None` using `select(CrawlJob.job_id).where(CrawlJob.status == JOB_SUCCESS).order_by(CrawlJob.job_id.desc()).limit(1)`. `schedule_listing_detail_backfill` obtains that ID in a short DB session, returns without browser work if absent, then runs the existing enrichment coroutine with the exact 100/2/50 limits. Let authentication/bootstrap errors propagate after printing their existing error; do not mark any listing checked on such failure.

Register the job at 23:00 with `id="job_listing_detail_backfill"`, `CronTrigger.from_crontab("0 23 * * *")`, `max_instances=1`, `replace_existing=True`, `misfire_grace_time=3600`, and `coalesce=True`.

- [ ] **Step 4: Run the command and scheduler tests**

Run: `python -m pytest tests/unit/test_listing_detail_preload_script.py tests/unit/test_scheduler.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 2 only**

```powershell
git add -- scripts/enrich_listing_details.py src/realty_radar/scheduler/schedules.py src/realty_radar/scheduler/scheduler.py tests/unit/test_listing_detail_preload_script.py tests/unit/test_scheduler.py
git commit -m "feat: schedule bounded listing detail preload"
```

### Task 3: Render truthful detail states on listing cards

**Files:**
- Modify: `src/realty_radar/web/templates/listings/_listing_cards.html`
- Modify: `tests/integration/test_listing_detail_ui.py`

**Interfaces:**
- Consumes: `item.detail_checked_at`, `item.parking_per_household_x100`, `item.monthly_management_cost`, `item.move_in_date`, and `item.nearest_subway_walk_minutes`.
- Produces: human-readable `확인 대기`, `원본 미제공`, or existing formatted numeric values.

- [ ] **Step 1: Write the failing rendered-card test**

```python
def test_listing_card_distinguishes_unchecked_and_source_missing_detail(monkeypatch):
    unchecked = _factory_with_listing(detail_checked_at=None, parking=None, management=None, subway=None)
    checked_missing = _factory_with_listing(detail_checked_at=datetime(2026, 8, 4), parking=None, management=None, subway=None)

    unchecked_html = _render_home(monkeypatch, unchecked)
    checked_html = _render_home(monkeypatch, checked_missing)

    assert "주차 확인 대기" in unchecked_html
    assert "관리비 확인 대기" in unchecked_html
    assert "역 도보 확인 대기" in unchecked_html
    assert "주차 원본 미제공" in checked_html
    assert "관리비 원본 미제공" in checked_html
    assert "역 도보 원본 미제공" in checked_html
```

- [ ] **Step 2: Run the test to verify failure**

Run: `python -m pytest tests/integration/test_listing_detail_ui.py -k "detail.*state" -q`

Expected: FAIL because currently absent fields are hidden or use a generic placeholder.

- [ ] **Step 3: Add a narrow Jinja macro and use it for the four fields**

At the top of `_listing_cards.html`, add:

```jinja2
{% macro detail_value(item, value, label, suffix='') -%}
  {%- if value is not none -%}{{ label }} {{ value }}{{ suffix }}
  {%- elif not item.detail_checked_at -%}{{ label }} 확인 대기
  {%- else -%}{{ label }} 원본 미제공
  {%- endif -%}
{%- endmacro %}
```

For parking, pass `item.parking_per_household_x100 / 100` only when it is not none and suffix `대/세대`; for management fee pass `item.monthly_management_cost | comma_number` and suffix `원`; for move-in pass `item.move_in_date` using the existing populated format; for subway walk pass `item.nearest_subway_walk_minutes` and suffix `분`. Apply the macro both to the visible tag row and the expanded detail grid. Keep all unrelated card labels and layout unchanged.

- [ ] **Step 4: Run card rendering regression tests**

Run: `python -m pytest tests/integration/test_listing_detail_ui.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 3 only**

```powershell
git add -- src/realty_radar/web/templates/listings/_listing_cards.html tests/integration/test_listing_detail_ui.py
git commit -m "feat: show listing detail collection states"
```

### Task 4: Verify data safety, coverage, and real worker behavior

**Files:**
- Modify: only files from Tasks 1-3 when direct verification fails.
- Test: `tests/integration/test_detail_enrichment_claims.py`
- Test: `tests/integration/test_mortgage_enrichment.py`
- Test: `tests/unit/test_listing_detail_preload_script.py`
- Test: `tests/unit/test_scheduler.py`
- Test: `tests/integration/test_listing_detail_ui.py`

**Interfaces:**
- Consumes: completed claim, catchup, and template behavior.
- Produces: bounded, resumable enrichment with traceable state labels.

- [ ] **Step 1: Run migration and targeted tests**

Run: `alembic upgrade head; python -m pytest tests/integration/test_detail_enrichment_claims.py tests/integration/test_mortgage_enrichment.py tests/unit/test_listing_detail_preload_script.py tests/unit/test_scheduler.py tests/integration/test_listing_detail_ui.py -q`

Expected: migration applies once and all tests pass.

- [ ] **Step 2: Run one bounded authenticated smoke batch**

After confirming the local browser/session preflight succeeds, choose the latest successful crawl job ID and run:

```powershell
python scripts/enrich_listing_details.py --job-id <latest-successful-job-id> --batch-size 10 --max-batches 1 --concurrency 2
```

Expected: output `checked=<0..10>`. If authentication fails, stop without retrying browser actions or marking rows checked; repair the existing authenticated crawler setup first.

- [ ] **Step 3: Measure before/after coverage without treating missing source data as failure**

Run a read-only query reporting, among active listings, `detail_checked_at IS NOT NULL` plus non-null counts for `parking_per_household_x100`, `monthly_management_cost`, `move_in_date`, and `nearest_subway_walk_minutes`. Record both coverage classes: checked rows demonstrate collection progress; non-null fields demonstrate what the source actually provided.

- [ ] **Step 4: Run full regression and browser verification**

Run: `python -m pytest -q; node --test tests/web/test_listing_map_controller.mjs`

Expected: all tests pass.

Verify in a browser that one unchecked card shows `확인 대기`, one checked missing card shows `원본 미제공`, and a known populated card retains its exact numeric unit.

- [ ] **Step 5: Commit direct verification fixes only**

```powershell
git add -- <only files changed by direct verification failures>
git commit -m "test: verify listing detail preload"
```
