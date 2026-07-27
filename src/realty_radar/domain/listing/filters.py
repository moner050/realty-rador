"""v2 keyset 검색에 필요한 최소 필터 계약."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from realty_radar.crawler.adapters.site_a.region_codes import SIDO_CODES, resolve_cortarno


class ListingSearchValidationError(ValueError):
    """Raised when a listing search input cannot be safely evaluated."""


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
_TRADE_TYPE_CODES = {
    "SALE": 1,
    "매매": 1,
    "JEONSE": 2,
    "전세": 2,
    "MONTHLY_RENT": 3,
    "월세": 3,
    "SHORT_TERM": 4,
    "단기임대": 4,
}
_MORTGAGE_CODES = {
    "UNKNOWN": 0,
    "정보미상": 0,
    "EXPLICIT_NONE": 1,
    "융자없음": 1,
    "융자금없음": 1,
    "EXPLICIT_EXISTS": 2,
    "융자있음": 2,
    "융자금있음": 2,
}


@dataclass(slots=True)
class ListingSearchFilter:
    region_code: int | None = None
    sido_code: int | None = None
    sigungu_code: int | None = None
    sigungu_codes: list[int] | None = None
    invalid_municipality: bool = False
    complex_id: int | None = None
    complex_keyword: str | None = None
    trade_type: int | None = None
    trade_types: list[int] | None = None
    min_price: int | None = None
    max_price: int | None = None
    min_deposit: int | None = None
    max_deposit: int | None = None
    max_monthly_rent: int | None = None
    direct_trade_only: bool = False
    safe_lessor_hug_only: bool = False
    min_room_count: int | None = None
    min_bathroom_count: int | None = None
    parking_possible_only: bool = False
    min_parking_per_household: Decimal | None = None
    max_monthly_management_cost: int | None = None
    move_in_by: date | None = None
    max_subway_walk_minutes: int | None = None
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

    def __post_init__(self) -> None:
        if self.sigungu_codes is not None:
            self.sigungu_codes = sorted({int(code) for code in self.sigungu_codes}) or None

    def fingerprint_values(self) -> dict[str, object]:
        values = asdict(self)
        values.pop("cursor", None)
        values.pop("page_size", None)
        return values

    def to_dict(self) -> dict[str, object]:
        values = asdict(self)
        values.pop("complex_id", None)
        for key in ("min_exclusive_area", "max_exclusive_area", "min_parking_per_household"):
            if values[key] is not None:
                values[key] = str(values[key])
        if values["move_in_by"] is not None:
            values["move_in_by"] = values["move_in_by"].isoformat()
        values["cursor"] = None
        return values

    @classmethod
    def from_dict(cls, values: dict[str, object]) -> "ListingSearchFilter":
        copied = dict(values)
        # v1 saved preferences used strings and included source-specific keys.
        # The v2 hot table uses the numeric parser codes and is SITE_A-only.
        copied["direction_codes"] = cls._code_values(
            cls._legacy_value(copied, "direction_codes", "directions", "direction"), _DIRECTION_CODES
        )
        copied["floor_bands"] = cls._code_values(
            cls._legacy_value(copied, "floor_bands", "floor_types", "floors", "floor"), _FLOOR_BANDS
        )
        copied["mortgage_codes"] = cls._code_values(
            cls._legacy_value(copied, "mortgage_codes", "mortgage_status"), _MORTGAGE_CODES
        )
        trade_values = cls._legacy_value(copied, "trade_types", "trade_type", "transaction_type")
        copied["trade_types"] = cls._code_values(trade_values, _TRADE_TYPE_CODES)
        if isinstance(copied.get("trade_type"), str):
            copied["trade_type"] = None
        cls._migrate_region(copied)
        copied["sigungu_codes"] = cls._int_values(copied.get("sigungu_codes"))
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
        copied["min_parking_per_household"] = (
            Decimal(str(copied["min_parking_per_household"]))
            if copied.get("min_parking_per_household") is not None
            else None
        )
        copied["move_in_by"] = cls._date_value(copied.get("move_in_by"))
        for key in (
            "min_room_count",
            "min_bathroom_count",
            "max_monthly_management_cost",
            "max_subway_walk_minutes",
        ):
            copied[key] = cls._int_value(copied.get(key))
        for key in ("direct_trade_only", "safe_lessor_hug_only", "parking_possible_only"):
            copied[key] = cls._bool_value(copied.get(key), False)
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

    @staticmethod
    def _int_values(value: object) -> list[int] | None:
        if value is None:
            return None
        if isinstance(value, (str, int)):
            value = [value]
        if not isinstance(value, Iterable):
            return None
        values = [int(item) for item in value if str(item).strip().isdigit()]
        return sorted(set(values)) or None

    @staticmethod
    def _legacy_value(values: dict[str, object], *keys: str) -> object:
        for key in keys:
            value = values.get(key)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _migrate_region(values: dict[str, object]) -> None:
        if any(values.get(key) not in (None, "") for key in ("region_code", "sido_code", "sigungu_code")):
            return
        sido = str(values.get("sido") or "").strip()
        city = str(values.get("city") or "").strip()
        county = str(values.get("county") or "").strip()
        district = str(values.get("district") or "").strip()
        region_name = str(values.get("region_name") or values.get("region") or "").strip()
        names = [
            " ".join(part for part in (sido, city, district or county) if part),
            " ".join(part for part in (sido, city or district or county) if part),
            region_name,
            district or county or city or sido,
        ]
        for name in names:
            code = resolve_cortarno(name) if name else None
            if not code or code == "ALL_METRO":
                continue
            numeric = int(code)
            if code in SIDO_CODES.values():
                values["sido_code"] = numeric // 100_000_000
            else:
                values["sigungu_code"] = numeric // 100_000
                values["sido_code"] = numeric // 100_000_000
            return

    @staticmethod
    def _int_value(value: object) -> int | None:
        try:
            return int(str(value)) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _bool_value(value: object, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return default

    @staticmethod
    def _date_value(value: object) -> date | None:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
        return None

    @property
    def min_area_x100(self) -> int | None:
        return self._area_x100(self.min_exclusive_area)

    @property
    def max_area_x100(self) -> int | None:
        return self._area_x100(self.max_exclusive_area)

    @property
    def min_parking_per_household_x100(self) -> int | None:
        return self._area_x100(self.min_parking_per_household)

    @staticmethod
    def _area_x100(value: Decimal | None) -> int | None:
        return None if value is None else int(value * 100)
