from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models import Base, CrawlJob, SchedulerLog
from realty_radar.scheduler import scheduler as scheduler_module
from realty_radar.scheduler import schedules
from realty_radar.scheduler.schedules import schedule_regular_search_job


class FakeStats:
    selected_count = 0
    external_request_count = 0
    ok_count = 0
    not_found_count = 0
    failed_count = 0


class FakeGeocoder:
    pass


class RecordingScheduler:
    def __init__(self):
        self.jobs = []
        self.started = False

    def add_job(self, func, **kwargs):
        self.jobs.append({"func": func, **kwargs})

    def start(self):
        self.started = True


def test_schedule_geocode_backfill_uses_daily_sweep_bounds(monkeypatch):
    observed = {}
    monkeypatch.setattr(
        schedules,
        "run_geocode_sweep",
        lambda *args, **kwargs: observed.update(args=args, **kwargs) or FakeStats(),
    )
    monkeypatch.setattr(schedules, "NaverGeocoder", FakeGeocoder)

    schedules.schedule_geocode_backfill()

    assert observed["args"][0] is schedules.SessionFactory
    assert isinstance(observed["args"][1], FakeGeocoder)
    assert observed["batch_size"] == 100
    assert observed["max_batches"] == 5
    assert observed["max_requests"] == 500


def test_task_scheduler_registers_geocode_before_0600_crawl(monkeypatch):
    scheduler = RecordingScheduler()
    monkeypatch.setattr(scheduler_module, "BackgroundScheduler", lambda: scheduler)

    task_scheduler = scheduler_module.TaskScheduler()
    task_scheduler.start()

    geocode_job, crawl_job = scheduler.jobs
    assert geocode_job["id"] == "job_geocode_complexes"
    assert geocode_job["func"] is scheduler_module.schedule_geocode_backfill
    assert geocode_job["trigger"].fields[5].expressions[0].first == 5
    assert geocode_job["trigger"].fields[6].expressions[0].first == 30
    assert crawl_job["id"] == "job_regular_search_site_a"
    assert crawl_job["trigger"].fields[5].expressions[0].first == 6
    assert crawl_job["trigger"].fields[6].expressions[0].first == 0
    assert scheduler.started is True


def test_schedule_regular_search_job_enqueues_metro_batch_and_logs():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with patch("realty_radar.scheduler.schedules.SessionFactory", factory):
        schedule_regular_search_job()

    with factory() as session:
        jobs = list(session.scalars(select(CrawlJob)).all())
        assert len(jobs) == 84  # 수도권 전체 84개 시/군/구 정기 수집 배치 생성 확인
        assert any("manual-metro:" in job.dedupe_key for job in jobs)

        logs = list(session.scalars(select(SchedulerLog)).all())
        assert len(logs) == 1
        assert logs[0].status == SchedulerLog.STATUS_SUCCESS
        assert logs[0].jobs_created == 84
        assert logs[0].trigger_type == "cron"


