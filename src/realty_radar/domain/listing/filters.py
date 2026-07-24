from dataclasses import dataclass
from decimal import Decimal

from realty_radar.constants import MortgageStatus, TransactionType


@dataclass
class ListingSearchFilter:
    """매물 검색 필터링 조건 DTO (고급 필터 속성 포함)."""

    region_keyword: str | None = None
    region_name: str | None = None
    complex_keyword: str | None = None
    sido: str | None = None
    city: str | None = None
    county: str | None = None
    district: str | None = None

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
    exclude_short_term: bool = True
    group_by_complex: bool = False

    sort_by: str = "recent"  # recent (최신순), price_asc (가격낮은순), price_desc (가격높은순), area_desc (면적넓은순)
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        """SQL OFFSET 위치 계산."""
        return (self.page - 1) * self.page_size

    def to_dict(self) -> dict:
        """JSON 직렬화용 Dict 변환."""
        return {
            "region_keyword": self.region_keyword,
            "region_name": self.region_name,
            "complex_keyword": self.complex_keyword,
            "sido": self.sido,
            "city": self.city,
            "county": self.county,
            "district": self.district,
            "transaction_type": self.transaction_type.value if self.transaction_type else None,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "min_deposit": self.min_deposit,
            "max_deposit": self.max_deposit,
            "max_monthly_rent": self.max_monthly_rent,
            "min_exclusive_area": str(self.min_exclusive_area) if self.min_exclusive_area is not None else None,
            "max_exclusive_area": str(self.max_exclusive_area) if self.max_exclusive_area is not None else None,
            "mortgage_status": self.mortgage_status.value if self.mortgage_status else None,
            "exclude_unknown_mortgage": self.exclude_unknown_mortgage,
            "min_construction_year": self.min_construction_year,
            "min_households": self.min_households,
            "recent_days": self.recent_days,
            "source_code": self.source_code,
            "only_eligible_loans": self.only_eligible_loans,
            "exclude_short_term": self.exclude_short_term,
            "group_by_complex": self.group_by_complex,
            "sort_by": self.sort_by,
            "page": self.page,
            "page_size": self.page_size,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ListingSearchFilter":
        """Dict 데이터로부터 ListingSearchFilter 객체 복원."""
        tt_val = data.get("transaction_type")
        ms_val = data.get("mortgage_status")
        min_ea = data.get("min_exclusive_area")
        max_ea = data.get("max_exclusive_area")

        return cls(
            region_keyword=data.get("region_keyword"),
            region_name=data.get("region_name"),
            complex_keyword=data.get("complex_keyword"),
            sido=data.get("sido"),
            city=data.get("city"),
            county=data.get("county"),
            district=data.get("district"),
            transaction_type=TransactionType(tt_val) if tt_val else None,
            min_price=data.get("min_price"),
            max_price=data.get("max_price"),
            min_deposit=data.get("min_deposit"),
            max_deposit=data.get("max_deposit"),
            max_monthly_rent=data.get("max_monthly_rent"),
            min_exclusive_area=Decimal(str(min_ea)) if min_ea is not None else None,
            max_exclusive_area=Decimal(str(max_ea)) if max_ea is not None else None,
            mortgage_status=MortgageStatus(ms_val) if ms_val else None,
            exclude_unknown_mortgage=data.get("exclude_unknown_mortgage", False),
            min_construction_year=data.get("min_construction_year"),
            min_households=data.get("min_households"),
            recent_days=data.get("recent_days"),
            source_code=data.get("source_code"),
            only_eligible_loans=data.get("only_eligible_loans", False),
            exclude_short_term=data.get("exclude_short_term", True),
            group_by_complex=data.get("group_by_complex", False),
            sort_by=data.get("sort_by", "price_asc"),
            page=data.get("page", 1),
            page_size=data.get("page_size", 20),
        )
