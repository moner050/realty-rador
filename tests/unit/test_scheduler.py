from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models import Base, CrawlJob
from realty_radar.scheduler.schedules import schedule_regular_search_job


def test_schedule_regular_search_job_enqueues_metro_batch():
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
        assert len(jobs) == 75  # 수도권 전체 75개 시/군/구 정기 수집 배치 생성 확인
        assert any("manual-metro:" in job.dedupe_key for job in jobs)
