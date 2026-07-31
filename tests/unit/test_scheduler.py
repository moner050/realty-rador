from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models import Base, CrawlJob, SchedulerLog
from realty_radar.scheduler.schedules import schedule_regular_search_job


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


