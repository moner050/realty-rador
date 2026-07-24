from decimal import Decimal
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.constants import TransactionType
from realty_radar.web.routes.settings import load_user_search_filter, save_user_search_filter


def test_user_isolated_search_filter_persistence(tmp_path, monkeypatch):
    """로그인 사용자 계정별 검색 필터 독립 영구 보존 테스트."""
    profiles_dir = tmp_path / "user_profiles"
    monkeypatch.setattr("realty_radar.web.routes.settings.PROFILES_DIR", profiles_dir)

    # 1. User A 검색 필터 저장
    filter_a = ListingSearchFilter(
        sido="경기도",
        city="과천시",
        transaction_type=TransactionType.SALE,
        min_price=500_000_000,
        max_price=1_500_000_000,
        min_exclusive_area=Decimal("59.0"),
    )
    save_user_search_filter(filter_a, username="user_a")

    # 2. User B 검색 필터 저장 (다른 조건)
    filter_b = ListingSearchFilter(
        sido="서울특별시",
        district="강남구",
        transaction_type=TransactionType.JEONSE,
        max_deposit=800_000_000,
    )
    save_user_search_filter(filter_b, username="user_b")

    # 3. 사용자별 개별 복원 검증
    loaded_a = load_user_search_filter("user_a")
    loaded_b = load_user_search_filter("user_b")

    assert loaded_a is not None
    assert loaded_a.sido == "경기도"
    assert loaded_a.city == "과천시"
    assert loaded_a.transaction_type == TransactionType.SALE
    assert loaded_a.min_price == 500_000_000
    assert loaded_a.min_exclusive_area == Decimal("59.0")

    assert loaded_b is not None
    assert loaded_b.sido == "서울특별시"
    assert loaded_b.district == "강남구"
    assert loaded_b.transaction_type == TransactionType.JEONSE
    assert loaded_b.max_deposit == 800_000_000
