"""JOIN/COUNT/OFFSET 없는 v2 listing keyset search."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from realty_radar.config import settings
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.domain.listing.models import ComplexGroupItem, SearchResult
from realty_radar.infrastructure.database.models import ComplexCurrent, ListingCurrent


LIFECYCLE_ACTIVE = 1


@dataclass(frozen=True, slots=True)
class _SortSpec:
    name: str
    descending: bool
    value_kind: str


SORT_SPECS = {
    "price_asc": _SortSpec("primary_price", False, "int"),
    "price_desc": _SortSpec("primary_price", True, "int"),
    "recent": _SortSpec("first_seen_at", True, "datetime"),
    "area_asc": _SortSpec("exclusive_area_x100", False, "int"),
    "area_desc": _SortSpec("exclusive_area_x100", True, "int"),
    "households_asc": _SortSpec("household_count", False, "int"),
    "households_desc": _SortSpec("household_count", True, "int"),
}


class ListingSearchService:
    def __init__(self, db: Session, *, cursor_secret: str | None = None):
        self.db = db
        self._cursor_secret = (cursor_secret or settings.secret_key).encode("utf-8")

    def search_listings(self, filters: ListingSearchFilter, applicant: Any = None) -> SearchResult:
        self._validate(filters)
        return self._search_grouped(filters) if filters.group_by_complex else self._search_rows(filters)

    def _search_rows(self, filters: ListingSearchFilter) -> SearchResult:
        sort = self._sort(filters)
        statement = self._filtered_rows(filters)
        sort_column = getattr(ListingCurrent, sort.name)
        anchor = self._decode_cursor(filters, sort, grouped=False)
        if anchor is not None:
            statement = self._apply_keyset(statement, sort_column, ListingCurrent.article_id, sort.descending, anchor)
        statement = statement.order_by(
            sort_column.desc() if sort.descending else sort_column.asc(),
            ListingCurrent.article_id.desc() if sort.descending else ListingCurrent.article_id.asc(),
        ).limit(filters.page_size + 1)
        rows = list(self.db.scalars(statement).all())
        has_more = len(rows) > filters.page_size
        items = rows[: filters.page_size]
        next_cursor = self._encode_cursor(filters, sort, items[-1], items[-1].article_id, grouped=False) if has_more else None
        return SearchResult(items=items, next_cursor=next_cursor, has_more=has_more)

    def _search_grouped(self, filters: ListingSearchFilter) -> SearchResult:
        sort = self._sort(filters)
        filtered = self._filtered_rows(filters).cte("filtered_listing")
        grouped = (
            select(
                filtered.c.complex_id,
                func.min(filtered.c.primary_price).label("min_price"),
                func.max(filtered.c.primary_price).label("max_price"),
                func.max(filtered.c.first_seen_at).label("latest_seen_at"),
                func.min(filtered.c.exclusive_area_x100).label("min_area_x100"),
                func.max(filtered.c.exclusive_area_x100).label("max_area_x100"),
                func.max(filtered.c.household_count).label("household_count"),
                func.count().label("listing_count"),
            )
            .group_by(filtered.c.complex_id)
            .cte("grouped_complex")
        )
        sort_column_name = {
            "primary_price": "max_price" if sort.descending else "min_price",
            "first_seen_at": "latest_seen_at",
            "exclusive_area_x100": "max_area_x100" if sort.descending else "min_area_x100",
            "household_count": "household_count",
        }[sort.name]
        sort_column = getattr(grouped.c, sort_column_name)
        statement = select(grouped)
        anchor = self._decode_cursor(filters, sort, grouped=True)
        if anchor is not None:
            statement = self._apply_keyset(statement, sort_column, grouped.c.complex_id, sort.descending, anchor)
        statement = statement.order_by(
            sort_column.desc() if sort.descending else sort_column.asc(),
            grouped.c.complex_id.desc() if sort.descending else grouped.c.complex_id.asc(),
        ).limit(filters.page_size + 1)
        group_rows = list(self.db.execute(statement).mappings().all())
        has_more = len(group_rows) > filters.page_size
        selected = group_rows[: filters.page_size]
        if not selected:
            return SearchResult(items=[], next_cursor=None, has_more=False, grouped_items=[], is_grouped=True)

        complex_ids = [row["complex_id"] for row in selected]
        listing_rows = list(
            self.db.scalars(
                self._filtered_rows(filters)
                .where(ListingCurrent.complex_id.in_(complex_ids))
                .order_by(ListingCurrent.complex_id, ListingCurrent.primary_price, ListingCurrent.article_id)
            ).all()
        )
        rows_by_complex: dict[int, list[ListingCurrent]] = {complex_id: [] for complex_id in complex_ids}
        for listing in listing_rows:
            rows_by_complex[listing.complex_id].append(listing)
        groups: list[ComplexGroupItem] = []
        for row in selected:
            listings = rows_by_complex[row["complex_id"]]
            representative = listings[0]
            groups.append(
                ComplexGroupItem(
                    complex_id=row["complex_id"],
                    complex_name=representative.complex_name,
                    address=representative.address,
                    household_count=representative.household_count,
                    construction_year=representative.construction_year,
                    min_price=row["min_price"],
                    max_price=row["max_price"],
                    listing_count=row["listing_count"],
                    listings=listings,
                )
            )
        last = selected[-1]
        next_cursor = self._encode_cursor(
            filters,
            sort,
            last[sort_column_name],
            last["complex_id"],
            grouped=True,
        ) if has_more else None
        return SearchResult(
            items=listing_rows,
            next_cursor=next_cursor,
            has_more=has_more,
            grouped_items=groups,
            is_grouped=True,
        )

    def _filtered_rows(self, filters: ListingSearchFilter):
        statement = select(ListingCurrent).where(ListingCurrent.lifecycle == LIFECYCLE_ACTIVE)
        if filters.exclude_short_term:
            statement = statement.where(ListingCurrent.is_short_term.is_(False))
        for column, value in (
            (ListingCurrent.region_code, filters.region_code),
            (ListingCurrent.sido_code, filters.sido_code),
            (ListingCurrent.sigungu_code, filters.sigungu_code),
            (ListingCurrent.trade_type, filters.trade_type),
        ):
            if value is not None:
                statement = statement.where(column == value)
        if filters.min_price is not None:
            statement = statement.where(ListingCurrent.primary_price >= filters.min_price)
        if filters.max_price is not None:
            statement = statement.where(ListingCurrent.primary_price <= filters.max_price)
        if filters.min_deposit is not None:
            statement = statement.where(ListingCurrent.primary_price >= filters.min_deposit)
        if filters.max_deposit is not None:
            statement = statement.where(ListingCurrent.primary_price <= filters.max_deposit)
        if filters.max_monthly_rent is not None:
            statement = statement.where(ListingCurrent.monthly_rent <= filters.max_monthly_rent)
        if filters.min_area_x100 is not None:
            statement = statement.where(ListingCurrent.exclusive_area_x100 >= filters.min_area_x100)
        if filters.max_area_x100 is not None:
            statement = statement.where(ListingCurrent.exclusive_area_x100 <= filters.max_area_x100)
        if filters.min_construction_year is not None:
            statement = statement.where(ListingCurrent.construction_year >= filters.min_construction_year)
        if filters.min_households is not None:
            statement = statement.where(ListingCurrent.household_count >= filters.min_households)
        if filters.mortgage_codes:
            statement = statement.where(ListingCurrent.mortgage_code.in_(filters.mortgage_codes))
        if filters.direction_codes:
            statement = statement.where(ListingCurrent.direction_code.in_(filters.direction_codes))
        if filters.floor_bands:
            statement = statement.where(ListingCurrent.floor_band.in_(filters.floor_bands))
        if filters.exclude_first_floor:
            statement = statement.where(or_(ListingCurrent.floor_no.is_(None), ListingCurrent.floor_no != 1))
        if filters.complex_keyword:
            statement = statement.where(ListingCurrent.complex_id.in_(self._complex_keyword_ids(filters.complex_keyword)))
        return statement

    def _complex_keyword_ids(self, keyword: str):
        normalized = "".join(keyword.split())
        if self.db.bind is not None and self.db.bind.dialect.name == "mysql":
            return select(ComplexCurrent.complex_id).where(
                text("MATCH(name, normalized_name, address) AGAINST (:complex_keyword IN BOOLEAN MODE)")
            ).params(complex_keyword=normalized)
        return select(ComplexCurrent.complex_id).where(
            or_(
                ComplexCurrent.normalized_name.contains(normalized),
                ComplexCurrent.name.contains(keyword),
                ComplexCurrent.address.contains(keyword),
            )
        )

    def _sort(self, filters: ListingSearchFilter) -> _SortSpec:
        try:
            return SORT_SPECS[filters.sort_by]
        except KeyError as error:
            raise ValueError("unsupported sort") from error

    @staticmethod
    def _apply_keyset(statement, sort_column, id_column, descending: bool, anchor: tuple[Any, int]):
        value, item_id = anchor
        if descending:
            return statement.where(or_(sort_column < value, and_(sort_column == value, id_column < item_id)))
        return statement.where(or_(sort_column > value, and_(sort_column == value, id_column > item_id)))

    def _encode_cursor(self, filters: ListingSearchFilter, sort: _SortSpec, item: Any, item_id: int, *, grouped: bool) -> str:
        value = getattr(item, sort.name) if hasattr(item, sort.name) else item
        payload = {
            "sort": self._serialize_value(value),
            "id": item_id,
            "fp": self._filter_fingerprint(filters),
            "grouped": grouped,
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(self._cursor_secret, raw, hashlib.sha256).digest()
        return f"{self._b64(raw)}.{self._b64(signature)}"

    def _decode_cursor(self, filters: ListingSearchFilter, sort: _SortSpec, *, grouped: bool) -> tuple[Any, int] | None:
        if not filters.cursor:
            return None
        try:
            raw_encoded, signature_encoded = filters.cursor.split(".", 1)
            raw = self._unb64(raw_encoded)
            signature = self._unb64(signature_encoded)
            expected = hmac.new(self._cursor_secret, raw, hashlib.sha256).digest()
            payload = json.loads(raw)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("invalid cursor") from error
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid cursor signature")
        if payload.get("fp") != self._filter_fingerprint(filters) or payload.get("grouped") is not grouped:
            raise ValueError("cursor does not match filters")
        try:
            return self._deserialize_value(payload["sort"], sort.value_kind), int(payload["id"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("invalid cursor") from error

    @staticmethod
    def _serialize_value(value: Any) -> str | int:
        return value.isoformat() if isinstance(value, datetime) else int(value)

    @staticmethod
    def _deserialize_value(value: Any, kind: str) -> Any:
        return datetime.fromisoformat(value) if kind == "datetime" else int(value)

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _unb64(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    @staticmethod
    def _filter_fingerprint(filters: ListingSearchFilter) -> str:
        normalized = json.dumps(filters.fingerprint_values(), default=str, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate(filters: ListingSearchFilter) -> None:
        if not 1 <= filters.page_size <= 100:
            raise ValueError("page_size must be between 1 and 100")
        if filters.complex_keyword and len("".join(filters.complex_keyword.split())) < 2:
            raise ValueError("complex keyword must be at least two characters")
