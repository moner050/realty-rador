# Geocode Preload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preload verified coordinates for every known complex without making a map page request call NAVER Geocoding.

**Architecture:** Keep `ComplexCurrent` as the sole coordinate store. Extend the existing backfill service to reuse equal-address results and expose a sweep that opens, commits, and closes one DB session per small batch. The CLI performs the initial capped sweep; an independent pre-crawl APScheduler job handles a small daily budget.

**Tech Stack:** Python 3, SQLAlchemy, FastAPI configuration, APScheduler, httpx, pytest.

## Global Constraints

- Use `ComplexCurrent` latitude, longitude, geocode status, hash, and retry fields; add no coordinate table or migration.
- A page request is read-only: it must neither invoke `NaverGeocoder` nor call `commit`.
- A source address change already resets coordinates to `PENDING`; preserve that behavior.
- `NOT_FOUND` is terminal until the source address changes; `FAILED` retries only after the existing six-hour delay.
- Initial CLI defaults are `batch_size=100`, `max_batches=1`, and `max_requests=15000`; daily automation uses `batch_size=100`, `max_batches=5`, and `max_requests=500`.
- Each completed batch commits before the next batch starts. Use `python -m pytest`, never bare `pytest`.
- Preserve unrelated dirty worktree changes; stage only files changed by the completed task.

---

## File Structure

- `src/realty_radar/enrichment/naver_maps/backfill.py` — address reuse, per-run request budget, and committed sweep orchestration.
- `scripts/backfill_complex_geocodes.py` — explicit initial-catchup CLI flags and aggregate output.
- `src/realty_radar/scheduler/schedules.py` — bounded daily sweep entrypoint.
- `src/realty_radar/scheduler/scheduler.py` — daily pre-crawl scheduler registration.
- `tests/unit/test_complex_geocode_backfill.py` — service and checkpoint behavior.
- `tests/unit/test_backfill_complex_geocodes_script.py` — CLI flags and output contract.
- `tests/unit/test_scheduler.py` — scheduler entrypoint behavior.

### Task 1: Deduplicate addresses inside one backfill batch

**Files:**
- Modify: `src/realty_radar/enrichment/naver_maps/backfill.py`
- Modify: `tests/unit/test_complex_geocode_backfill.py`

**Interfaces:**
- Consumes: `ComplexGeocodeBackfill.run(batch_size, now, complex_ids=None, max_requests=None)`.
- Produces: `GeocodeBackfillStats(selected_count, external_request_count, reused_count, ok_count, not_found_count, failed_count)`.

- [ ] **Step 1: Write the failing address-reuse tests**

```python
def test_backfill_calls_geocoder_once_for_two_pending_complexes_with_same_address():
    session = _session()
    address = "서울특별시 강서구 테스트로 1"
    session.add_all([_complex(1, address), _complex(2, address)])
    session.commit()
    geocoder = CountingGeocoder({address: GeocodeResult(GeocodeStatus.OK, Decimal("37.55"), Decimal("126.85"))})

    stats = ComplexGeocodeBackfill(session, geocoder).run(batch_size=10, now=datetime(2026, 8, 4, 7, 0))

    assert geocoder.calls == [address]
    assert stats.external_request_count == 1
    assert stats.reused_count == 1
    assert {session.get(ComplexCurrent, 1).geocode_status, session.get(ComplexCurrent, 2).geocode_status} == {GEOCODE_STATUS_OK}


def test_backfill_reuses_an_existing_ok_coordinate_without_calling_geocoder():
    session = _session()
    address = "서울특별시 강서구 테스트로 1"
    cached = _complex(1, address, status=GEOCODE_STATUS_OK)
    cached.latitude, cached.longitude = Decimal("37.55"), Decimal("126.85")
    session.add_all([cached, _complex(2, address)])
    session.commit()
    geocoder = CountingGeocoder({})

    stats = ComplexGeocodeBackfill(session, geocoder).run(batch_size=10, now=datetime(2026, 8, 4, 7, 0))

    assert geocoder.calls == []
    assert stats.external_request_count == 0
    assert stats.reused_count == 1
    assert session.get(ComplexCurrent, 2).latitude == Decimal("37.5500000")
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `python -m pytest tests/unit/test_complex_geocode_backfill.py -k "same_address or existing_ok" -q`

Expected: FAIL because the current backfill calls the geocoder once per pending row and has no reuse counters.

- [ ] **Step 3: Add the smallest exact reuse implementation**

```python
@dataclass(frozen=True, slots=True)
class GeocodeBackfillStats:
    selected_count: int = 0
    external_request_count: int = 0
    reused_count: int = 0
    ok_count: int = 0
    not_found_count: int = 0
    failed_count: int = 0
```

After selecting candidates, load `OK` `ComplexCurrent` rows whose `address` appears in the candidates into an `address -> (latitude, longitude)` map. Iterate candidates in `complex_id` order. Reuse a successful stored coordinate first; otherwise reuse a result stored in an in-memory `outcomes_by_address` map; only then call `self.geocoder.geocode(address)`. Apply the same result transition to every duplicate candidate. Increment `reused_count` only for rows that did not make an external request, and increment `external_request_count` only immediately before `geocode()`.

```python
if max_requests is not None and external_request_count >= max_requests:
    break
result = self.geocoder.geocode(candidate.address)
external_request_count += 1
outcomes_by_address[candidate.address] = result
```

Leave unprocessed candidates as `PENDING` when the budget is exhausted. Do not change the six-hour failure transition or address hash calculation.

- [ ] **Step 4: Run the service test file**

Run: `python -m pytest tests/unit/test_complex_geocode_backfill.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 1 only**

```powershell
git add -- src/realty_radar/enrichment/naver_maps/backfill.py tests/unit/test_complex_geocode_backfill.py
git commit -m "feat: reuse duplicate complex geocodes"
```

### Task 2: Add a checkpointed, request-capped sweep and CLI

**Files:**
- Modify: `src/realty_radar/enrichment/naver_maps/backfill.py`
- Modify: `scripts/backfill_complex_geocodes.py`
- Modify: `tests/unit/test_complex_geocode_backfill.py`
- Modify: `tests/unit/test_backfill_complex_geocodes_script.py`

**Interfaces:**
- Consumes: a zero-argument SQLAlchemy `session_factory`, a configured `Geocoder`, and integer batch/request limits.
- Produces: `run_geocode_sweep(session_factory, geocoder, *, now, batch_size, max_batches, max_requests, complex_ids=None) -> GeocodeSweepStats`.

- [ ] **Step 1: Write the failing sweep and CLI tests**

```python
def test_geocode_sweep_commits_each_batch_and_stops_at_request_budget():
    factory = _session_factory_with_pending_complexes(3)
    geocoder = CountingGeocoder({address: ok_result(index) for index, address in enumerate(_addresses(3))})

    stats = run_geocode_sweep(
        factory, geocoder, now=datetime(2026, 8, 4, 7, 0),
        batch_size=1, max_batches=3, max_requests=2,
    )

    assert stats.batch_count == 2
    assert stats.external_request_count == 2
    with factory() as session:
        assert _status_counts(session) == {GEOCODE_STATUS_OK: 2, GEOCODE_STATUS_PENDING: 1}


def test_backfill_command_exposes_sweep_limits():
    result = subprocess.run([sys.executable, "scripts/backfill_complex_geocodes.py", "--help"], ...)
    assert "--max-batches" in result.stdout
    assert "--max-requests" in result.stdout
```

- [ ] **Step 2: Run the new tests to verify failure**

Run: `python -m pytest tests/unit/test_complex_geocode_backfill.py tests/unit/test_backfill_complex_geocodes_script.py -q`

Expected: FAIL because no sweep orchestration or limit flags exist.

- [ ] **Step 3: Implement the committed sweep and CLI**

```python
def run_geocode_sweep(session_factory, geocoder, *, now, batch_size, max_batches, max_requests, complex_ids=None):
    stats = GeocodeSweepStats()
    for _ in range(max_batches):
        if stats.external_request_count >= max_requests:
            break
        with session_factory() as session:
            batch = ComplexGeocodeBackfill(session, geocoder).run(
                batch_size=batch_size, now=now, complex_ids=complex_ids,
                max_requests=max_requests - stats.external_request_count,
            )
            session.commit()
        stats = stats.add(batch)
        if batch.selected_count == 0:
            break
    return stats
```

Define frozen `GeocodeSweepStats` with `batch_count` and the six integer counters in `GeocodeBackfillStats`; its `add()` method returns a new aggregate. Validate all three limits are positive. Add `--max-batches` and `--max-requests` to the CLI, replace its manually opened single session with `run_geocode_sweep(SessionLocal, NaverGeocoder(), ...)`, and print every aggregate counter as `key=value`.

- [ ] **Step 4: Run sweep and command tests**

Run: `python -m pytest tests/unit/test_complex_geocode_backfill.py tests/unit/test_backfill_complex_geocodes_script.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 2 only**

```powershell
git add -- src/realty_radar/enrichment/naver_maps/backfill.py scripts/backfill_complex_geocodes.py tests/unit/test_complex_geocode_backfill.py tests/unit/test_backfill_complex_geocodes_script.py
git commit -m "feat: add checkpointed geocode sweep"
```

### Task 3: Schedule a bounded daily preload independently of page traffic

**Files:**
- Modify: `src/realty_radar/scheduler/schedules.py`
- Modify: `src/realty_radar/scheduler/scheduler.py`
- Modify: `tests/unit/test_scheduler.py`

**Interfaces:**
- Consumes: `run_geocode_sweep`, `NaverGeocoder`, `SessionFactory`, and `utc_now()`.
- Produces: `schedule_geocode_backfill() -> None`, registered at 05:30 Asia/Seoul before the existing 06:00 crawl enqueue.

- [ ] **Step 1: Write the failing scheduler tests**

```python
def test_schedule_geocode_backfill_uses_the_daily_500_request_budget(monkeypatch):
    observed = {}
    monkeypatch.setattr(schedules, "run_geocode_sweep", lambda *args, **kwargs: observed.update(kwargs) or FakeStats())
    monkeypatch.setattr(schedules, "NaverGeocoder", FakeGeocoder)

    schedules.schedule_geocode_backfill()

    assert observed["batch_size"] == 100
    assert observed["max_batches"] == 5
    assert observed["max_requests"] == 500


def test_task_scheduler_registers_daily_geocode_job_before_crawl_job(monkeypatch):
    scheduler = RecordingScheduler()
    monkeypatch.setattr(scheduler_module, "BackgroundScheduler", lambda: scheduler)

    task_scheduler = scheduler_module.TaskScheduler()
    task_scheduler.start()

    assert scheduler.jobs[0]["id"] == "job_geocode_complexes"
    assert scheduler.jobs[0]["trigger"].fields[5].expressions[0].first == 30
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `python -m pytest tests/unit/test_scheduler.py -q`

Expected: FAIL because there is only a 06:00 crawl-enqueue job.

- [ ] **Step 3: Implement the independent scheduled function**

```python
def schedule_geocode_backfill() -> None:
    stats = run_geocode_sweep(
        SessionFactory, NaverGeocoder(), now=utc_now(),
        batch_size=100, max_batches=5, max_requests=500,
    )
    print(f"[Scheduler] geocode selected={stats.selected_count} requests={stats.external_request_count} ok={stats.ok_count} not_found={stats.not_found_count} failed={stats.failed_count}")
```

Import this function into `scheduler.py` and register it with `CronTrigger.from_crontab("30 5 * * *")`, `id="job_geocode_complexes"`, `replace_existing=True`, `misfire_grace_time=3600`, and `coalesce=True`. Do not call it from `schedule_regular_search_job`; the map batch must remain independent from crawls and browser requests.

- [ ] **Step 4: Run scheduler and prior focused tests**

Run: `python -m pytest tests/unit/test_scheduler.py tests/unit/test_complex_geocode_backfill.py tests/unit/test_backfill_complex_geocodes_script.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 3 only**

```powershell
git add -- src/realty_radar/scheduler/schedules.py src/realty_radar/scheduler/scheduler.py tests/unit/test_scheduler.py
git commit -m "feat: schedule daily complex geocode preload"
```

### Task 4: Remove geocoding from the map request and verify the initial catchup

**Files:**
- Modify: `src/realty_radar/web/routes/home.py`
- Modify: `tests/integration/test_listing_map_ui.py`
- Test: `tests/unit/test_complex_geocode_backfill.py`

**Interfaces:**
- Consumes: stored `ComplexCurrent` coordinates only.
- Produces: `/listings/map` as a read-only map fragment; a pending coordinate remains a rendered status, not an on-demand API call.

- [ ] **Step 1: Replace the on-demand geocode integration test**

```python
def test_map_sidebar_does_not_geocode_or_commit_pending_coordinates(monkeypatch):
    factory = _factory(verified_coordinate=False)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    monkeypatch.setattr(home, "NaverGeocoder", lambda: (_ for _ in ()).throw(AssertionError("must not construct geocoder")))
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/listings/map")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    with factory() as session:
        assert session.get(ComplexCurrent, 1).geocode_status == GEOCODE_STATUS_PENDING
```

- [ ] **Step 2: Run the test to verify failure**

Run: `python -m pytest tests/integration/test_listing_map_ui.py -k "does_not_geocode" -q`

Expected: FAIL because `/listings/map` currently constructs `NaverGeocoder`, updates the row, and commits.

- [ ] **Step 3: Delete only the request-time geocoding block**

Remove `ComplexGeocodeBackfill`, `NaverGeocoder`, and the corresponding datetime imports from `home.py` when they have no remaining use. Keep the response status message for unverified coordinates, but do not call `rollback` or `commit` in the route. Keep the existing verified-marker rendering until the map aggregation plan replaces it.

- [ ] **Step 4: Run focused regression checks and the initial operator command**

Run: `python -m pytest tests/integration/test_listing_map_ui.py tests/unit/test_complex_geocode_backfill.py tests/unit/test_backfill_complex_geocodes_script.py tests/unit/test_scheduler.py -q`

Expected: PASS.

After automated tests pass and with production credentials configured, run once:

```powershell
python scripts/backfill_complex_geocodes.py --batch-size 100 --max-batches 150 --max-requests 15000
```

Record the command output and query `ComplexCurrent.geocode_status` counts before and after. Do not rerun failures before their retry time.

- [ ] **Step 5: Commit Task 4 only**

```powershell
git add -- src/realty_radar/web/routes/home.py tests/integration/test_listing_map_ui.py
git commit -m "fix: keep map requests free of geocoding"
```
