import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.domain.listing.models import ListingFilterParams
from realty_radar.infrastructure.database.models import ApartmentComplex, Base, CrawlSource, Listing


@pytest.fixture(name="db_session")
def db_session_fixture():
    """지역 격리 테스트용 인메모리 DB 픽스처."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = Session()

    source = CrawlSource(code="SITE_A", name="네이버부동산", base_url="https://land.naver.com", adapter_name="site_a")
    session.add(source)
    session.commit()

    # 1. 서울 동대문구 매물 및 단지
    c1 = ApartmentComplex(official_name="답십리 래미안", normalized_name="답십리래미안", road_address="서울특별시 동대문구 답십리로 123")
    session.add(c1)
    session.commit()

    l1 = Listing(
        source_id=source.id,
        complex_id=c1.id,
        external_listing_id="SEOUL_DONGDAEMUN_01",
        source_url="http://example.com/1",
        complex_name_raw="답십리 래미안 101동",
        address_raw="서울특별시 동대문구 답십리동 100번지",
        transaction_type="SALE",
        sale_price=450_000_000,
        exclusive_area=84.95,
    )

    # 2. 경기도 안산시 매물 및 단지
    c2 = ApartmentComplex(official_name="안산 푸르지오", normalized_name="안산푸르지오", road_address="경기도 안산시 단원구 원시로 456")
    session.add(c2)
    session.commit()

    l2 = Listing(
        source_id=source.id,
        complex_id=c2.id,
        external_listing_id="GYEONGGI_ANSAN_01",
        source_url="http://example.com/2",
        complex_name_raw="원시동 푸르지오 105동",
        address_raw="경기도 안산시 단원구 원시동 200번지",
        transaction_type="SALE",
        sale_price=500_000_000,
        exclusive_area=59.95,
    )

    session.add_all([l1, l2])
    session.commit()

    try:
        yield session
    finally:
        session.close()


def test_region_filter_isolation(db_session):
    """서울특별시 동대문구 검색 시 경기도 안산시 매물이 철저히 차단되는지 검증."""
    service = ListingSearchService(db_session)

    # 서울특별시 동대문구 지역 필터 적용
    params = ListingFilterParams(region_name="서울특별시 동대문구")
    result = service.search_listings(params)

    assert result.total_count == 1
    assert result.items[0].external_listing_id == "SEOUL_DONGDAEMUN_01"
    assert "동대문구" in result.items[0].address_raw
    assert "안산시" not in result.items[0].address_raw


def test_policy_loan_and_region_filter_isolation(db_session):
    """정책대출 가능 매물 필터(only_eligible_loans=True)와 서울특별시 동대문구 지역 필터 동시 적용 시 격리 검증."""
    from realty_radar.domain.loan.entities import ApplicantProfile

    service = ListingSearchService(db_session)
    applicant = ApplicantProfile(is_homeless=True, annual_income=50_000_000, net_assets=500_000_000)

    params = ListingFilterParams(region_name="서울특별시 동대문구", only_eligible_loans=True)
    result = service.search_listings(params, applicant=applicant)

    # 서울 동대문구 매물만 조회되고 안산시 매물은 철저히 차단되어야 함
    assert result.total_count == 1
    assert result.items[0].external_listing_id == "SEOUL_DONGDAEMUN_01"
    assert "안산시" not in result.items[0].address_raw
