from datetime import datetime
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.constants import MortgageStatus, TransactionType
from realty_radar.domain.listing.filters import ListingSearchFilter
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
    """StaticPool 기반 인메모리 DB 세션 및 샘플 매물 등록 픽스처."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSession()

    # 샘플 소스
    source = CrawlSource(code="SITE_A", name="사이트A", base_url="https://site-a.com", adapter_name="adapter_a")
    session.add(source)
    session.flush()

    # 샘플 매물 3건 등록
    item1 = Listing(
        source_id=source.id,
        external_listing_id="EXT-1",
        source_url="https://site-a.com/1",
        complex_name_raw="여의도 시범아파트 1동",
        transaction_type=TransactionType.SALE.value,
        sale_price=650_000_000,
        exclusive_area=Decimal("84.97"),
        mortgage_status=MortgageStatus.EXPLICIT_NONE.value,
        listing_status="ACTIVE",
        first_seen_at=datetime.now(),
        last_seen_at=datetime.now(),
    )
    item2 = Listing(
        source_id=source.id,
        external_listing_id="EXT-2",
        source_url="https://site-a.com/2",
        complex_name_raw="여의도 광장아파트 3동",
        transaction_type=TransactionType.JEONSE.value,
        deposit=400_000_000,
        exclusive_area=Decimal("59.9"),
        mortgage_status=MortgageStatus.EXPLICIT_EXISTS.value,
        listing_status="ACTIVE",
        first_seen_at=datetime.now(),
        last_seen_at=datetime.now(),
    )
    item3 = Listing(
        source_id=source.id,
        external_listing_id="EXT-3",
        source_url="https://site-a.com/3",
        complex_name_raw="강남 삼풍아파트",
        transaction_type=TransactionType.SALE.value,
        sale_price=1_200_000_000,
        exclusive_area=Decimal("130.0"),
        mortgage_status=MortgageStatus.UNKNOWN.value,
        listing_status="ACTIVE",
        first_seen_at=datetime.now(),
        last_seen_at=datetime.now(),
    )

    session.add_all([item1, item2, item3])
    session.commit()

    try:
        yield session
    finally:
        session.close()


def test_search_service_filter_by_transaction_type(db_session):
    """거래 유형 필터링 테스트."""
    service = ListingSearchService(db_session)

    # 매매 필터
    result_sale = service.search_listings(ListingSearchFilter(transaction_type=TransactionType.SALE))
    assert result_sale.total_count == 2

    # 전세 필터
    result_jeonse = service.search_listings(ListingSearchFilter(transaction_type=TransactionType.JEONSE))
    assert result_jeonse.total_count == 1
    assert result_jeonse.items[0].external_listing_id == "EXT-2"


def test_search_service_filter_by_price_and_mortgage(db_session):
    """가격 및 융자 상태 복합 필터링 테스트."""
    service = ListingSearchService(db_session)

    filters = ListingSearchFilter(
        transaction_type=TransactionType.SALE,
        max_price=800_000_000,
        mortgage_status=MortgageStatus.EXPLICIT_NONE,
    )
    result = service.search_listings(filters)

    assert result.total_count == 1
    assert result.items[0].complex_name_raw == "여의도 시범아파트 1동"


def test_search_service_keyword_search(db_session):
    """단지명 키워드 검색 테스트."""
    service = ListingSearchService(db_session)

    result = service.search_listings(ListingSearchFilter(complex_keyword="광장"))
    assert result.total_count == 1
    assert result.items[0].external_listing_id == "EXT-2"
