from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.crawl_job_service import (
    JOB_QUEUED,
    JOB_RETRY_WAIT,
    JOB_RUNNING,
    CrawlJobService,
)
from realty_radar.application.listing_batch_writer import IncomingListing, ListingBatchWriter
from realty_radar.infrastructure.database.models import Base, ListingCurrent


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _listing(article_id: int) -> IncomingListing:
    return IncomingListing(
        article_id=article_id,
        complex_id=1001,
        region_code=1150010200,
        complex_name="테스트 아파트",
        normalized_complex_name="테스트아파트",
        address="서울특별시 강서구 테스트로 1",
        trade_type=1,
        primary_price=500_000_000,
    )


def test_job_claim_uses_lease_and_heartbeat():
    session = _session()
    service = CrawlJobService(session)
    queued = service.create_job(scope_level=3, scope_code=1150010200, dedupe_key="dong:1150010200")
    assert queued.status == JOB_QUEUED

    claimed = service.claim_next_job("worker-a")
    assert claimed is not None
    assert claimed.status == JOB_RUNNING
    assert claimed.lease_owner == "worker-a"
    assert claimed.lease_token
    assert claimed.lease_expires_at is not None
    assert service.heartbeat(claimed.job_id, claimed.lease_token) is True

    retried = service.mark_retry(claimed.job_id, claimed.lease_token, "HTTP_429", "retry later")
    assert retried is not None
    assert retried.status == JOB_RETRY_WAIT


def test_only_complete_scope_advances_stale_then_removed():
    session = _session()
    service = CrawlJobService(session)

    first = service.create_job(scope_level=3, scope_code=1150010200, dedupe_key="dong:1150010200:one")
    ListingBatchWriter(session).commit_batch(first.job_id, [_listing(2001)])
    service.open_scope(first.job_id, 1150010200)
    assert service.complete_scope(first.job_id, 1150010200) == (0, 0)

    incomplete = service.create_job(scope_level=3, scope_code=1150010200, dedupe_key="dong:1150010200:incomplete")
    service.open_scope(incomplete.job_id, 1150010200)
    service.fail_scope(incomplete.job_id, 1150010200, "PARTIAL", "page failed")
    assert service.complete_scope(incomplete.job_id, 1150010200) == (0, 0)
    assert session.scalar(select(ListingCurrent.lifecycle).where(ListingCurrent.article_id == 2001)) == 1

    second = service.create_job(scope_level=3, scope_code=1150010200, dedupe_key="dong:1150010200:two")
    service.open_scope(second.job_id, 1150010200)
    assert service.complete_scope(second.job_id, 1150010200) == (1, 0)
    assert session.scalar(select(ListingCurrent.lifecycle).where(ListingCurrent.article_id == 2001)) == 2
    assert service.complete_scope(second.job_id, 1150010200) == (0, 0)
    assert session.scalar(select(ListingCurrent.lifecycle).where(ListingCurrent.article_id == 2001)) == 2

    third = service.create_job(scope_level=3, scope_code=1150010200, dedupe_key="dong:1150010200:three")
    service.open_scope(third.job_id, 1150010200)
    assert service.complete_scope(third.job_id, 1150010200) == (0, 1)
    assert session.scalar(select(ListingCurrent.lifecycle).where(ListingCurrent.article_id == 2001)) == 3
