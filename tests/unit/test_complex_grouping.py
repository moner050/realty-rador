from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from realty_radar.application.listing_search_service import ListingSearchService, format_korean_money
from realty_radar.domain.listing.models import ListingFilterParams
from realty_radar.infrastructure.database.models import ApartmentComplex, Listing


def test_format_korean_money():
    assert format_korean_money(550_000_000) == "5억 5,000만 원"
    assert format_korean_money(600_000_000) == "6억 원"
    assert format_korean_money(35_000_000) == "3,500만 원"


def test_group_by_complex_search_results():
    mock_db = MagicMock()
    
    # 2개 아파트 단지 매물 모킹
    l1 = MagicMock(spec=Listing)
    l1.id = 1
    l1.complex_id = 100
    l1.complex_name_raw = "삼성 아파트 101동"
    l1.price_deposit = Decimal("550000000")
    l1.price_monthly = 0
    l1.status = "ACTIVE"
    l1.is_short_term = False
    l1.address_raw = "서울시 관악구 봉천동"
    l1.sido = "서울특별시"
    l1.sigungu = "관악구"
    l1.total_households = 25
    l1.construction_year = 1974
    l1.complex = MagicMock(spec=ApartmentComplex, official_name="삼성", total_households=25, construction_year=1974)

    l2 = MagicMock(spec=Listing)
    l2.id = 2
    l2.complex_id = 100
    l2.complex_name_raw = "삼성 아파트 102동"
    l2.price_deposit = Decimal("600000000")
    l2.price_monthly = 0
    l2.status = "ACTIVE"
    l2.is_short_term = False
    l2.address_raw = "서울시 관악구 봉천동"
    l2.sido = "서울특별시"
    l2.sigungu = "관악구"
    l2.total_households = 25
    l2.construction_year = 1974
    l2.complex = l1.complex

    mock_query = MagicMock()
    mock_query.where.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.subquery.return_value = mock_query
    mock_query.unique.return_value.all.return_value = [l1, l2]

    mock_db.scalar.return_value = 2
    mock_db.scalars.return_value = mock_query

    service = ListingSearchService(mock_db)
    params = ListingFilterParams(group_by_complex=True, max_price=Decimal("600000000"))

    result = service.search_listings(params)

    assert result.is_grouped is True
    assert len(result.grouped_items) == 1
    
    grp = result.grouped_items[0]
    assert grp.complex_name == "삼성"
    assert grp.min_price == Decimal("550000000")
    assert grp.max_price == Decimal("600000000")
    assert grp.price_range_str == "5억 5,000만 원 ~ 6억 원"
    assert grp.listing_count == 2


def test_group_by_complex_unmatched_dong_stripping():
    """complex_id가 None이고 동 번호(105동, 102동)가 붙은 매물들이 '현대' 그룹으로 통합되는지 검증."""
    mock_db = MagicMock()

    l1 = MagicMock(spec=Listing)
    l1.id = 101
    l1.complex_id = None
    l1.complex_name_raw = "현대 105동"
    l1.price_deposit = Decimal("480000000")
    l1.price_monthly = 0
    l1.status = "ACTIVE"
    l1.is_short_term = False
    l1.address_raw = "서울특별시 관악구 신림동"
    l1.sido = "서울특별시"
    l1.sigungu = "관악구"
    l1.total_households = 336
    l1.construction_year = 1991
    l1.complex = None

    l2 = MagicMock(spec=Listing)
    l2.id = 102
    l2.complex_id = None
    l2.complex_name_raw = "현대 102동"
    l2.price_deposit = Decimal("480000000")
    l2.price_monthly = 0
    l2.status = "ACTIVE"
    l2.is_short_term = False
    l2.address_raw = "서울특별시 관악구 신림동"
    l2.sido = "서울특별시"
    l2.sigungu = "관악구"
    l2.total_households = 336
    l2.construction_year = 1991
    l2.complex = None

    l3 = MagicMock(spec=Listing)
    l3.id = 103
    l3.complex_id = None
    l3.complex_name_raw = "현대 105동"
    l3.price_deposit = Decimal("490000000")
    l3.price_monthly = 0
    l3.status = "ACTIVE"
    l3.is_short_term = False
    l3.address_raw = "서울특별시 관악구 신림동"
    l3.sido = "서울특별시"
    l3.sigungu = "관악구"
    l3.total_households = 336
    l3.construction_year = 1991
    l3.complex = None

    mock_query = MagicMock()
    mock_query.where.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.subquery.return_value = mock_query
    mock_query.unique.return_value.all.return_value = [l1, l2, l3]

    mock_db.scalar.return_value = 3
    mock_db.scalars.return_value = mock_query

    service = ListingSearchService(mock_db)
    params = ListingFilterParams(group_by_complex=True)

    result = service.search_listings(params)

    assert result.is_grouped is True
    assert len(result.grouped_items) == 1

    grp = result.grouped_items[0]
    assert grp.complex_name == "현대"
    assert grp.min_price == Decimal("480000000")
    assert grp.max_price == Decimal("490000000")
    assert grp.price_range_str == "4억 8,000만 원 ~ 4억 9,000만 원"
    assert grp.listing_count == 3
