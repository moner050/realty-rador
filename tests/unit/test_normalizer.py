from decimal import Decimal
from realty_radar.constants import MortgageStatus, TransactionType
from realty_radar.crawler.adapters.site_a.normalizer import SiteANormalizer
from realty_radar.crawler.base.models import RawListing


def test_normalizer_korean_money():
    """한글 금액 정수(원) 변환 테스트."""
    normalizer = SiteANormalizer()

    assert normalizer.parse_korean_money("6억 5,000만 원") == 650_000_000
    assert normalizer.parse_korean_money("6억 5,000") == 650_000_000
    assert normalizer.parse_korean_money("전세 3억") == 300_000_000
    assert normalizer.parse_korean_money("4,200만 원") == 42_000_000


def test_normalizer_price_and_floor_and_mortgage():
    """매물 데이터 종합 정규화 테스트."""
    normalizer = SiteANormalizer()

    raw = RawListing(
        source_code="SITE_A",
        external_listing_id="EX-001",
        source_url="https://site-a.com/item/001",
        price_raw="매매 8억 2,000",
        area_raw="공급 110㎡ / 전용 84.97㎡",
        floor_raw="중/20층",
        description_raw="융자없음 깨끗한 로얄층 매물",
    )

    norm = normalizer.normalize(raw)

    assert norm.transaction_type == TransactionType.SALE
    assert norm.sale_price == 820_000_000
    assert norm.exclusive_area == Decimal("84.97")
    assert norm.supply_area == Decimal("110")
    assert norm.floor_group == "중"
    assert norm.total_floor == 20
    assert norm.mortgage_status == MortgageStatus.EXPLICIT_NONE
