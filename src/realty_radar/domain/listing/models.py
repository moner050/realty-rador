from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterator, Optional

from realty_radar.constants import MortgageStatus, SortBy, TransactionType


@dataclass
class RawListingDTO:
    """수집 직후 원본 매물 DTO."""

    source_code: str
    external_listing_id: str
    source_url: str
    complex_name_raw: str
    address_raw: str | None
    price_raw: str
    area_raw: str | None
    floor_raw: str | None
    description_raw: str | None
    collected_at: datetime


@dataclass
class ListingFilterParams:
    """매물 검색 필터링 조건 전달 객체."""

    complex_keyword: Optional[str] = None
    region_name: Optional[str] = None
    transaction_type: Optional[TransactionType] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    min_exclusive_area: Optional[Decimal] = None
    max_exclusive_area: Optional[Decimal] = None
    min_construction_year: Optional[int] = None
    min_households: Optional[int] = None
    mortgage_status: Optional[MortgageStatus] = None
    exclude_unknown_mortgage: bool = False
    recent_days: Optional[int] = None
    sort_by: SortBy = SortBy.RECENT
    limit: int = 50
    offset: int = 0
    page: int = 1
    page_size: int = 20
    region_keyword: Optional[str] = None
    source_code: Optional[str] = None
    only_eligible_loans: bool = False

    def __post_init__(self):
        if self.region_keyword and not self.region_name:
            self.region_name = self.region_keyword


# 하위 호환 클래스 별칭
ListingSearchFilter = ListingFilterParams


class SearchResult:
    """검색 결과 객체 (객체 속성 접근 .items, .total_count, .total_pages 및 (items, count) 언패킹 모두 지원)."""

    def __init__(self, items: list[Any], total_count: int, page: int = 1, page_size: int = 20):
        self.items = items
        self.total_count = total_count
        self.page = max(1, page)
        self.page_size = max(1, page_size)

    @property
    def total_pages(self) -> int:
        """총 페이지 수 계산."""
        if self.total_count <= 0 or self.page_size <= 0:
            return 1
        return max(1, (self.total_count + self.page_size - 1) // self.page_size)

    @property
    def has_prev(self) -> bool:
        """이전 페이지 존재 여부."""
        return self.page > 1

    @property
    def has_next(self) -> bool:
        """다음 페이지 존재 여부."""
        return self.page < self.total_pages

    def __iter__(self) -> Iterator[Any]:
        return iter((self.items, self.total_count))

    def __getitem__(self, index: int) -> Any:
        return (self.items, self.total_count)[index]

    def __len__(self) -> int:
        return 2
