from dataclasses import dataclass
from decimal import Decimal

from realty_radar.constants import MortgageStatus, TransactionType


@dataclass
class ListingSearchFilter:
    """매물 검색 필터링 조건 DTO (고급 필터 속성 포함)."""

    region_keyword: str | None = None
    region_name: str | None = None
    complex_keyword: str | None = None

    transaction_type: TransactionType | None = None

    min_price: int | None = None
    max_price: int | None = None

    min_deposit: int | None = None
    max_deposit: int | None = None
    max_monthly_rent: int | None = None

    min_exclusive_area: Decimal | None = None
    max_exclusive_area: Decimal | None = None

    mortgage_status: MortgageStatus | None = None
    exclude_unknown_mortgage: bool = False

    min_construction_year: int | None = None
    min_households: int | None = None

    recent_days: int | None = None
    source_code: str | None = None

    only_eligible_loans: bool = False

    sort_by: str = "recent"  # recent (최신순), price_asc (가격낮은순), price_desc (가격높은순), area_desc (면적넓은순)
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        """SQL OFFSET 위치 계산."""
        return (self.page - 1) * self.page_size
