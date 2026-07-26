"""JOIN/COUNT/OFFSET 없는 v2 listing keyset search."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from realty_radar.config import settings
from realty_radar.constants import TransactionType
from realty_radar.domain.listing.filters import ListingSearchFilter, ListingSearchValidationError
from realty_radar.domain.listing.models import ComplexGroupItem, SearchResult
from realty_radar.domain.loan.evaluator import LoanRuleEvaluator
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
        self._loan_evaluator = LoanRuleEvaluator()

    def search_listings(self, filters: ListingSearchFilter, applicant: Any = None) -> SearchResult:
        self._validate(filters)
        if filters.group_by_complex:
            return self._search_grouped(filters, applicant)
        return self._search_rows(filters, applicant)

    def _search_rows(self, filters: ListingSearchFilter, applicant: Any) -> SearchResult:
        sort = self._sort(filters)
        if filters.only_eligible_loans:
            return self._search_eligible_rows(filters, sort, applicant)
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
        next_cursor = (
            self._encode_cursor(
                filters, sort, items[-1], items[-1].article_id, grouped=False, applicant=applicant
            ) if has_more else None
        )
        return SearchResult(items=items, next_cursor=next_cursor, has_more=has_more)

    def _search_grouped(self, filters: ListingSearchFilter, applicant: Any) -> SearchResult:
        sort = self._sort(filters)
        if filters.only_eligible_loans:
            return self._search_eligible_grouped(filters, sort, applicant)
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
            applicant=applicant,
        ) if has_more else None
        return SearchResult(
            items=listing_rows,
            next_cursor=next_cursor,
            has_more=has_more,
            grouped_items=groups,
            is_grouped=True,
        )

    def _search_eligible_rows(self, filters: ListingSearchFilter, sort: _SortSpec, applicant: Any) -> SearchResult:
        anchor = self._decode_cursor(filters, sort, grouped=False, applicant=applicant)
        items = self._scan_eligible_rows(filters, sort, anchor, applicant, filters.page_size + 1)
        has_more = len(items) > filters.page_size
        page = items[: filters.page_size]
        next_cursor = (
            self._encode_cursor(
                filters, sort, page[-1], page[-1].article_id, grouped=False, applicant=applicant
            ) if has_more else None
        )
        return SearchResult(items=page, next_cursor=next_cursor, has_more=has_more)

    def _scan_eligible_rows(
        self,
        filters: ListingSearchFilter,
        sort: _SortSpec,
        anchor: tuple[Any, int] | None,
        applicant: Any,
        wanted: int | None,
    ) -> list[ListingCurrent]:
        statement = self._filtered_rows(filters)
        sort_column = getattr(ListingCurrent, sort.name)
        candidate_anchor = anchor
        eligible: list[ListingCurrent] = []
        batch_size = max(100, filters.page_size * 4)
        while wanted is None or len(eligible) < wanted:
            candidates = statement
            if candidate_anchor is not None:
                candidates = self._apply_keyset(
                    candidates, sort_column, ListingCurrent.article_id, sort.descending, candidate_anchor
                )
            candidates = candidates.order_by(
                sort_column.desc() if sort.descending else sort_column.asc(),
                ListingCurrent.article_id.desc() if sort.descending else ListingCurrent.article_id.asc(),
            ).limit(batch_size)
            rows = list(self.db.scalars(candidates).all())
            if not rows:
                break
            for row in rows:
                if self._is_loan_eligible(row, applicant):
                    eligible.append(row)
                    if wanted is not None and len(eligible) >= wanted:
                        return eligible
            candidate_anchor = (getattr(rows[-1], sort.name), rows[-1].article_id)
            if len(rows) < batch_size:
                break
        return eligible

    def _search_eligible_grouped(self, filters: ListingSearchFilter, sort: _SortSpec, applicant: Any) -> SearchResult:
        # Policy evaluation is Python-only, but group candidates remain SQL
        # ordered and keyset-bounded. Stop as soon as a page plus lookahead is
        # eligible; never materialize the full result set.
        filtered = self._filtered_rows(filters).cte("eligible_group_candidates")
        grouped = (
            select(
                filtered.c.complex_id,
                func.min(filtered.c.primary_price).label("min_price"),
                func.max(filtered.c.primary_price).label("max_price"),
                func.max(filtered.c.first_seen_at).label("latest_seen_at"),
                func.min(filtered.c.exclusive_area_x100).label("min_area_x100"),
                func.max(filtered.c.exclusive_area_x100).label("max_area_x100"),
                func.min(filtered.c.household_count).label("min_household_count"),
                func.max(filtered.c.household_count).label("household_count"),
            )
            .group_by(filtered.c.complex_id)
            .cte("eligible_grouped_complex")
        )
        sort_column_name = (
            "min_household_count"
            if sort.name == "household_count" and not sort.descending
            else {
                "primary_price": "max_price" if sort.descending else "min_price",
                "first_seen_at": "latest_seen_at",
                "exclusive_area_x100": "max_area_x100" if sort.descending else "min_area_x100",
                "household_count": "household_count",
            }[sort.name]
        )
        sort_column = getattr(grouped.c, sort_column_name)
        anchor = self._decode_cursor(filters, sort, grouped=True, applicant=applicant)
        # The issued cursor is based on eligible aggregates, which intentionally
        # differs from the raw SQL candidate aggregate. Keep the scan keyset
        # private to this request and apply the public cursor after evaluation.
        candidate_anchor = None
        wanted = filters.page_size + 1
        qualified: list[tuple[ComplexGroupItem, Any, int]] = []
        batch_size = max(50, filters.page_size * 4)
        while True:
            statement = select(grouped)
            if candidate_anchor is not None:
                statement = self._apply_keyset(
                    statement, sort_column, grouped.c.complex_id, sort.descending, candidate_anchor
                )
            group_rows = list(
                self.db.execute(
                    statement.order_by(
                        sort_column.desc() if sort.descending else sort_column.asc(),
                        grouped.c.complex_id.desc() if sort.descending else grouped.c.complex_id.asc(),
                    ).limit(batch_size)
                ).mappings().all()
            )
            if not group_rows:
                break
            complex_ids = [row["complex_id"] for row in group_rows]
            listing_rows = list(
                self.db.scalars(
                    self._filtered_rows(filters)
                    .where(ListingCurrent.complex_id.in_(complex_ids))
                    .order_by(ListingCurrent.complex_id, ListingCurrent.primary_price, ListingCurrent.article_id)
                ).all()
            )
            by_complex: dict[int, list[ListingCurrent]] = {complex_id: [] for complex_id in complex_ids}
            for listing in listing_rows:
                if self._is_loan_eligible(listing, applicant):
                    by_complex[listing.complex_id].append(listing)
            batch_qualified: list[tuple[ComplexGroupItem, Any, int]] = []
            for row in group_rows:
                listings = by_complex[row["complex_id"]]
                if listings:
                    item = self._make_group(row["complex_id"], listings)
                    value = self._group_sort_value(item, sort)
                    if anchor is None or self._is_after_anchor(value, item.complex_id, sort.descending, anchor):
                        batch_qualified.append((item, value, item.complex_id))
            batch_qualified.sort(
                key=lambda item: (item[1], item[2]), reverse=sort.descending
            )
            qualified.extend(batch_qualified)
            qualified.sort(key=lambda item: (item[1], item[2]), reverse=sort.descending)
            qualified = qualified[:wanted]
            candidate_anchor = (group_rows[-1][sort_column_name], group_rows[-1]["complex_id"])
            if len(group_rows) < batch_size:
                break
            if len(qualified) >= wanted and self._raw_bound_is_safe(
                candidate_anchor, (qualified[-1][1], qualified[-1][2]), sort.descending
            ):
                break
        has_more = len(qualified) > filters.page_size
        page = qualified[: filters.page_size]
        if not page:
            return SearchResult(items=[], next_cursor=None, has_more=False, grouped_items=[], is_grouped=True)
        _, last_value, last_id = page[-1]
        next_cursor = (
            self._encode_cursor(filters, sort, last_value, last_id, grouped=True, applicant=applicant)
            if has_more
            else None
        )
        return SearchResult(
            items=[listing for item, _, _ in page for listing in item.listings],
            next_cursor=next_cursor,
            has_more=has_more,
            grouped_items=[item for item, _, _ in page],
            is_grouped=True,
        )

    @staticmethod
    def _make_group(complex_id: int, listings: list[ListingCurrent]) -> ComplexGroupItem:
        representative = min(listings, key=lambda row: (row.primary_price, row.article_id))
        return ComplexGroupItem(
            complex_id=complex_id,
            complex_name=representative.complex_name,
            address=representative.address,
            household_count=representative.household_count,
            construction_year=representative.construction_year,
            min_price=min(row.primary_price for row in listings),
            max_price=max(row.primary_price for row in listings),
            listing_count=len(listings),
            listings=sorted(listings, key=lambda row: (row.primary_price, row.article_id)),
        )

    @staticmethod
    def _group_sort_value(item: ComplexGroupItem, sort: _SortSpec) -> Any:
        if sort.name == "primary_price":
            return item.max_price if sort.descending else item.min_price
        if sort.name == "first_seen_at":
            return max(row.first_seen_at for row in item.listings)
        if sort.name == "exclusive_area_x100":
            values = [row.exclusive_area_x100 for row in item.listings]
            return max(values) if sort.descending else min(values)
        return max(row.household_count for row in item.listings)

    @staticmethod
    def _is_after_anchor(value: Any, item_id: int, descending: bool, anchor: tuple[Any, int]) -> bool:
        anchor_value, anchor_id = anchor
        if descending:
            return value < anchor_value or (value == anchor_value and item_id < anchor_id)
        return value > anchor_value or (value == anchor_value and item_id > anchor_id)

    @staticmethod
    def _raw_bound_is_safe(raw_bound: tuple[Any, int], worst: tuple[Any, int], descending: bool) -> bool:
        """Whether unscanned raw aggregates cannot outrank the eligible page tail."""
        return raw_bound <= worst if descending else raw_bound >= worst

    def _is_loan_eligible(self, listing: ListingCurrent, applicant: Any) -> bool:
        transaction = {
            1: TransactionType.SALE,
            2: TransactionType.JEONSE,
            3: TransactionType.MONTHLY_RENT,
            4: TransactionType.MONTHLY_RENT,
        }.get(listing.trade_type)
        if transaction is None:
            return False
        area = Decimal(listing.exclusive_area_x100) / 100
        if transaction == TransactionType.SALE:
            evaluations = (
                self._loan_evaluator.evaluate_didimdol(
                    transaction, listing.primary_price, area, listing.address, applicant
                ),
                self._loan_evaluator.evaluate_bogumjari(
                    transaction, listing.primary_price, area, listing.address, applicant
                ),
                self._loan_evaluator.evaluate_neonatal_purchase(
                    transaction, listing.primary_price, area, listing.address, applicant
                ),
            )
        else:
            evaluations = (
                self._loan_evaluator.evaluate_beotimmok(
                    transaction, listing.primary_price, area, listing.address, applicant
                ),
            )
        return any(result.is_eligible for result in evaluations)

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
        if filters.trade_types:
            statement = statement.where(ListingCurrent.trade_type.in_(filters.trade_types))
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
        if filters.direct_trade_only:
            statement = statement.where(ListingCurrent.is_direct_trade.is_(True))
        if filters.safe_lessor_hug_only:
            statement = statement.where(ListingCurrent.is_safe_lessor_hug.is_(True))
        if filters.min_room_count is not None:
            statement = statement.where(ListingCurrent.room_count >= filters.min_room_count)
        if filters.min_bathroom_count is not None:
            statement = statement.where(ListingCurrent.bathroom_count >= filters.min_bathroom_count)
        if filters.parking_possible_only:
            statement = statement.where(ListingCurrent.parking_possible.is_(True))
        if filters.min_parking_per_household_x100 is not None:
            statement = statement.where(
                ListingCurrent.parking_per_household_x100 >= filters.min_parking_per_household_x100
            )
        if filters.max_monthly_management_cost is not None:
            statement = statement.where(ListingCurrent.monthly_management_cost <= filters.max_monthly_management_cost)
        if filters.move_in_by is not None:
            statement = statement.where(ListingCurrent.move_in_available_on <= filters.move_in_by)
        if filters.max_subway_walk_minutes is not None:
            statement = statement.where(
                ListingCurrent.nearest_subway_walk_minutes <= filters.max_subway_walk_minutes
            )
        if filters.min_area_x100 is not None:
            statement = statement.where(ListingCurrent.exclusive_area_x100 >= filters.min_area_x100)
        if filters.max_area_x100 is not None:
            statement = statement.where(ListingCurrent.exclusive_area_x100 <= filters.max_area_x100)
        if filters.min_construction_year is not None:
            statement = statement.where(ListingCurrent.construction_year >= filters.min_construction_year)
        if filters.min_households is not None:
            statement = statement.where(ListingCurrent.household_count >= filters.min_households)
        if filters.recent_days is not None:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=filters.recent_days)
            statement = statement.where(ListingCurrent.first_seen_at >= cutoff)
        if filters.mortgage_codes:
            statement = statement.where(ListingCurrent.mortgage_code.in_(filters.mortgage_codes))
            if 0 in filters.mortgage_codes:
                statement = statement.where(ListingCurrent.mortgage_checked_at.is_not(None))
        if filters.exclude_unknown_mortgage:
            statement = statement.where(
                ListingCurrent.mortgage_checked_at.is_not(None), ListingCurrent.mortgage_code.in_((1, 2))
            )
        if filters.direction_codes:
            statement = statement.where(ListingCurrent.direction_code.in_(filters.direction_codes))
        if filters.floor_bands:
            statement = statement.where(ListingCurrent.floor_band.in_(filters.floor_bands))
        if filters.exclude_first_floor:
            statement = statement.where(or_(ListingCurrent.floor_no.is_(None), ListingCurrent.floor_no != 1))
        if filters.complex_keyword:
            statement = statement.where(
                ListingCurrent.complex_id.in_(self._complex_keyword_ids(filters.complex_keyword))
            )
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
            raise ListingSearchValidationError("unsupported sort") from error

    @staticmethod
    def _apply_keyset(statement, sort_column, id_column, descending: bool, anchor: tuple[Any, int]):
        value, item_id = anchor
        if descending:
            return statement.where(or_(sort_column < value, and_(sort_column == value, id_column < item_id)))
        return statement.where(or_(sort_column > value, and_(sort_column == value, id_column > item_id)))

    def _encode_cursor(
        self,
        filters: ListingSearchFilter,
        sort: _SortSpec,
        item: Any,
        item_id: int,
        *,
        grouped: bool,
        applicant: Any = None,
    ) -> str:
        value = getattr(item, sort.name) if hasattr(item, sort.name) else item
        payload = {
            "sort": self._serialize_value(value),
            "id": item_id,
            "fp": self._filter_fingerprint(filters, applicant),
            "grouped": grouped,
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(self._cursor_secret, raw, hashlib.sha256).digest()
        return f"{self._b64(raw)}.{self._b64(signature)}"

    def _decode_cursor(
        self, filters: ListingSearchFilter, sort: _SortSpec, *, grouped: bool, applicant: Any = None
    ) -> tuple[Any, int] | None:
        if not filters.cursor:
            return None
        try:
            raw_encoded, signature_encoded = filters.cursor.split(".", 1)
            raw = self._unb64(raw_encoded)
            signature = self._unb64(signature_encoded)
            expected = hmac.new(self._cursor_secret, raw, hashlib.sha256).digest()
            payload = json.loads(raw)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ListingSearchValidationError("invalid cursor") from error
        if not hmac.compare_digest(signature, expected):
            raise ListingSearchValidationError("invalid cursor signature")
        if payload.get("fp") != self._filter_fingerprint(filters, applicant) or payload.get("grouped") is not grouped:
            raise ListingSearchValidationError("cursor does not match filters")
        try:
            return self._deserialize_value(payload["sort"], sort.value_kind), int(payload["id"])
        except (KeyError, TypeError, ValueError) as error:
            raise ListingSearchValidationError("invalid cursor") from error

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
    def _filter_fingerprint(filters: ListingSearchFilter, applicant: Any = None) -> str:
        values: dict[str, Any] = {"filters": filters.fingerprint_values()}
        if filters.only_eligible_loans:
            values["applicant"] = ListingSearchService._applicant_values(applicant)
        normalized = json.dumps(values, default=str, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _applicant_values(applicant: Any) -> dict[str, Any] | None:
        if applicant is None:
            return None
        if hasattr(applicant, "to_dict"):
            return dict(applicant.to_dict())
        names = (
            "is_homeless", "annual_income", "net_assets", "is_newlywed", "is_first_home_buyer",
            "child_count", "has_newborn", "use_promissory_note", "promissory_note_person_count",
            "promissory_note_amount", "promissory_notes",
        )
        return {name: getattr(applicant, name, None) for name in names}

    @staticmethod
    def _validate(filters: ListingSearchFilter) -> None:
        if not 1 <= filters.page_size <= 100:
            raise ListingSearchValidationError("page_size must be between 1 and 100")
        if filters.complex_keyword and len("".join(filters.complex_keyword.split())) < 2:
            raise ListingSearchValidationError("complex keyword must be at least two characters")
