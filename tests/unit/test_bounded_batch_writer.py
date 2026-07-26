import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.async_batch_writer import BoundedBatchWriter
from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.application.listing_batch_writer import IncomingListing
from realty_radar.infrastructure.database.models import Base, ListingCurrent


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _row(article_id: int) -> IncomingListing:
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


@pytest.mark.anyio
async def test_writer_uses_bounded_queue_and_flushes_500_row_batches():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        job = CrawlJobService(session).create_job(
            scope_level=3,
            scope_code=1150010200,
            dedupe_key="dong:1150010200:writer",
        )
        job_id = job.job_id

    writer = BoundedBatchWriter(factory, job_id, max_queue_size=600, batch_size=500, flush_seconds=60)
    writer.start()
    await writer.submit([_row(10_000 + index) for index in range(501)])
    await writer.flush()
    result = await writer.aclose()

    assert result.committed_count == 501
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ListingCurrent)) == 501
