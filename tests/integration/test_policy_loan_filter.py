import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.domain.listing.models import ListingFilterParams
from realty_radar.domain.loan.entities import ApplicantProfile
from realty_radar.infrastructure.database.models import ApartmentComplex, Base, CrawlSource, Listing


@pytest.fixture(name="db_session")
def db_session_fixture():
    """정책대출 필터 전용 테스트 인메모리 DB 픽스처."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = Session()

    source = CrawlSource(code="SITE_A", name="네이버부동산", base_url="https://land.naver.com", adapter_name="site_a")
    session.add(source)
    session.commit()

    # 단지 생성
    c1 = ApartmentComplex(official_name="테스트 단지", normalized_name="테스트단지", road_address="서울특별시 동대문구")
    session.add(c1)
    session.commit()

    # 1. 디딤돌 적격 매물 (매매, 5억 이하, 면적 85㎡ 이하)
    l1 = Listing(
        source_id=source.id,
        complex_id=c1.id,
        external_listing_id="ELIGIBLE_SALE",
        source_url="http://example.com/1",
        complex_name_raw="매매 적격",
        address_raw="서울특별시 동대문구",
        transaction_type="SALE",
        sale_price=450_000_000,
        exclusive_area=84.9,
    )

    # 2. 디딤돌 부적격 매물 (매매, 7억 - 일반 5억 한도 초과)
    l2 = Listing(
        source_id=source.id,
        complex_id=c1.id,
        external_listing_id="INELIGIBLE_SALE_PRICE",
        source_url="http://example.com/2",
        complex_name_raw="매매 부적격 가격",
        address_raw="서울특별시 동대문구",
        transaction_type="SALE",
        sale_price=700_000_000,
        exclusive_area=84.9,
    )

    # 3. 버팀목 적격 매물 (전세, 2억 5천, 면적 85㎡ 이하)
    l3 = Listing(
        source_id=source.id,
        complex_id=c1.id,
        external_listing_id="ELIGIBLE_RENT",
        source_url="http://example.com/3",
        complex_name_raw="전세 적격",
        address_raw="서울특별시 동대문구",
        transaction_type="JEONSE",
        deposit=250_000_000,
        exclusive_area=59.9,
    )

    session.add_all([l1, l2, l3])
    session.commit()

    try:
        yield session
    finally:
        session.close()


def test_only_eligible_loans_filter(db_session):
    """무주택자 소득 5500만원인 일반 신청자의 대출 필터링 검증."""
    service = ListingSearchService(db_session)
    applicant = ApplicantProfile(
        is_homeless=True,
        annual_income=55_000_000,  # 디딤돌 통과(일반 6000이하), 버팀목 탈락(일반 5000이하)
        net_assets=200_000_000,
        is_newlywed=False,
    )

    # 필터 적용
    params = ListingFilterParams(only_eligible_loans=True)
    result = service.search_listings(params, applicant=applicant)

    # 디딤돌(SALE)은 소득 한도(6000만) 이하이므로 ELIGIBLE_SALE 매물만 반환되어야 함.
    # 버팀목(JEONSE)은 소득 한도(5000만) 초과로 비적격이므로 ELIGIBLE_RENT는 제외됨.
    assert result.total_count == 1
    assert result.items[0].external_listing_id == "ELIGIBLE_SALE"


def test_promissory_note_person_count_filter(db_session):
    """차용증 작성 가능 인원수 1명(2.17억 자금 추가) 지정 시 개인 자격 대출 필터링 검증."""
    service = ListingSearchService(db_session)
    applicant = ApplicantProfile(
        is_homeless=True,
        annual_income=45_000_000,  # 개인 소득 디딤돌(6000만) & 버팀목(5000만) 모두 적격!
        net_assets=50_000_000,      # 순자산 5,000만 원
        use_promissory_note=True,
        promissory_note_person_count=1,  # 차용증 1명 (2억 1,700만 원) -> 총 자본금 2억 6,700만 원!
        is_newlywed=False,
    )

    params = ListingFilterParams(only_eligible_loans=True)
    result = service.search_listings(params, applicant=applicant)

    ext_ids = [item.external_listing_id for item in result.items]
    assert "ELIGIBLE_SALE" in ext_ids
    assert "ELIGIBLE_RENT" in ext_ids


def test_dynamic_promissory_notes_sum_filter(db_session):
    """동적 차용증 여러 명(아버지 1.5억, 어머니 1.5억 -> 3억 자금) 추가 시 총 자본금 계산 검증."""
    from realty_radar.domain.loan.entities import PromissoryNoteEntry

    service = ListingSearchService(db_session)
    applicant = ApplicantProfile(
        is_homeless=True,
        annual_income=45_000_000,
        net_assets=50_000_000,
        use_promissory_note=True,
        promissory_notes=[
            PromissoryNoteEntry(name="아버지", amount=150_000_000),
            PromissoryNoteEntry(name="어머니", amount=150_000_000),
        ],
        is_newlywed=False,
    )

    # 총 자본금 = 5000만 + 3억 = 3.5억
    assert applicant.promissory_note_total == 300_000_000
    assert applicant.total_capital == 350_000_000

    params = ListingFilterParams(only_eligible_loans=True)
    result = service.search_listings(params, applicant=applicant)

    ext_ids = [item.external_listing_id for item in result.items]
    assert "ELIGIBLE_SALE" in ext_ids
    assert "ELIGIBLE_RENT" in ext_ids

