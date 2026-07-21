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
    """StaticPool 인메모리 DB 픽스처 및 단지/매물 셋업."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSession()

    source = CrawlSource(code="SITE_A", name="사이트A", base_url="https://site-a.com", adapter_name="adapter_a")
    session.add(source)

    # 단지 2개 (2012년 1200세대 / 2002년 300세대)
    c1 = ApartmentComplex(official_name="여의도 시범아파트", normalized_name="여의도시범아파트", construction_year=2012, household_count=1200)
    c2 = ApartmentComplex(official_name="여의도 삼부아파트", normalized_name="여의도삼부아파트", construction_year=2002, household_count=300)
    session.add_all([c1, c2])
    session.flush()

    listing1 = Listing(
        source_id=source.id,
        complex_id=c1.id,
        external_listing_id="ADV-1",
        source_url="https://site-a.com/adv/1",
        complex_name_raw="여의도 시범아파트",
        transaction_type=TransactionType.SALE.value,
        sale_price=650_000_000,
        mortgage_status=MortgageStatus.EXPLICIT_NONE.value,
        first_seen_at=datetime.now(),
        last_seen_at=datetime.now(),
    )

    listing2 = Listing(
        source_id=source.id,
        complex_id=c2.id,
        external_listing_id="ADV-2",
        source_url="https://site-a.com/adv/2",
        complex_name_raw="여의도 삼부아파트",
        transaction_type=TransactionType.SALE.value,
        sale_price=900_000_000,
        mortgage_status=MortgageStatus.UNKNOWN.value,
        first_seen_at=datetime.now(),
        last_seen_at=datetime.now(),
    )

    session.add_all([listing1, listing2])
    session.commit()

    try:
        yield session
    finally:
        session.close()


def test_advanced_search_by_complex_year_and_households(db_session):
    """단지 준공연도 및 세대수 통합 검색 테스트."""
    service = ListingSearchService(db_session)

    # 2010년 이후 & 500세대 이상 필터
    filters = ListingSearchFilter(
        min_construction_year=2010,
        min_households=500,
    )
    result = service.search_listings(filters)

    assert result.total_count == 1
    assert result.items[0].external_listing_id == "ADV-1"


def test_advanced_search_exclude_unknown_mortgage(db_session):
    """융자 정보 미상 매물 제외 필터 테스트."""
    service = ListingSearchService(db_session)

    filters = ListingSearchFilter(exclude_unknown_mortgage=True)
    result = service.search_listings(filters)

    assert result.total_count == 1
    assert result.items[0].mortgage_status == MortgageStatus.EXPLICIT_NONE.value
