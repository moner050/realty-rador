from datetime import datetime
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_dedup_service import ListingDedupService
from realty_radar.constants import MortgageStatus, TransactionType
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

    s1 = CrawlSource(code="SITE_A", name="사이트A", base_url="https://site-a.com", adapter_name="adapter_a")
    s2 = CrawlSource(code="SITE_B", name="사이트B", base_url="https://site-b.com", adapter_name="adapter_b")
    session.add_all([s1, s2])

    c1 = ApartmentComplex(official_name="여의도 시범아파트", normalized_name="여의도시범아파트")
    session.add(c1)
    session.flush()

    # SITE_A 매물
    la = Listing(
        source_id=s1.id,
        complex_id=c1.id,
        external_listing_id="A-001",
        source_url="https://site-a.com/1",
        complex_name_raw="여의도 시범아파트 1동",
        transaction_type=TransactionType.SALE.value,
        sale_price=650_000_000,
        exclusive_area=Decimal("84.97"),
        floor_group="중",
        mortgage_status=MortgageStatus.EXPLICIT_NONE.value,
        listing_status="ACTIVE",
        first_seen_at=datetime.now(),
        last_seen_at=datetime.now(),
    )

    # SITE_B 매물 (동일 조건)
    lb = Listing(
        source_id=s2.id,
        complex_id=c1.id,
        external_listing_id="B-001",
        source_url="https://site-b.com/1",
        complex_name_raw="여의도 시범아파트 1동",
        transaction_type=TransactionType.SALE.value,
        sale_price=650_000_000,
        exclusive_area=Decimal("84.97"),
        floor_group="중",
        mortgage_status=MortgageStatus.EXPLICIT_NONE.value,
        listing_status="ACTIVE",
        first_seen_at=datetime.now(),
        last_seen_at=datetime.now(),
    )

    session.add_all([la, lb])
    session.commit()

    try:
        yield session
    finally:
        session.close()


def test_find_duplicates_service(db_session):
    """타 사이트 수집 매물간 동일 매물 추정 통합 테스트."""
    service = ListingDedupService(db_session)

    # SITE_A 매물 기준 중복 검색
    results = service.find_duplicates_for_listing(target_listing_id=1)

    assert len(results) == 1
    assert results[0].matched_listing_id == 2
    assert results[0].similarity_score >= Decimal("85.00")
    assert results[0].is_duplicate is True
