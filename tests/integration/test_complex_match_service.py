from datetime import datetime
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.complex_match_service import ComplexMatchService
from realty_radar.constants import TransactionType
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

    # 기존 단지 데이터 생성
    c1 = ApartmentComplex(
        official_name="여의도 시범아파트",
        normalized_name="여의도 시범아파트",
        road_address="서울특별시 영등포구 63로 45",
    )
    session.add(c1)

    source = CrawlSource(code="SITE_A", name="사이트A", base_url="https://site-a.com", adapter_name="adapter_a")
    session.add(source)
    session.flush()

    # 테스트 매물 1 (기존 단지와 매칭 대상)
    listing1 = Listing(
        source_id=source.id,
        external_listing_id="EX-COMPLEX-1",
        source_url="https://site-a.com/c/1",
        complex_name_raw="여의도 시범아파트 10동",
        address_raw="서울특별시 영등포구 63로 45",
        transaction_type=TransactionType.SALE.value,
        sale_price=650_000_000,
        first_seen_at=datetime.now(),
        last_seen_at=datetime.now(),
    )
    session.add(listing1)
    session.commit()

    try:
        yield session
    finally:
        session.close()


def test_complex_match_service_automatic_matching(db_session):
    """ComplexMatchService 매물 단지 자동 매칭 및 별칭 등록 테스트."""
    service = ComplexMatchService(db_session)

    listing = db_session.scalar(select(Listing).where(Listing.external_listing_id == "EX-COMPLEX-1"))
    assert listing.complex_id is None

    # 매칭 수행
    result = service.match_listing_complex(listing.id)

    assert result.complex_id is not None
    assert result.match_score >= 90.0
    assert listing.complex_id == result.complex_id

    # complex_alias에 추가되었는지 확인
    alias = db_session.scalar(select(ComplexAlias).where(ComplexAlias.complex_id == result.complex_id))
    assert alias is not None
    assert alias.alias_name == "여의도 시범아파트 10동"
