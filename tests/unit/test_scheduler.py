from unittest.mock import patch

import pytest
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


def _scheduler_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_schedule_geocode_backfill_uses_daily_sweep_bounds(monkeypatch):
    observed = {}
    factory = _scheduler_session_factory()
    monkeypatch.setattr(
        schedules,
        "run_geocode_sweep",
        lambda *args, **kwargs: observed.update(args=args, **kwargs) or FakeStats(),
    )
    monkeypatch.setattr(schedules, "NaverGeocoder", FakeGeocoder)
    monkeypatch.setattr(schedules, "SessionFactory", factory)

    schedules.schedule_geocode_backfill()

    assert observed["args"][0] is factory
    assert isinstance(observed["args"][1], FakeGeocoder)
    assert observed["batch_size"] == 100
    assert observed["max_batches"] == 5
    assert observed["max_requests"] == 500


def test_schedule_geocode_backfill_records_success_lifecycle(monkeypatch):
    factory = _scheduler_session_factory()
    monkeypatch.setattr(schedules, "SessionFactory", factory)
    monkeypatch.setattr(schedules, "run_geocode_sweep", lambda *args, **kwargs: FakeStats())
    monkeypatch.setattr(schedules, "NaverGeocoder", FakeGeocoder)

    schedules.schedule_geocode_backfill()

    with factory() as session:
        logs = list(session.scalars(select(SchedulerLog)).all())
        assert len(logs) == 1
        assert logs[0].job_name == "네이버 지도 단지 좌표 사전 적재"
        assert logs[0].status == SchedulerLog.STATUS_SUCCESS
        assert logs[0].trigger_type == "cron"
        assert logs[0].finished_at is not None


def test_schedule_geocode_backfill_records_bounded_failure_lifecycle(monkeypatch):
    factory = _scheduler_session_factory()
    monkeypatch.setattr(schedules, "SessionFactory", factory)
    monkeypatch.setattr(schedules, "NaverGeocoder", FakeGeocoder)

    def fail_sweep(*args, **kwargs):
        raise RuntimeError("x" * 600)

    monkeypatch.setattr(schedules, "run_geocode_sweep", fail_sweep)

    with pytest.raises(RuntimeError):
        schedules.schedule_geocode_backfill()

    with factory() as session:
        logs = list(session.scalars(select(SchedulerLog)).all())
        assert len(logs) == 1
        assert logs[0].status == SchedulerLog.STATUS_FAILED
        assert logs[0].error_message == "x" * 512
        assert logs[0].finished_at is not None


def test_task_scheduler_passes_asia_seoul_timezone_to_geocode_trigger(monkeypatch):
    captured = []
    scheduler = RecordingScheduler()

    class RecordingCronTrigger:
        @staticmethod
        def from_crontab(expression, timezone=None):
            captured.append((expression, timezone))
            return expression

    monkeypatch.setattr(scheduler_module, "BackgroundScheduler", lambda: scheduler)
    monkeypatch.setattr(scheduler_module, "CronTrigger", RecordingCronTrigger)

    scheduler_module.TaskScheduler().start()

    assert captured[0][0] == "30 5 * * *"
    assert captured[0][1].key == "Asia/Seoul"


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
    assert geocode_job["trigger"].timezone.key == "Asia/Seoul"
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


