from decimal import Decimal
from realty_radar.constants import MortgageStatus, TransactionType
from realty_radar.domain.listing.filters import ListingSearchFilter


def test_listing_search_filter_offset_calculation():
    """ListingSearchFilter 페이징 및 기본값 검증."""
    filters = ListingSearchFilter(
        page=3,
        page_size=15,
        transaction_type=TransactionType.SALE,
        min_price=500_000_000,
        mortgage_status=MortgageStatus.EXPLICIT_NONE,
        min_exclusive_area=Decimal("59.5"),
    )

    assert filters.offset == 30
    assert filters.transaction_type == TransactionType.SALE
    assert filters.min_price == 500_000_000
    assert filters.mortgage_status == MortgageStatus.EXPLICIT_NONE
    assert filters.min_exclusive_area == Decimal("59.5")
