from decimal import Decimal
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_upsert_service import ListingUpsertService
from realty_radar.constants import ListingStatus, MortgageStatus, TransactionType
from realty_radar.crawler.base.models import NormalizedListing
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
    """StaticPool 기반 인메모리 DB 세션 픽스처."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def test_listing_upsert_and_snapshot_creation(db_session):
    """매물 Upsert 및 가격 변경 스냅샷 생성 통합 테스트."""
    service = ListingUpsertService(db_session)

    item1 = NormalizedListing(
        source_code="SITE_A",
        external_listing_id="TEST-999",
        source_url="https://site-a.com/item/999",
        transaction_type=TransactionType.SALE,
        complex_name_raw="테스트아파트 101동",
        sale_price=650_000_000,
        exclusive_area=Decimal("84.97"),
        mortgage_status=MortgageStatus.EXPLICIT_NONE,
        listing_status=ListingStatus.ACTIVE,
    )

    # 1. 신규 등록
    listing, is_created = service.upsert_listing(item1)
    assert is_created is True
    assert listing.sale_price == 650_000_000

    # 스냅샷 1건 생성 확인
    snapshots = db_session.scalars(select(ListingSnapshot).where(ListingSnapshot.listing_id == listing.id)).all()
    assert len(snapshots) == 1
    assert snapshots[0].sale_price == 650_000_000

    # 2. 동일 조건 재수집 (가격 변경 없음)
    listing_updated, is_created2 = service.upsert_listing(item1)
    assert is_created2 is False
    snapshots_after_no_change = db_session.scalars(select(ListingSnapshot).where(ListingSnapshot.listing_id == listing.id)).all()
    assert len(snapshots_after_no_change) == 1  # 스냅샷 추가되지 않음

    # 3. 가격 인하 변경 수집
    item2 = NormalizedListing(
        source_code="SITE_A",
        external_listing_id="TEST-999",
        source_url="https://site-a.com/item/999",
        transaction_type=TransactionType.SALE,
        complex_name_raw="테스트아파트 101동",
        sale_price=620_000_000,  # 3천만원 인하
        exclusive_area=Decimal("84.97"),
        mortgage_status=MortgageStatus.EXPLICIT_NONE,
        listing_status=ListingStatus.ACTIVE,
    )

    listing_lowered, is_created3 = service.upsert_listing(item2)
    assert is_created3 is False
    assert listing_lowered.sale_price == 620_000_000

    # 스냅샷 2건 생성 확인
    snapshots_after_lowered = db_session.scalars(select(ListingSnapshot).where(ListingSnapshot.listing_id == listing.id)).all()
    assert len(snapshots_after_lowered) == 2
    assert snapshots_after_lowered[1].sale_price == 620_000_000
