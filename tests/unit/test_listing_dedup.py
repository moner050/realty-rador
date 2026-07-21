from decimal import Decimal
from realty_radar.application.listing_dedup_service import ListingDedupService
from realty_radar.constants import TransactionType
from realty_radar.infrastructure.database.models import Listing


def test_listing_dedup_similarity_calculation():
    """타 사이트 동일 매물 가중치 점수 계산 테스트."""
    service = ListingDedupService(db=None)

    listing_a = Listing(
        id=1,
        source_id=1,
        external_listing_id="A-101",
        complex_id=10,
        transaction_type=TransactionType.SALE.value,
        sale_price=650_000_000,
        exclusive_area=Decimal("84.97"),
        floor_group="중",
        description="융자없음 올수리 확장형 남향 매물",
    )

    listing_b = Listing(
        id=2,
        source_id=2,  # 타 사이트
        external_listing_id="B-202",
        complex_id=10,  # 동일 단지 (+40)
        transaction_type=TransactionType.SALE.value,  # 동일 거래유형 (+10)
        sale_price=650_000_000,  # 동일 가격 (+15)
        exclusive_area=Decimal("84.97"),  # 동일 면적 (+15)
        floor_group="중",  # 동일 층 (+10)
        description="융자없음 올수리 확장형 남향 매물",  # 설명 유사 (+10)
    )

    score = service.calculate_similarity(listing_a, listing_b)
    assert score >= Decimal("90.00")
