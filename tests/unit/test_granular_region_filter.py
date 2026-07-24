from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.domain.listing.models import ListingFilterParams
from realty_radar.infrastructure.database.models import Base, CrawlSource, Listing


@pytest.fixture(name="db_session")
def db_session_fixture():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()

    source = CrawlSource(source_code="SITE_A", source_name="네이버부동산", base_url="https://land.naver.com")
    session.add(source)
    session.commit()

    yield session
    session.close()


def test_granular_region_filtering_sido_city_county_district(db_session: Session):
    """시(City), 군(County), 구(District) 독립 및 조합 필터링 정밀 테스트."""
    source = db_session.query(CrawlSource).filter_by(source_code="SITE_A").first()
    assert source is not None

    # 1. 테스트 매물 4건 등록
    l1 = Listing(
        source_id=source.id,
        external_listing_id="TEST_REG_1",
        source_url="http://example.com/1",
        complex_name_raw="과천 래미안",
        address_raw="경기도 과천시 중앙동 10",
        sido="경기도",
        sigungu="과천시",
        transaction_type="SALE",
        price_deposit=Decimal("1000000000"),
        status="ACTIVE",
    )
    l2 = Listing(
        source_id=source.id,
        external_listing_id="TEST_REG_2",
        source_url="http://example.com/2",
        complex_name_raw="가평 아이파크",
        address_raw="경기도 가평군 가평읍 20",
        sido="경기도",
        sigungu="가평군",
        transaction_type="SALE",
        price_deposit=Decimal("500000000"),
        status="ACTIVE",
    )
    l3 = Listing(
        source_id=source.id,
        external_listing_id="TEST_REG_3",
        source_url="http://example.com/3",
        complex_name_raw="강남 자이",
        address_raw="서울특별시 강남구 역삼동 30",
        sido="서울특별시",
        sigungu="강남구",
        transaction_type="SALE",
        price_deposit=Decimal("1500000000"),
        status="ACTIVE",
    )
    l4 = Listing(
        source_id=source.id,
        external_listing_id="TEST_REG_4",
        source_url="http://example.com/4",
        complex_name_raw="분당 푸르지오",
        address_raw="경기도 성남시 분당구 정자동 40",
        sido="경기도",
        sigungu="성남시 분당구",
        transaction_type="SALE",
        price_deposit=Decimal("1200000000"),
        status="ACTIVE",
    )
    db_session.add_all([l1, l2, l3, l4])
    db_session.commit()

    service = ListingSearchService(db_session)

    # 1) 시(City) 필터 테스트: '과천시' -> l1 단독 검색
    res_city = service.search_listings(ListingFilterParams(city="과천시"))
    assert res_city.total_count == 1
    assert res_city.items[0].external_listing_id == "TEST_REG_1"

    # 2) 군(County) 필터 테스트: '가평군' -> l2 단독 검색
    res_county = service.search_listings(ListingFilterParams(county="가평군"))
    assert res_county.total_count == 1
    assert res_county.items[0].external_listing_id == "TEST_REG_2"

    # 3) 구(District) 필터 테스트: '강남구' -> l3 단독 검색
    res_district = service.search_listings(ListingFilterParams(district="강남구"))
    assert res_district.total_count == 1
    assert res_district.items[0].external_listing_id == "TEST_REG_3"

    # 4) 구(District) 필터 테스트: '분당구' -> l4 단독 검색
    res_bundang = service.search_listings(ListingFilterParams(district="분당구"))
    assert res_bundang.total_count == 1
    assert res_bundang.items[0].external_listing_id == "TEST_REG_4"

    # 5) 시/도 + 구 조합 테스트: '경기도' + '분당구' -> l4 단독 검색
    res_combo = service.search_listings(ListingFilterParams(sido="경기도", district="분당구"))
    assert res_combo.total_count == 1
    assert res_combo.items[0].external_listing_id == "TEST_REG_4"
