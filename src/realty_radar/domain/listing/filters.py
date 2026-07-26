"""v2 keyset 검색에 필요한 최소 필터 계약."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Iterable


_DIRECTION_CODES = {
    "남": 1,
    "남향": 1,
    "남동": 2,
    "남동향": 2,
    "동": 3,
    "동향": 3,
    "북동": 4,
    "북동향": 4,
    "북": 5,
    "북향": 5,
    "북서": 6,
    "북서향": 6,
    "서": 7,
    "서향": 7,
    "남서": 8,
    "남서향": 8,
}
_FLOOR_BANDS = {
    "저": 1,
    "저층": 1,
    "중": 2,
    "중층": 2,
    "고": 3,
    "고층": 3,
    "탑": 4,
    "탑층": 4,
    "지하": 5,
}
_TRADE_TYPE_CODES = {"SALE": 1, "JEONSE": 2, "MONTHLY_RENT": 3, "SHORT_TERM": 4}


@dataclass(slots=True)
class ListingSearchFilter:
    region_code: int | None = None
    sido_code: int | None = None
    sigungu_code: int | None = None
    complex_keyword: str | None = None
    trade_type: int | None = None
    trade_types: list[int] | None = None
    min_price: int | None = None
    max_price: int | None = None
    min_deposit: int | None = None
    max_deposit: int | None = None
    max_monthly_rent: int | None = None
    min_exclusive_area: Decimal | None = None
    max_exclusive_area: Decimal | None = None
    min_construction_year: int | None = None
    min_households: int | None = None
    recent_days: int | None = None
    mortgage_codes: list[int] | None = None
    exclude_unknown_mortgage: bool = False
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
        # v1 saved preferences used strings and included source-specific keys.
        # The v2 hot table uses the numeric parser codes and is SITE_A-only.
        copied["direction_codes"] = cls._code_values(
            copied.get("direction_codes", copied.get("directions")), _DIRECTION_CODES
        )
        copied["floor_bands"] = cls._code_values(
            copied.get("floor_bands", copied.get("floor_types", copied.get("floors"))), _FLOOR_BANDS
        )
        trade_values = copied.get("trade_types") or copied.get("trade_type")
        copied["trade_types"] = cls._code_values(trade_values, _TRADE_TYPE_CODES)
        if isinstance(copied.get("trade_type"), str):
            copied["trade_type"] = None
        if copied.get("min_price") is None:
            copied["min_price"] = copied.get("min_deposit")
        if copied.get("max_price") is None:
            copied["max_price"] = copied.get("max_deposit")
        copied["min_exclusive_area"] = (
            Decimal(str(copied["min_exclusive_area"])) if copied.get("min_exclusive_area") is not None else None
        )
        copied["max_exclusive_area"] = (
            Decimal(str(copied["max_exclusive_area"])) if copied.get("max_exclusive_area") is not None else None
        )
        allowed = {field_name for field_name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in copied.items() if key in allowed})

    @classmethod
    def _code_values(cls, value: object, names: dict[str, int]) -> list[int] | None:
        if value is None:
            return None
        if isinstance(value, (str, int)):
            value = [value]
        if not isinstance(value, Iterable):
            return None
        codes: list[int] = []
        for item in value:
            if isinstance(item, int) or str(item).strip().isdigit():
                codes.append(int(item))
            elif (code := names.get(str(item).replace(" ", "").strip())) is not None:
                codes.append(code)
        return list(dict.fromkeys(codes)) or None

    @property
    def min_area_x100(self) -> int | None:
        return self._area_x100(self.min_exclusive_area)

    @property
    def max_area_x100(self) -> int | None:
        return self._area_x100(self.max_exclusive_area)

    @staticmethod
    def _area_x100(value: Decimal | None) -> int | None:
        return None if value is None else int(value * 100)
