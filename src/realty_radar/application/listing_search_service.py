"""JOIN/COUNT/OFFSET 없는 v2 listing keyset search."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy import and_, false, func, or_, select, text, true
from sqlalchemy.orm import Session

from realty_radar.config import settings
from realty_radar.constants import TransactionType
from realty_radar.domain.listing.commute_map import get_sigungu_codes_within_commute
from realty_radar.domain.listing.filters import ListingSearchFilter, ListingSearchValidationError
from realty_radar.domain.listing.models import ComplexGroupItem, SearchDiagnostics, SearchResult
from realty_radar.domain.loan.candidate_plan import (
    CAPITAL_ADDRESS_KEYWORDS,
    CAPITAL_SIDO_CODES,
    LoanCandidateBranch,
    LoanCandidatePlan,
)
from realty_radar.domain.loan.evaluator import LoanRuleEvaluator
from realty_radar.infrastructure.database.models import ComplexCurrent, ListingCurrent


LIFECYCLE_ACTIVE = 1
CURSOR_VERSION = 2


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
    "construction_year_desc": _SortSpec("construction_year", True, "int"),
    "construction_year_asc": _SortSpec("construction_year", False, "int"),
}


class ListingSearchService:
    def __init__(self, db: Session, *, cursor_secret: str | None = None):
        self.db = db
        self._cursor_secret = (cursor_secret or settings.secret_key).encode("utf-8")
        self._loan_evaluator = LoanRuleEvaluator()
        self._diagnostics: SearchDiagnostics | None = None

    def search_listings(self, filters: ListingSearchFilter, applicant: Any = None) -> SearchResult:
        return self._run_search(filters, applicant, self._search_mode(filters))

    def _run_search(
        self,
        filters: ListingSearchFilter,
        applicant: Any,
        mode: str,
        *,
        include_previous: bool = True,
    ) -> SearchResult:
        diagnostics = SearchDiagnostics(mode=mode)
        self._diagnostics = diagnostics
        started_at = perf_counter()
        self._validate(filters)
        if filters.group_by_complex:
            result = self._search_grouped(filters, applicant)
        else:
            result = self._search_rows(filters, applicant, include_previous=include_previous)
        diagnostics.total_time_ms = (perf_counter() - started_at) * 1000
        result.diagnostics = diagnostics
        return result

    def search_complex_listings(
        self,
        filters: ListingSearchFilter,
        complex_id: int,
        applicant: Any = None,
    ) -> SearchResult:
        scoped_filters = replace(
            filters,
            complex_id=complex_id,
            group_by_complex=False,
            sort_by="price_asc",
            page_size=20,
        )
        return self._run_search(
            scoped_filters,
            applicant,
            "complex_detail",
            include_previous=False,
        )

    @staticmethod
    def _search_mode(filters: ListingSearchFilter) -> str:
        if filters.only_eligible_loans and filters.group_by_complex:
            return "eligible_grouped"
        if filters.only_eligible_loans:
            return "eligible_loans"
        if filters.group_by_complex:
            return "grouped"
        return "normal"

    def _scalars(self, statement) -> list[Any]:
        return self._timed_query(lambda: self.db.scalars(statement).all())

    def _mappings(self, statement) -> list[Any]:
        return self._timed_query(lambda: self.db.execute(statement).mappings().all())

    def _timed_query(self, query) -> list[Any]:
        started_at = perf_counter()
        try:
            return list(query())
        finally:
            if self._diagnostics is not None:
                self._diagnostics.sql_count += 1
                self._diagnostics.db_time_ms += (perf_counter() - started_at) * 1000

    def _search_rows(
        self,
        filters: ListingSearchFilter,
        applicant: Any,
        *,
        include_previous: bool = True,
    ) -> SearchResult:
        sort = self._sort(filters)
        if filters.only_eligible_loans:
            return self._search_eligible_rows(
                filters,
                sort,
                applicant,
                include_previous=include_previous,
            )
        base_statement = self._filtered_rows(filters)
        statement = base_statement
        sort_column = getattr(ListingCurrent, sort.name)
        anchor = self._decode_cursor(filters, sort, grouped=False)
        if anchor is not None:
            statement = self._apply_keyset(statement, sort_column, ListingCurrent.article_id, sort.descending, anchor)
        statement = statement.order_by(
            sort_column.desc() if sort.descending else sort_column.asc(),
            ListingCurrent.article_id.desc() if sort.descending else ListingCurrent.article_id.asc(),
        ).limit(filters.page_size + 1)
        rows = self._scalars(statement)
        has_more = len(rows) > filters.page_size
        items = rows[: filters.page_size]
        previous_cursor = (
            self._previous_row_cursor(filters, sort, base_statement, sort_column, items[0], applicant)
            if include_previous and anchor is not None and items
            else None
        )
        next_cursor = (
            self._encode_cursor(
                filters, sort, items[-1], items[-1].article_id, grouped=False, applicant=applicant
            ) if has_more else None
        )
        return SearchResult(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
            previous_cursor=previous_cursor,
            has_previous=include_previous and anchor is not None,
        )

    def _search_grouped(self, filters: ListingSearchFilter, applicant: Any) -> SearchResult:
        sort = self._sort(filters)
        if filters.only_eligible_loans:
            return self._search_eligible_grouped(filters, sort, applicant)
        page_size = min(filters.page_size, 20)
        filtered = self._filtered_rows(filters).with_only_columns(
            ListingCurrent.complex_id,
            ListingCurrent.primary_price,
            ListingCurrent.first_seen_at,
            ListingCurrent.exclusive_area_x100,
            ListingCurrent.household_count,
        ).cte("filtered_listing")
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
        ).limit(page_size + 1)
        group_rows = self._mappings(statement)
        has_more = len(group_rows) > page_size
        selected = group_rows[:page_size]
        if not selected:
            return SearchResult(items=[], next_cursor=None, has_more=False, grouped_items=[], is_grouped=True)

        complex_ids = [row["complex_id"] for row in selected]
        metadata = self._complex_metadata(complex_ids)
        groups: list[ComplexGroupItem] = []
        for row in selected:
            complex_row = metadata[row["complex_id"]]
            groups.append(
                ComplexGroupItem(
                    complex_id=row["complex_id"],
                    complex_name=complex_row.name,
                    address=complex_row.address,
                    household_count=complex_row.household_count,
                    construction_year=complex_row.construction_year,
                    min_price=row["min_price"],
                    max_price=row["max_price"],
                    listing_count=row["listing_count"],
                )
            )
        last = selected[-1]
        previous_cursor = None
        if anchor is not None:
            preceding = self._mappings(
                self._apply_previous_keyset(
                    select(grouped),
                    sort_column,
                    grouped.c.complex_id,
                    sort.descending,
                    (selected[0][sort_column_name], selected[0]["complex_id"]),
                )
                .order_by(
                    sort_column.asc() if sort.descending else sort_column.desc(),
                    grouped.c.complex_id.asc() if sort.descending else grouped.c.complex_id.desc(),
                )
                .limit(page_size + 1)
            )
            if len(preceding) > page_size:
                previous = preceding[-1]
                previous_cursor = self._encode_cursor(
                    filters,
                    sort,
                    previous[sort_column_name],
                    previous["complex_id"],
                    grouped=True,
                    applicant=applicant,
                )
        next_cursor = self._encode_cursor(
            filters,
            sort,
            last[sort_column_name],
            last["complex_id"],
            grouped=True,
            applicant=applicant,
        ) if has_more else None
        return SearchResult(
            items=[],
            next_cursor=next_cursor,
            has_more=has_more,
            previous_cursor=previous_cursor,
            has_previous=anchor is not None,
            grouped_items=groups,
            is_grouped=True,
        )

    def _complex_metadata(self, complex_ids: list[int]) -> dict[int, ComplexCurrent]:
        rows = self._scalars(
            select(ComplexCurrent).where(ComplexCurrent.complex_id.in_(complex_ids))
        )
        return {row.complex_id: row for row in rows}

    def _search_eligible_rows(
        self,
        filters: ListingSearchFilter,
        sort: _SortSpec,
        applicant: Any,
        *,
        include_previous: bool = True,
    ) -> SearchResult:
        anchor = self._decode_cursor(filters, sort, grouped=False, applicant=applicant)
        if not LoanCandidatePlan.for_applicant(applicant).branches:
            return SearchResult(
                items=[],
                next_cursor=None,
                has_more=False,
                has_previous=include_previous and anchor is not None,
            )
        items = self._scan_eligible_rows(filters, sort, anchor, applicant, filters.page_size + 1)
        has_more = len(items) > filters.page_size
        page = items[: filters.page_size]
        previous_cursor = (
            self._previous_eligible_row_cursor(filters, sort, page[0], applicant)
            if include_previous and anchor is not None and page
            else None
        )
        next_cursor = (
            self._encode_cursor(
                filters, sort, page[-1], page[-1].article_id, grouped=False, applicant=applicant
            ) if has_more else None
        )
        return SearchResult(
            items=page,
            next_cursor=next_cursor,
            has_more=has_more,
            previous_cursor=previous_cursor,
            has_previous=include_previous and anchor is not None,
        )

    def _scan_eligible_rows(
        self,
        filters: ListingSearchFilter,
        sort: _SortSpec,
        anchor: tuple[Any, int] | None,
        applicant: Any,
        wanted: int | None,
    ) -> list[ListingCurrent]:
        candidate_anchor = anchor
        eligible: list[ListingCurrent] = []
        batch_size = max(100, filters.page_size * 4)
        while wanted is None or len(eligible) < wanted:
            rows = self._loan_candidate_batch(
                filters,
                sort,
                candidate_anchor,
                applicant,
                batch_size=batch_size,
            )
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
        anchor = self._decode_cursor(filters, sort, grouped=True, applicant=applicant)
        candidate_anchor = self._decode_scan_anchor(
            filters,
            sort,
            grouped=True,
            applicant=applicant,
        )
        if not LoanCandidatePlan.for_applicant(applicant).branches:
            return SearchResult(items=[], next_cursor=None, has_more=False, grouped_items=[], is_grouped=True)
        filtered = self._eligible_candidate_rows(filters, applicant).with_only_columns(
            ListingCurrent.complex_id,
            ListingCurrent.primary_price,
            ListingCurrent.first_seen_at,
            ListingCurrent.exclusive_area_x100,
            ListingCurrent.household_count,
        ).cte("eligible_group_candidates")
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
        page_size = min(filters.page_size, 20)
        wanted = page_size + 1
        qualified: list[
            tuple[ComplexGroupItem, Any, int, int, tuple[Any, int] | None]
        ] = []
        raw_order = 0
        batch_size = page_size + 1
        while True:
            statement = select(grouped)
            if candidate_anchor is not None:
                statement = self._apply_keyset(
                    statement, sort_column, grouped.c.complex_id, sort.descending, candidate_anchor
                )
            group_rows = self._mappings(
                statement.order_by(
                    sort_column.desc() if sort.descending else sort_column.asc(),
                    grouped.c.complex_id.desc() if sort.descending else grouped.c.complex_id.asc(),
                ).limit(batch_size)
            )
            if not group_rows:
                break
            complex_ids = [row["complex_id"] for row in group_rows]
            listing_rows = self._scalars(
                self._eligible_candidate_rows(filters, applicant)
                .where(ListingCurrent.complex_id.in_(complex_ids))
                .order_by(ListingCurrent.complex_id, ListingCurrent.primary_price, ListingCurrent.article_id)
            )
            by_complex: dict[int, list[ListingCurrent]] = {complex_id: [] for complex_id in complex_ids}
            for listing in listing_rows:
                if self._is_loan_eligible(listing, applicant):
                    by_complex[listing.complex_id].append(listing)
            predecessor = candidate_anchor
            for row in group_rows:
                listings = by_complex[row["complex_id"]]
                if listings:
                    item = self._make_group(row["complex_id"], listings)
                    value = self._group_sort_value(item, sort)
                    if anchor is None or self._is_after_anchor(value, item.complex_id, sort.descending, anchor):
                        qualified.append(
                            (item, value, item.complex_id, raw_order, predecessor)
                        )
                predecessor = (row[sort_column_name], row["complex_id"])
                raw_order += 1
            candidate_anchor = (group_rows[-1][sort_column_name], group_rows[-1]["complex_id"])
            if len(group_rows) < batch_size:
                break
            ranked = sorted(
                qualified,
                key=lambda item: (item[1], item[2]),
                reverse=sort.descending,
            )
            if len(ranked) >= wanted and self._raw_bound_is_safe(
                candidate_anchor,
                (ranked[wanted - 1][1], ranked[wanted - 1][2]),
                sort.descending,
            ):
                break
        ranked = sorted(
            qualified,
            key=lambda item: (item[1], item[2]),
            reverse=sort.descending,
        )
        has_more = len(ranked) > page_size
        page = ranked[:page_size]
        if not page:
            return SearchResult(items=[], next_cursor=None, has_more=False, grouped_items=[], is_grouped=True)
        _, last_value, last_id, _, _ = page[-1]
        returned_ids = {item[2] for item in page}
        remaining = [item for item in qualified if item[2] not in returned_ids]
        next_scan_anchor = (
            min(remaining, key=lambda item: item[3])[4]
            if remaining
            else candidate_anchor
        )
        next_cursor = (
            self._encode_cursor(
                filters,
                sort,
                last_value,
                last_id,
                grouped=True,
                applicant=applicant,
                scan_anchor=next_scan_anchor,
            )
            if has_more
            else None
        )
        groups = [item for item, _, _, _, _ in page]
        metadata = self._complex_metadata([item.complex_id for item in groups])
        for item in groups:
            complex_row = metadata[item.complex_id]
            item.complex_name = complex_row.name
            item.address = complex_row.address
            item.household_count = complex_row.household_count
            item.construction_year = complex_row.construction_year
            item.listings = []
        return SearchResult(
            items=[],
            next_cursor=next_cursor,
            has_more=has_more,
            grouped_items=groups,
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
        diagnostics = self._diagnostics
        if diagnostics is not None:
            diagnostics.candidate_count += 1
        started_at = perf_counter()
        try:
            transaction = {
                1: TransactionType.SALE,
                2: TransactionType.JEONSE,
                3: TransactionType.MONTHLY_RENT,
                4: TransactionType.MONTHLY_RENT,
            }.get(listing.trade_type)
            if transaction is None:
                return False
            area = Decimal(listing.exclusive_area_x100) / 100
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
                self._loan_evaluator.evaluate_beotimmok(
                    transaction, listing.primary_price, area, listing.address, applicant
                ),
            )
            listing.loan_evaluations = list(evaluations)
            return any(result.is_eligible for result in evaluations)
        finally:
            if diagnostics is not None:
                diagnostics.loan_evaluation_time_ms += (perf_counter() - started_at) * 1000

    @staticmethod
    def _loan_candidate_condition(branch: LoanCandidateBranch):
        trade_condition = (
            ListingCurrent.trade_type == branch.trade_types[0]
            if len(branch.trade_types) == 1
            else ListingCurrent.trade_type.in_(branch.trade_types)
        )
        if branch.capital_max_price == branch.non_capital_max_price:
            price_condition = ListingCurrent.primary_price <= branch.capital_max_price
        else:
            capital_location = or_(
                ListingCurrent.sido_code.in_(CAPITAL_SIDO_CODES),
                ListingCurrent.address.is_(None),
                ListingCurrent.address == "",
                *(ListingCurrent.address.contains(keyword) for keyword in CAPITAL_ADDRESS_KEYWORDS),
            )
            price_condition = or_(
                ListingCurrent.primary_price <= branch.non_capital_max_price,
                and_(capital_location, ListingCurrent.primary_price <= branch.capital_max_price),
            )
        conditions = [trade_condition, ListingCurrent.primary_price > 0, price_condition]
        if branch.max_exclusive_area_x100 is not None:
            conditions.extend(
                (
                    ListingCurrent.exclusive_area_x100 > 0,
                    ListingCurrent.exclusive_area_x100 <= branch.max_exclusive_area_x100,
                )
            )
        return and_(*conditions)

    def _eligible_candidate_rows(self, filters: ListingSearchFilter, applicant: Any):
        plan = LoanCandidatePlan.for_applicant(applicant)
        return self._filtered_rows(filters).where(
            or_(*(self._loan_candidate_condition(branch) for branch in plan.branches))
        )

    def _eligible_candidate_streams(
        self,
        filters: ListingSearchFilter,
        applicant: Any,
    ) -> list[Any]:
        streams = []
        for branch in LoanCandidatePlan.for_applicant(applicant).branches:
            for trade_type in branch.trade_types:
                if filters.trade_type is not None and filters.trade_type != trade_type:
                    continue
                if filters.trade_types and trade_type not in filters.trade_types:
                    continue
                stream_branch = LoanCandidateBranch(
                    trade_types=(trade_type,),
                    capital_max_price=branch.capital_max_price,
                    non_capital_max_price=branch.non_capital_max_price,
                    max_exclusive_area_x100=branch.max_exclusive_area_x100,
                )
                streams.append(
                    self._filtered_rows(filters).where(
                        self._loan_candidate_condition(stream_branch)
                    )
                )
        return streams

    def _loan_candidate_batch(
        self,
        filters: ListingSearchFilter,
        sort: _SortSpec,
        anchor: tuple[Any, int] | None,
        applicant: Any,
        *,
        batch_size: int,
        previous: bool = False,
    ) -> list[ListingCurrent]:
        sort_column = getattr(ListingCurrent, sort.name)
        merged: dict[int, ListingCurrent] = {}
        for stream in self._eligible_candidate_streams(filters, applicant):
            statement = self._with_candidate_index_hint(stream, filters, sort)
            if anchor is not None:
                keyset = self._apply_previous_keyset if previous else self._apply_keyset
                statement = keyset(
                    statement,
                    sort_column,
                    ListingCurrent.article_id,
                    sort.descending,
                    anchor,
                )
            stream_descending = not sort.descending if previous else sort.descending
            rows = self._scalars(
                statement.order_by(
                    sort_column.desc() if stream_descending else sort_column.asc(),
                    ListingCurrent.article_id.desc()
                    if stream_descending
                    else ListingCurrent.article_id.asc(),
                ).limit(batch_size)
            )
            merged.update((row.article_id, row) for row in rows)
        return sorted(
            merged.values(),
            key=lambda row: (getattr(row, sort.name), row.article_id),
            reverse=not sort.descending if previous else sort.descending,
        )[:batch_size]

    @staticmethod
    def _with_candidate_index_hint(statement, filters: ListingSearchFilter, sort: _SortSpec):
        if sort.name != "primary_price" or filters.complex_id is not None:
            return statement
        index_name = (
            "ix_listing_price_sigungu_tx"
            if filters.sigungu_code is not None
            else "ix_listing_price_tx"
        )
        return statement.with_hint(
            ListingCurrent,
            f"USE INDEX ({index_name})",
            dialect_name="mysql",
        )

    def _filtered_rows(self, filters: ListingSearchFilter):
        statement = select(ListingCurrent).where(ListingCurrent.lifecycle == LIFECYCLE_ACTIVE)
        if filters.exclude_short_term:
            statement = statement.where(ListingCurrent.is_short_term == false())
        # 단일 지정 기본 필터 (지역 관련 필터 제외)
        for column, value in (
            (ListingCurrent.region_code, filters.region_code),
            (ListingCurrent.complex_id, filters.complex_id),
            (ListingCurrent.trade_type, filters.trade_type),
        ):
            if value is not None:
                statement = statement.where(column == value)

        # 다중 지역 칩 기반 필터링 (sido_codes + sigungu_codes + commute_codes를 OR 합집합으로 결합)
        effective_sigungu_codes = list(filters.sigungu_codes) if filters.sigungu_codes else None
        if filters.max_commute_gangnam is not None:
            commute_codes = get_sigungu_codes_within_commute(filters.max_commute_gangnam, "gangnam")
            if effective_sigungu_codes:
                effective_sigungu_codes = list(dict.fromkeys(effective_sigungu_codes + commute_codes))
            else:
                effective_sigungu_codes = commute_codes

        if filters.sido_codes and effective_sigungu_codes:
            # 시/도 전체 + 개별 시군구 복합: OR 결합
            statement = statement.where(
                or_(
                    ListingCurrent.sido_code.in_(filters.sido_codes),
                    ListingCurrent.sigungu_code.in_(effective_sigungu_codes),
                )
            )
        elif filters.sido_codes:
            statement = statement.where(ListingCurrent.sido_code.in_(filters.sido_codes))
        elif effective_sigungu_codes:
            statement = statement.where(ListingCurrent.sigungu_code.in_(effective_sigungu_codes))
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
            statement = statement.where(ListingCurrent.is_direct_trade == true())
        if filters.safe_lessor_hug_only:
            statement = statement.where(ListingCurrent.is_safe_lessor_hug == true())
        if filters.min_room_count is not None:
            statement = statement.where(ListingCurrent.room_count >= filters.min_room_count)
        if filters.min_bathroom_count is not None:
            statement = statement.where(ListingCurrent.bathroom_count >= filters.min_bathroom_count)
        if filters.parking_possible_only:
            statement = statement.where(ListingCurrent.parking_possible == true())
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
                and_(
                    ListingCurrent.nearest_subway_walk_minutes > 0,
                    ListingCurrent.nearest_subway_walk_minutes <= filters.max_subway_walk_minutes,
                )
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

    @staticmethod
    def _apply_previous_keyset(statement, sort_column, id_column, descending: bool, anchor: tuple[Any, int]):
        value, item_id = anchor
        if descending:
            return statement.where(or_(sort_column > value, and_(sort_column == value, id_column > item_id)))
        return statement.where(or_(sort_column < value, and_(sort_column == value, id_column < item_id)))

    def _previous_row_cursor(
        self,
        filters: ListingSearchFilter,
        sort: _SortSpec,
        statement,
        sort_column,
        first_item: ListingCurrent,
        applicant: Any,
    ) -> str | None:
        preceding = self._scalars(
            self._apply_previous_keyset(
                statement,
                sort_column,
                ListingCurrent.article_id,
                sort.descending,
                (getattr(first_item, sort.name), first_item.article_id),
            )
            .order_by(
                sort_column.asc() if sort.descending else sort_column.desc(),
                ListingCurrent.article_id.asc() if sort.descending else ListingCurrent.article_id.desc(),
            )
            .limit(filters.page_size + 1)
        )
        if len(preceding) <= filters.page_size:
            return None
        previous = preceding[-1]
        return self._encode_cursor(
            filters, sort, previous, previous.article_id, grouped=False, applicant=applicant
        )

    def _previous_eligible_row_cursor(
        self,
        filters: ListingSearchFilter,
        sort: _SortSpec,
        first_item: ListingCurrent,
        applicant: Any,
    ) -> str | None:
        anchor = (getattr(first_item, sort.name), first_item.article_id)
        preceding: list[ListingCurrent] = []
        batch_size = max(100, filters.page_size * 4)
        while len(preceding) < filters.page_size + 1:
            rows = self._loan_candidate_batch(
                filters,
                sort,
                anchor,
                applicant,
                batch_size=batch_size,
                previous=True,
            )
            if not rows:
                break
            for row in rows:
                if self._is_loan_eligible(row, applicant):
                    preceding.append(row)
                    if len(preceding) >= filters.page_size + 1:
                        break
            anchor = (getattr(rows[-1], sort.name), rows[-1].article_id)
            if len(rows) < batch_size:
                break
        if len(preceding) <= filters.page_size:
            return None
        previous = preceding[-1]
        return self._encode_cursor(
            filters, sort, previous, previous.article_id, grouped=False, applicant=applicant
        )

    def _encode_cursor(
        self,
        filters: ListingSearchFilter,
        sort: _SortSpec,
        item: Any,
        item_id: int,
        *,
        grouped: bool,
        applicant: Any = None,
        scan_anchor: tuple[Any, int] | None = None,
    ) -> str:
        value = getattr(item, sort.name) if hasattr(item, sort.name) else item
        payload = {
            "v": CURSOR_VERSION,
            "sort": self._serialize_value(value),
            "id": item_id,
            "fp": self._filter_fingerprint(filters, applicant),
            "grouped": grouped,
        }
        if scan_anchor is not None:
            payload["scan"] = {
                "sort": self._serialize_value(scan_anchor[0]),
                "id": scan_anchor[1],
            }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(self._cursor_secret, raw, hashlib.sha256).digest()
        return f"{self._b64(raw)}.{self._b64(signature)}"

    def _decode_cursor(
        self, filters: ListingSearchFilter, sort: _SortSpec, *, grouped: bool, applicant: Any = None
    ) -> tuple[Any, int] | None:
        payload = self._decode_cursor_payload(
            filters,
            grouped=grouped,
            applicant=applicant,
        )
        if payload is None:
            return None
        try:
            return self._deserialize_value(payload["sort"], sort.value_kind), int(payload["id"])
        except (KeyError, TypeError, ValueError) as error:
            raise ListingSearchValidationError("invalid cursor") from error

    def _decode_scan_anchor(
        self,
        filters: ListingSearchFilter,
        sort: _SortSpec,
        *,
        grouped: bool,
        applicant: Any = None,
    ) -> tuple[Any, int] | None:
        payload = self._decode_cursor_payload(
            filters,
            grouped=grouped,
            applicant=applicant,
        )
        if payload is None or "scan" not in payload:
            return None
        try:
            scan = payload["scan"]
            return self._deserialize_value(scan["sort"], sort.value_kind), int(scan["id"])
        except (KeyError, TypeError, ValueError) as error:
            raise ListingSearchValidationError("invalid cursor scan anchor") from error

    def _decode_cursor_payload(
        self,
        filters: ListingSearchFilter,
        *,
        grouped: bool,
        applicant: Any = None,
    ) -> dict[str, Any] | None:
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
        if not isinstance(payload, dict):
            raise ListingSearchValidationError("invalid cursor")
        if payload.get("v") != CURSOR_VERSION:
            raise ListingSearchValidationError("unsupported cursor version")
        if payload.get("fp") != self._filter_fingerprint(filters, applicant) or payload.get("grouped") is not grouped:
            raise ListingSearchValidationError("cursor does not match filters")
        return payload

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
        if filters.invalid_municipality:
            raise ListingSearchValidationError("unsupported municipality")
        if filters.complex_keyword and len("".join(filters.complex_keyword.split())) < 2:
            raise ListingSearchValidationError("complex keyword must be at least two characters")
