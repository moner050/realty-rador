"""v2 keyset 검색에 필요한 최소 필터 계약."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal


@dataclass(slots=True)
class ListingSearchFilter:
    region_code: int | None = None
    sido_code: int | None = None
    sigungu_code: int | None = None
    complex_keyword: str | None = None
    trade_type: int | None = None
    min_price: int | None = None
    max_price: int | None = None
    min_deposit: int | None = None
    max_deposit: int | None = None
    max_monthly_rent: int | None = None
    min_exclusive_area: Decimal | None = None
    max_exclusive_area: Decimal | None = None
    min_construction_year: int | None = None
    min_households: int | None = None
    mortgage_codes: list[int] | None = None
    direction_codes: list[int] | None = None
    floor_bands: list[int] | None = None
    exclude_first_floor: bool = False
    exclude_short_term: bool = True
    only_eligible_loans: bool = False
    group_by_complex: bool = False
    sort_by: str = "price_asc"
    page_size: int = 20
    cursor: str | None = None

    def fingerprint_values(self) -> dict[str, object]:
        values = asdict(self)
        values.pop("cursor", None)
        values.pop("page_size", None)
        return values

    def to_dict(self) -> dict[str, object]:
        values = asdict(self)
        for key in ("min_exclusive_area", "max_exclusive_area"):
            if values[key] is not None:
                values[key] = str(values[key])
        values["cursor"] = None
        return values

    @classmethod
    def from_dict(cls, values: dict[str, object]) -> "ListingSearchFilter":
        copied = dict(values)
        copied["min_exclusive_area"] = (
            Decimal(str(copied["min_exclusive_area"])) if copied.get("min_exclusive_area") is not None else None
        )
        copied["max_exclusive_area"] = (
            Decimal(str(copied["max_exclusive_area"])) if copied.get("max_exclusive_area") is not None else None
        )
        allowed = {field_name for field_name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in copied.items() if key in allowed})

    @property
    def min_area_x100(self) -> int | None:
        return self._area_x100(self.min_exclusive_area)

    @property
    def max_area_x100(self) -> int | None:
        return self._area_x100(self.max_exclusive_area)

    @staticmethod
    def _area_x100(value: Decimal | None) -> int | None:
        return None if value is None else int(value * 100)
