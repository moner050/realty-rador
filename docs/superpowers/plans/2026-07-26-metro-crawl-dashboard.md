# 수도권 전체 수동 수집 현황 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 수집현황에서 서울·경기·인천의 모든 시/군/구 수집 job을 한 번에 등록하고, 가장 최근 batch의 시군구별 진행 상태를 표시한다.

**Architecture:** CrawlJobService가 기존 crawl_job 행을 manual-metro:<run-id>:<sigungu-code> dedupe key로 생성한다. 최신 batch를 key prefix로 조회해 진행 DTO를 만들고, HTMX fragment가 그 DTO를 5초마다 다시 렌더링한다. worker·pipeline의 lease, retry, scope 처리 경로는 바꾸지 않는다.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy, Jinja2, HTMX, pytest, MySQL 8.4.

## Global Constraints

- SITE_A 전용이며 서울·경기·인천의 SIGUNGU_CODES만 사용한다.
- 새 테이블·migration·worker process 시작 기능을 만들지 않는다.
- 웹 버튼은 job 등록만 하며 실행 worker가 없으면 queued 상태로 표시한다.
- 활성 전체 수집 batch가 있으면 새 batch를 만들지 않는다.

---

### Task 1: 수도권 batch 서비스와 상태 집계

**Files:**

- Modify: src/realty_radar/application/crawl_job_service.py
- Test: tests/integration/test_crawl_job_service.py

**Interfaces:**

- Produces: CrawlJobService.enqueue_metro_batch() -> list[CrawlJob]
- Produces: CrawlJobService.get_latest_metro_batch_progress() -> dict[str, object]

- [ ] **Step 1: Write failing service tests**

~~~python
def test_enqueue_metro_batch_creates_one_job_per_sigungu_and_blocks_active_batch():
    jobs = service.enqueue_metro_batch()
    assert len(jobs) == sum(len(codes) for codes in SIGUNGU_CODES.values())
    assert all(job.scope_level == 2 for job in jobs)
    assert service.enqueue_metro_batch() == []


def test_latest_metro_batch_progress_groups_sigungu_status_and_counts():
    jobs = service.enqueue_metro_batch()
    jobs[0].status = JOB_RUNNING
    jobs[1].status = JOB_SUCCESS
    session.commit()
    progress = service.get_latest_metro_batch_progress()
    assert progress["total_sigungu"] == len(jobs)
    assert progress["running_count"] == 1
    assert progress["completed_count"] == 1
    assert progress["regions"][0]["items"]
~~~

- [ ] **Step 2: Verify RED**

Run: python -m pytest tests/integration/test_crawl_job_service.py -q

Expected: FAIL because the service methods do not exist.

- [ ] **Step 3: Implement the minimal service API**

~~~python
METRO_BATCH_PREFIX = "manual-metro:"

def enqueue_metro_batch(self) -> list[CrawlJob]:
    if self.get_latest_metro_batch_progress()["is_active"]:
        return []
    batch_id = uuid4().hex
    return [
        self.create_job(
            scope_level=2,
            scope_code=int(code),
            dedupe_key=f"{METRO_BATCH_PREFIX}{batch_id}:{code}",
            priority=50,
        )
        for _, codes in SIGUNGU_CODES.items()
        for _, code in codes.items()
    ]
~~~

Parse the run ID from the most recent prefixed job and query all matching jobs. Map scope_code to Sido and Sigungu names. Return queued/running/completed/retry/failed counts, is_active, each job’s fetched/committed counts, and bounded error text. Leave existing generic progress summary unchanged.

- [ ] **Step 4: Verify GREEN and commit**

Run: python -m pytest tests/integration/test_crawl_job_service.py -q

Expected: PASS.

~~~powershell
git add src/realty_radar/application/crawl_job_service.py tests/integration/test_crawl_job_service.py
git commit -m "feat: enqueue metro crawl batches"
~~~

### Task 2: 수집현황 route와 progress fragment

**Files:**

- Modify: src/realty_radar/web/routes/crawl_jobs.py
- Modify: src/realty_radar/web/templates/jobs/index.html
- Modify: src/realty_radar/web/templates/jobs/progress_partial.html
- Create: tests/integration/test_crawl_jobs_dashboard.py

**Interfaces:**

- Consumes: Task 1’s two CrawlJobService methods.
- Produces: authenticated POST /api/crawl-jobs/metro and a progress fragment with metro_progress.

- [ ] **Step 1: Write failing route/template tests**

~~~python
def test_metro_post_enqueues_batch_and_returns_progress_fragment(client):
    response = client.post("/api/crawl-jobs/metro", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "서울" in response.text
    assert "worker 대기 중" in response.text


def test_jobs_dashboard_renders_disabled_metro_button_and_sigungu_statuses(client):
    client.post("/api/crawl-jobs/metro")
    response = client.get("/jobs")
    assert 'action="/api/crawl-jobs/metro"' in response.text
    assert "disabled" in response.text
    assert "시/군/구별 진행 현황" in response.text
~~~

The test client must override get_db with an in-memory SQLite session and set a valid realty_session cookie via create_session_token.

- [ ] **Step 2: Verify RED**

Run: python -m pytest tests/integration/test_crawl_jobs_dashboard.py -q

Expected: FAIL because the route and template content do not exist.

- [ ] **Step 3: Implement minimal route/template changes**

~~~python
@router.post("/api/crawl-jobs/metro", name="create_metro_crawl_batch")
def create_metro_crawl_batch(request: Request, db: Annotated[Session, Depends(get_db)]):
    CrawlJobService(db).enqueue_metro_batch()
    return _render_progress(request, db)
~~~

Use _render_progress for both POST and GET /api/crawl-jobs/progress. Keep the existing single-region form and recent job table. Add a clearly labelled “수도권 전체 수동 수집” button that is disabled only when metro_progress["is_active"]. The fragment must use hx-get="/api/crawl-jobs/progress", hx-trigger="every 5s", and hx-swap="outerHTML"; show worker 대기 중 when queued jobs exist and no job is running. Render each Sido section with Sigungu name, status, fetched/committed counts, and error detail.

- [ ] **Step 4: Verify GREEN and commit**

Run: python -m pytest tests/integration/test_crawl_jobs_dashboard.py tests/integration/test_crawl_job_service.py -q

Expected: PASS.

~~~powershell
git add src/realty_radar/web/routes/crawl_jobs.py src/realty_radar/web/templates/jobs/index.html src/realty_radar/web/templates/jobs/progress_partial.html tests/integration/test_crawl_jobs_dashboard.py
git commit -m "feat: show metro crawl progress dashboard"
~~~

### Task 3: Retry/failed regression and full verification

**Files:**

- Modify: tests/integration/test_crawl_job_service.py

**Interfaces:**

- Consumes: get_latest_metro_batch_progress().
- Produces: retry/failed status coverage for a sigungu row.

- [ ] **Step 1: Write the retry/failed regression**

~~~python
def test_latest_metro_batch_progress_exposes_retry_and_failed_sigungu():
    jobs = service.enqueue_metro_batch()
    jobs[0].status = JOB_RETRY_WAIT
    jobs[0].error_code = "HTTP_429"
    jobs[1].status = JOB_FAILED
    jobs[1].error_message = "retry exhausted"
    session.commit()
    progress = service.get_latest_metro_batch_progress()
    assert progress["pending_count"] >= 1
    assert progress["failed_count"] == 1
~~~

- [ ] **Step 2: Verify RED or close the missing aggregation**

Run: python -m pytest tests/integration/test_crawl_job_service.py::test_latest_metro_batch_progress_exposes_retry_and_failed_sigungu -q

Expected: FAIL if Task 1 omitted the aggregation; then add only that aggregation and re-run to PASS.

- [ ] **Step 3: Run full verification**

Run: python -m pytest -q; python -m compileall -q src; git diff --check

Expected: all tests PASS and exit code 0.

- [ ] **Step 4: Commit test changes if Task 3 added them**

~~~powershell
git add tests/integration/test_crawl_job_service.py
git commit -m "test: cover metro crawl status retries"
~~~

## Plan self-review

- Task 1 covers durable per-sigungu job creation, active-batch blocking, and status aggregation.
- Task 2 covers the action, worker-wait display, automatic refresh, and human-readable Sigungu view.
- Task 3 covers retry/failed rows and full regressions.
- The plan adds no table, migration, crawler behavior, or worker-launch behavior.
