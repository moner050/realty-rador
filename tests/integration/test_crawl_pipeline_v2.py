import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.application.crawl_pipeline_service import CrawlPipelineService
from realty_radar.application.listing_batch_writer import IncomingListing
from realty_radar.crawler.adapters.site_a.adapter import DongCollectionOutcome
from realty_radar.infrastructure.database.models import Base, CrawlScope


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeAdapter:
    def __init__(self):
        self.bootstrap_count = 0
        self.closed = False

    async def begin_job(self):
        self.bootstrap_count += 1

    async def list_dongs(self, region_code: int):
        return [1150010200]

    async def collect_dong(self, region_code: int, on_batch):
        result = on_batch(
            [
                IncomingListing(
                    article_id=2001,
                    complex_id=1001,
                    region_code=region_code,
                    complex_name="테스트 아파트",
                    normalized_complex_name="테스트아파트",
                    address="서울특별시 강서구 테스트로 1",
                    trade_type=1,
                    primary_price=500_000_000,
                )
            ]
        )
        if result is not None:
            await result
        return DongCollectionOutcome(region_code, 1, 1, 0, False)

    async def aclose(self):
        self.closed = True


@pytest.mark.anyio
async def test_pipeline_bootstraps_each_job_but_keeps_injected_worker_adapter_open():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    adapter = FakeAdapter()
    with factory() as session:
        job = CrawlJobService(session).create_job(scope_level=1, scope_code=1100000000, dedupe_key="pipeline:1")
        result = await CrawlPipelineService(session, session_factory=factory, adapter=adapter).execute_job(job)

        assert result["created_count"] == 1
        assert result["partial_scope_count"] == 0
        assert adapter.bootstrap_count == 1
        assert adapter.closed is False
        assert session.get(CrawlScope, (job.job_id, 1150010200)).status == 2
