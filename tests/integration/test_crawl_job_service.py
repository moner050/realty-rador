import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.constants import CrawlJobStatus, CrawlJobType
from realty_radar.infrastructure.database.models import (
    ApartmentComplex,
    Base,
    ComplexAlias,
    CrawlJob,
    CrawlSchedule,
    CrawlSource,
    Listing,
    ListingSnapshot,
)


@pytest.fixture(name="db_session")
def db_session_fixture():
    """StaticPool 인메모리 DB 픽스처."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def test_crawl_job_lifecycle(db_session):
    """crawl_job 등록 -> 선점 -> 성공/실패 백오프 라이프사이클 테스트."""
    service = CrawlJobService(db_session)

    # 1. 작업 생성
    job = service.create_job(
        source_code="SITE_A",
        job_type=CrawlJobType.SEARCH,
        request_data={"region_name": "여의도동"},
    )
    assert job.status == CrawlJobStatus.PENDING.value
    assert job.attempt_count == 0

    # 2. Worker가 작업 선점
    fetched_job = service.fetch_next_job(worker_id="worker-test-1")
    assert fetched_job is not None
    assert fetched_job.id == job.id
    assert fetched_job.status == CrawlJobStatus.RUNNING.value
    assert fetched_job.attempt_count == 1
    assert fetched_job.worker_id == "worker-test-1"

    # 3. 1차 실패 시 백오프 예약 (RETRY_WAIT)
    failed_job = service.mark_job_failure(
        job_id=job.id,
        error_type="NetworkError",
        error_message="연결 시간 초과",
    )
    assert failed_job.status == CrawlJobStatus.RETRY_WAIT.value
    assert failed_job.next_retry_at is not None

    # 4. 성공 처리 테스트
    success_job = service.mark_job_success(job.id, result_data={"total_fetched": 10})
    assert success_job.status == CrawlJobStatus.SUCCESS.value
    assert success_job.completed_at is not None
