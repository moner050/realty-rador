"""v2 keyset listing search routes."""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, ROUND_CEILING
from time import perf_counter
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.params import Param
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.crawler.adapters.site_a.region_codes import SIDO_CODES, SIGUNGU_CODES
from realty_radar.domain.listing.filters import ListingSearchFilter, ListingSearchValidationError
from realty_radar.domain.loan.entities import LoanEligibilityStatus
from realty_radar.domain.loan.evaluator import LoanRuleEvaluator
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.auth import SESSION_COOKIE_NAME, is_authenticated, verify_session_token, get_current_username, is_admin_user
from realty_radar.web.jinja_filters import register_jinja_filters
from realty_radar.web.routes.settings import get_request_user_profile, load_user_search_filter, save_user_search_filter


router = APIRouter()
templates = Jinja2Templates(directory="src/realty_radar/web/templates")
register_jinja_filters(templates)
_LOAN_EVALUATOR = LoanRuleEvaluator()
logger = logging.getLogger(__name__)

TRADE_TYPE_CODES = {"SALE": 1, "JEONSE": 2, "MONTHLY_RENT": 3, "SHORT_TERM": 4}
TRADE_TYPE_NAMES = {code: name for name, code in TRADE_TYPE_CODES.items()}
MAX_PRICE_WON = 3_000_000_000
SORT_OPTIONS = (
    ("price_asc", "가격 낮은순"),
    ("price_desc", "가격 높은순"),
    ("recent", "최신 등록순"),
    ("area_asc", "전용면적 좁은순"),
    ("area_desc", "전용면적 넓은순"),
    ("households_asc", "세대수 적은순"),
    ("households_desc", "세대수 많은순"),
)


def _optional_int(value: str | int | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_decimal(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(value)
    except Exception:
        return None


def _optional_eok_price(value: str | None) -> int | None:
    amount = _optional_decimal(value)
    if amount is None or not amount.is_finite() or amount < 0:
        return None
    return int(amount * Decimal(100_000_000))


def _capped_price(value: int | None) -> int | None:
    return min(value, MAX_PRICE_WON) if value is not None else None


def _query_value_was_provided(value: object) -> bool:
    return value is not None and not isinstance(value, Param)


def _optional_date(value: str | None) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _code_list(values: list[str] | None) -> list[int] | None:
    parsed = [
        int(token)
        for value in (values if isinstance(values, list) else [])
        for token in value.split(",")
        if token.strip().isdigit()
    ]
    return list(dict.fromkeys(parsed)) or None


def _trade_codes(values: list[str] | None) -> list[int] | None:
    codes = [
        TRADE_TYPE_CODES[token.strip().upper()]
        for token in (values if isinstance(values, list) else [])
        if token.strip().upper() in TRADE_TYPE_CODES
    ]
    return list(dict.fromkeys(codes)) or None


def _request_list(value: object) -> list[str] | None:
    return value if isinstance(value, list) else None


def _request_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _request_bool(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _region_options() -> list[dict[str, object]]:
    options: list[dict[str, object]] = []
    for sido_name, sido_code in SIDO_CODES.items():
        municipalities: dict[str, dict[str, object]] = {}
        direct_districts: list[dict[str, object]] = []
        for sigungu_name, sigungu_code in SIGUNGU_CODES[sido_name].items():
            code = int(sigungu_code) // 100_000
            parent, separator, district = sigungu_name.partition(" ")
            if separator and parent.endswith("시") and district.endswith("구"):
                municipality = municipalities.setdefault(
                    parent,
                    {"name": parent, "codes": [], "districts": []},
                )
                municipality["codes"].append(code)
                municipality["districts"].append({"name": district, "code": code})
            elif sido_name == "경기도":
                municipalities[sigungu_name] = {"name": sigungu_name, "codes": [code], "districts": []}
            else:
                direct_districts.append({"name": sigungu_name, "code": code})
        options.append(
            {
                "name": sido_name,
                "code": int(sido_code) // 100_000_000,
                "municipalities": list(municipalities.values()),
                "districts": direct_districts,
            }
        )
    return options


def _municipality_codes(sido_code: int | None, municipality: str | None) -> list[int] | None:
    if not municipality:
        return None
    for region in _region_options():
        if region["code"] != sido_code:
            continue
        for item in region["municipalities"]:
            if item["name"] == municipality:
                return list(item["codes"])
    return []


def _region_labels() -> tuple[dict[int, str], dict[int, str]]:
    return (
        {int(code) // 100_000_000: name for name, code in SIDO_CODES.items()},
        {
            int(code) // 100_000: name
            for sigungu in SIGUNGU_CODES.values()
            for name, code in sigungu.items()
        },
    )


def _selected_municipality(filters: ListingSearchFilter) -> str | None:
    if not filters.sigungu_codes or filters.sigungu_code is not None:
        return None
    selected_codes = sorted(filters.sigungu_codes)
    for region in _region_options():
        for municipality in region["municipalities"]:
            if municipality["codes"] == selected_codes:
                return str(municipality["name"])
    return None


def _slider_limits(filters: ListingSearchFilter) -> dict[str, int | Decimal]:
    def scaled_limit(value: int | Decimal | None, *, base: int, scale: int = 1) -> int:
        if value is None:
            return base
        return max(base, int((Decimal(value) / scale).to_integral_value(rounding=ROUND_CEILING)))

    return {
        "price_eok": 30,
        "monthly_rent_manwon": scaled_limit(filters.max_monthly_rent, base=1_000, scale=10_000),
        "area": scaled_limit(
            max(value for value in (filters.min_exclusive_area, filters.max_exclusive_area) if value is not None)
            if filters.min_exclusive_area is not None or filters.max_exclusive_area is not None
            else None,
            base=500,
        ),
        "parking": scaled_limit(filters.min_parking_per_household, base=5),
        "management_cost_manwon": scaled_limit(filters.max_monthly_management_cost, base=200, scale=10_000),
        "subway_minutes": scaled_limit(filters.max_subway_walk_minutes, base=60),
        "construction_year": scaled_limit(filters.min_construction_year, base=date.today().year),
        "households": scaled_limit(filters.min_households, base=10_000),
        "recent_days": scaled_limit(filters.recent_days, base=365),
    }


def parse_search_filter(
    region_code: str | None = Query(None),
    sido_code: str | None = Query(None),
    municipality: str | None = Query(None),
    sigungu_code: str | None = Query(None),
    sigungu_codes: list[str] | None = Query(None),
    complex_keyword: str | None = Query(None),
    transaction_type: str | None = Query(None),
    transaction_types: list[str] | None = Query(None),
    trade_types: list[str] | None = Query(None),
    min_price: str | None = Query(None),
    max_price: str | None = Query(None),
    min_price_eok: str | None = Query(None),
    max_price_eok: str | None = Query(None),
    min_deposit: str | None = Query(None),
    max_deposit: str | None = Query(None),
    max_monthly_rent: str | None = Query(None),
    direct_trade_only: bool = Query(False),
    safe_lessor_hug_only: bool = Query(False),
    min_room_count: str | None = Query(None),
    min_bathroom_count: str | None = Query(None),
    parking_possible_only: bool = Query(False),
    min_parking_per_household: str | None = Query(None),
    max_monthly_management_cost: str | None = Query(None),
    move_in_by: str | None = Query(None),
    max_subway_walk_minutes: str | None = Query(None),
    min_exclusive_area: str | None = Query(None),
    max_exclusive_area: str | None = Query(None),
    min_construction_year: str | None = Query(None),
    min_households: str | None = Query(None),
    recent_days: str | None = Query(None),
    recent_days_custom: str | None = Query(None),
    mortgage_codes: list[str] | None = Query(None),
    exclude_unknown_mortgage: bool = Query(False),
    direction_codes: list[str] | None = Query(None),
    floor_bands: list[str] | None = Query(None),
    sort_by: str = Query("price_asc"),
    page_size: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    exclude_short_term: bool = Query(True),
    exclude_first_floor: bool = Query(False),
    group_by_complex: bool = Query(False),
    only_eligible_loans: bool = Query(False),
) -> ListingSearchFilter:
    transaction = _request_string(transaction_type)
    trades = _trade_codes(
        _request_list(trade_types)
        or _request_list(transaction_types)
        or ([transaction] if transaction else None)
    )
    parsed_min_price = _optional_int(min_price)
    parsed_max_price = _optional_int(max_price)
    parsed_min_eok = _optional_eok_price(min_price_eok)
    parsed_max_eok = _optional_eok_price(max_price_eok)
    parsed_recent_days = _optional_int(recent_days)
    if parsed_recent_days is None:
        parsed_recent_days = _optional_int(recent_days_custom)
    parsed_exclude_short_term = _request_bool(exclude_short_term, True)
    if trades and 4 in trades:
        parsed_exclude_short_term = False
    parsed_sido_code = _optional_int(sido_code)
    municipality_value = _request_string(municipality)
    municipality_codes = _municipality_codes(parsed_sido_code, municipality_value)
    explicit_sigungu_codes = _code_list(_request_list(sigungu_codes))
    return ListingSearchFilter(
        region_code=_optional_int(region_code),
        sido_code=parsed_sido_code,
        sigungu_code=_optional_int(sigungu_code),
        sigungu_codes=explicit_sigungu_codes or municipality_codes or None,
        invalid_municipality=(
            explicit_sigungu_codes is None and municipality_value is not None and municipality_codes == []
        ),
        complex_keyword=(keyword.strip() if (keyword := _request_string(complex_keyword)) and keyword.strip() else None),
        trade_type=trades[0] if trades and len(trades) == 1 else None,
        trade_types=trades,
        min_price=_capped_price(
            parsed_min_price
            if _query_value_was_provided(min_price)
            else parsed_min_eok
            if parsed_min_eok is not None
            else _optional_int(min_deposit)
        ),
        max_price=_capped_price(
            parsed_max_price
            if _query_value_was_provided(max_price)
            else parsed_max_eok
            if parsed_max_eok is not None
            else _optional_int(max_deposit)
        ),
        max_monthly_rent=_optional_int(max_monthly_rent),
        direct_trade_only=_request_bool(direct_trade_only, False),
        safe_lessor_hug_only=_request_bool(safe_lessor_hug_only, False),
        min_room_count=_optional_int(min_room_count),
        min_bathroom_count=_optional_int(min_bathroom_count),
        parking_possible_only=_request_bool(parking_possible_only, False),
        min_parking_per_household=_optional_decimal(min_parking_per_household),
        max_monthly_management_cost=_optional_int(max_monthly_management_cost),
        move_in_by=_optional_date(move_in_by),
        max_subway_walk_minutes=_optional_int(max_subway_walk_minutes),
        min_exclusive_area=_optional_decimal(min_exclusive_area),
        max_exclusive_area=_optional_decimal(max_exclusive_area),
        min_construction_year=_optional_int(min_construction_year),
        min_households=_optional_int(min_households),
        recent_days=parsed_recent_days,
        mortgage_codes=_code_list(_request_list(mortgage_codes)),
        exclude_unknown_mortgage=_request_bool(exclude_unknown_mortgage, False),
        direction_codes=_code_list(_request_list(direction_codes)),
        floor_bands=_code_list(_request_list(floor_bands)),
        sort_by=_request_string(sort_by) or "price_asc",
        page_size=page_size if isinstance(page_size, int) else 20,
        cursor=_request_string(cursor),
        exclude_short_term=parsed_exclude_short_term,
        exclude_first_floor=_request_bool(exclude_first_floor, False),
        group_by_complex=_request_bool(group_by_complex, False),
        only_eligible_loans=_request_bool(only_eligible_loans, False),
    )


def _listing_items(result):
    if result.is_grouped:
        return [item for group in result.grouped_items for item in group.listings]
    return result.items


def _favorite_listing_payload(item) -> dict[str, object]:
    return {
        "article_id": item.article_id,
        "complex_id": item.complex_id,
        "complex_name": item.complex_name,
        "address": item.address,
        "trade_type": item.trade_type,
        "primary_price": item.primary_price,
        "exclusive_area_x100": item.exclusive_area_x100,
        "floor_no": item.floor_no,
        "direction_code": item.direction_code,
        "household_count": item.household_count,
        "construction_year": item.construction_year,
        "eligible_loans": [
            {"loan_type_name": loan.loan_type_name} for loan in getattr(item, "eligible_loans", [])
        ],
    }


def _favorite_complex_payload(group) -> dict[str, object]:
    return {
        "complex_id": group.complex_id,
        "complex_name": group.complex_name,
        "address": group.address,
    }


def _favorite_payload_context(result) -> dict[str, dict[int, dict[str, object]]]:
    return {
        "favorite_listing_payloads": {
            item.article_id: _favorite_listing_payload(item) for item in _listing_items(result)
        },
        "favorite_complex_payloads": {
            group.complex_id: _favorite_complex_payload(group) for group in result.grouped_items
        },
    }


def _loan_calculation_criteria(item, applicant, evaluation) -> list[tuple[str, str]]:
    area = Decimal(item.exclusive_area_x100) / 100 if item.exclusive_area_x100 is not None else None
    price_label = "매매가" if item.trade_type == 1 else "보증금"
    criteria = [
        (price_label, f"{item.primary_price:,}원" if item.primary_price is not None else "확인 필요"),
        ("전용면적", f"{area}㎡" if area is not None else "확인 필요"),
        ("주소", item.address or "확인 필요"),
        ("연소득", f"{applicant.annual_income:,}원"),
        ("무주택", "예" if applicant.is_homeless else "아니오"),
    ]
    if evaluation.product_code in {"DIDIMDOL", "BOGUMJARI", "NEONATAL_PURCHASE"}:
        ltv = "80%" if applicant.is_first_home_buyer and not _LOAN_EVALUATOR._is_capital_area(item.address) else "70%"
        criteria.append(("적용 LTV", ltv))
    if evaluation.product_code == "DIDIMDOL":
        criteria.extend(
            [
                ("생애최초", "예" if applicant.is_first_home_buyer else "아니오"),
                ("신혼 여부", "예" if applicant.is_newlywed else "아니오"),
            ]
        )
    elif evaluation.product_code == "NEONATAL_PURCHASE":
        criteria.append(("2년 내 출산", "예" if applicant.has_newborn else "아니오"))
    elif evaluation.product_code == "BEOTIMMOK":
        criteria.append(("신혼 여부", "예" if applicant.is_newlywed else "아니오"))
    return criteria


def _enrich_listings_with_loans(result, applicant) -> float:
    evaluation_time_ms = 0.0
    for item in _listing_items(result):
        transaction_type = {1: "SALE", 2: "JEONSE", 3: "MONTHLY_RENT", 4: "MONTHLY_RENT"}.get(item.trade_type)
        if transaction_type is None:
            item.eligible_loans = []
            item.other_loans = []
            item.loan_evaluations = []
            continue
        try:
            from realty_radar.constants import TransactionType

            tx = TransactionType(transaction_type)
            area = Decimal(item.exclusive_area_x100) / 100 if item.exclusive_area_x100 is not None else None
            cached_evaluations = getattr(item, "loan_evaluations", None)
            if cached_evaluations:
                evaluations = tuple(cached_evaluations)
            else:
                started_at = perf_counter()
                try:
                    evaluations = (
                        _LOAN_EVALUATOR.evaluate_didimdol(tx, item.primary_price, area, item.address, applicant),
                        _LOAN_EVALUATOR.evaluate_bogumjari(tx, item.primary_price, area, item.address, applicant),
                        _LOAN_EVALUATOR.evaluate_neonatal_purchase(
                            tx, item.primary_price, area, item.address, applicant
                        ),
                        _LOAN_EVALUATOR.evaluate_beotimmok(tx, item.primary_price, area, item.address, applicant),
                    )
                finally:
                    evaluation_time_ms += (perf_counter() - started_at) * 1000
            for evaluation in evaluations:
                evaluation.calculation_criteria = _loan_calculation_criteria(item, applicant, evaluation)
            item.loan_evaluations = list(evaluations)
            item.eligible_loans = [
                evaluation for evaluation in evaluations if evaluation.status == LoanEligibilityStatus.ELIGIBLE
            ]
            item.other_loans = [
                evaluation for evaluation in evaluations if evaluation.status != LoanEligibilityStatus.ELIGIBLE
            ]
        except Exception:
            item.eligible_loans = []
            item.other_loans = []
            item.loan_evaluations = []
    return evaluation_time_ms


def _log_search_diagnostics(result, started_at: float) -> None:
    diagnostics = result.diagnostics
    diagnostics.total_time_ms = (perf_counter() - started_at) * 1000
    logger.info(
        "listing_search mode=%s sql_count=%d candidate_count=%d "
        "db_ms=%.3f loan_ms=%.3f total_ms=%.3f",
        diagnostics.mode,
        diagnostics.sql_count,
        diagnostics.candidate_count,
        diagnostics.db_time_ms,
        diagnostics.loan_evaluation_time_ms,
        diagnostics.total_time_ms,
    )


def _filter_query_items(filters: ListingSearchFilter) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    minimums = [value for value in (filters.min_price, filters.min_deposit) if value is not None]
    maximums = [value for value in (filters.max_price, filters.max_deposit) if value is not None]
    scalar_values = {
        "region_code": filters.region_code,
        "sido_code": filters.sido_code,
        "sigungu_code": filters.sigungu_code,
        "complex_keyword": filters.complex_keyword,
        "min_price": max(minimums) if minimums else None,
        "max_price": min(maximums) if maximums else None,
        "max_monthly_rent": filters.max_monthly_rent,
        "min_room_count": filters.min_room_count,
        "min_bathroom_count": filters.min_bathroom_count,
        "min_parking_per_household": filters.min_parking_per_household,
        "max_monthly_management_cost": filters.max_monthly_management_cost,
        "move_in_by": filters.move_in_by,
        "max_subway_walk_minutes": filters.max_subway_walk_minutes,
        "min_exclusive_area": filters.min_exclusive_area,
        "max_exclusive_area": filters.max_exclusive_area,
        "min_construction_year": filters.min_construction_year,
        "min_households": filters.min_households,
        "recent_days": filters.recent_days,
        "sort_by": filters.sort_by,
        "page_size": filters.page_size,
    }
    for key, value in scalar_values.items():
        if value is not None:
            items.append((key, value.isoformat() if isinstance(value, date) else str(value)))
    for key, value in (
        ("direct_trade_only", filters.direct_trade_only),
        ("safe_lessor_hug_only", filters.safe_lessor_hug_only),
        ("parking_possible_only", filters.parking_possible_only),
        ("exclude_unknown_mortgage", filters.exclude_unknown_mortgage),
        ("exclude_first_floor", filters.exclude_first_floor),
        ("exclude_short_term", filters.exclude_short_term),
        ("group_by_complex", filters.group_by_complex),
        ("only_eligible_loans", filters.only_eligible_loans),
    ):
        items.append((key, str(value).lower()))
    for key, values in (
        ("sigungu_codes", filters.sigungu_codes),
        ("mortgage_codes", filters.mortgage_codes),
        ("direction_codes", filters.direction_codes),
        ("floor_bands", filters.floor_bands),
    ):
        items.extend((key, str(value)) for value in values or ())
    trade_codes = filters.trade_types or ([filters.trade_type] if filters.trade_type is not None else [])
    items.extend(
        ("trade_types", name)
        for code in trade_codes
        if (name := TRADE_TYPE_NAMES.get(code)) is not None
    )
    return items


def _complex_listing_urls(
    request: Request,
    result,
    filters: ListingSearchFilter,
) -> dict[int, str]:
    query_items = (
        [
            (key, value)
            for key, value in request.query_params.multi_items()
            if key not in {"append", "cursor"}
        ]
        if request.query_params
        else _filter_query_items(filters)
    )
    query = urlencode(query_items)
    return {
        group.complex_id: (
            f"{request.url_for('complex_listings', complex_id=group.complex_id)}?{query}"
            if query
            else str(request.url_for("complex_listings", complex_id=group.complex_id))
        )
        for group in result.grouped_items
    }


def _render_result(request: Request, db: Session, filters: ListingSearchFilter, template_name: str):
    started_at = perf_counter()
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_token(token)
    if username and not request.query_params:
        filters = load_user_search_filter(username) or filters
    elif username:
        save_user_search_filter(filters, username)
    applicant = get_request_user_profile(request)
    result = ListingSearchService(db).search_listings(filters, applicant=applicant)
    result.diagnostics.loan_evaluation_time_ms += _enrich_listings_with_loans(result, applicant)
    favorite_payloads = _favorite_payload_context(result)
    page_url = request.url.remove_query_params("append")
    next_url = str(page_url.include_query_params(cursor=result.next_cursor)) if result.next_cursor else None
    previous_url = None
    if result.has_previous:
        previous_url = (
            str(page_url.include_query_params(cursor=result.previous_cursor))
            if result.previous_cursor
            else str(page_url.remove_query_params("cursor"))
        )
    sido_labels, sigungu_labels = _region_labels()
    response = templates.TemplateResponse(
        request,
        template_name,
        context={
            "result": result,
            "listings": result.items,
            "filters": filters,
            "next_url": next_url,
            "previous_url": previous_url,
            "complex_urls": _complex_listing_urls(request, result, filters),
            "applicant": applicant,
            "promissory_note_entries": [entry.to_dict() for entry in applicant.promissory_notes],
            "is_authenticated": is_authenticated(request),
            "is_admin": is_admin_user(request),
            "current_username": get_current_username(request),
            "region_options": _region_options(),
            "selected_municipality": _selected_municipality(filters),
            "slider_limits": _slider_limits(filters),
            "sort_options": SORT_OPTIONS,
            "sido_labels": sido_labels,
            "sigungu_labels": sigungu_labels,
            **favorite_payloads,
        },
    )
    _log_search_diagnostics(result, started_at)
    return response


def _render_search_error(request: Request, filters: ListingSearchFilter, *, is_htmx: bool):
    sido_labels, sigungu_labels = _region_labels()
    applicant = get_request_user_profile(request)
    context = {
        "applicant": applicant,
        "promissory_note_entries": [entry.to_dict() for entry in applicant.promissory_notes],
        "filters": filters,
        "region_options": _region_options(),
        "selected_municipality": _selected_municipality(filters),
        "slider_limits": _slider_limits(filters),
        "sort_options": SORT_OPTIONS,
        "sido_labels": sido_labels,
        "sigungu_labels": sigungu_labels,
        "is_authenticated": is_authenticated(request),
        "is_admin": is_admin_user(request),
        "search_error": True,
    }
    response = templates.TemplateResponse(
        request,
        "listings/search_error.html" if is_htmx else "listings/index.html",
        context=context,
        status_code=200 if is_htmx else 400,
    )
    if is_htmx:
        response.headers["HX-Retarget"] = "#search-results"
        response.headers["HX-Reswap"] = "outerHTML"
    return response


def _render_or_client_error(
    request: Request,
    db: Session,
    filters: ListingSearchFilter,
    template_name: str,
    *,
    is_htmx: bool,
):
    try:
        return _render_result(request, db, filters, template_name)
    except ListingSearchValidationError:
        return _render_search_error(request, filters, is_htmx=is_htmx)


@router.get("/", response_class=HTMLResponse, name="home")
def index(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[ListingSearchFilter, Depends(parse_search_filter)],
):
    return _render_or_client_error(request, db, filters, "listings/index.html", is_htmx=False)


@router.get("/listings/search", response_class=HTMLResponse, name="search_listings")
def search_listings(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[ListingSearchFilter, Depends(parse_search_filter)],
    append: bool = Query(False),
):
    is_htmx = request.headers.get("HX-Request") == "true"
    template_name = (
        "listings/list_append.html"
        if is_htmx and append
        else "listings/list_partial.html"
        if is_htmx
        else "listings/index.html"
    )
    return _render_or_client_error(request, db, filters, template_name, is_htmx=is_htmx)


@router.get("/listings/complex/{complex_id}", response_class=HTMLResponse, name="complex_listings")
def complex_listings(
    complex_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[ListingSearchFilter, Depends(parse_search_filter)],
):
    started_at = perf_counter()
    applicant = get_request_user_profile(request)
    try:
        result = ListingSearchService(db).search_complex_listings(filters, complex_id, applicant)
    except ListingSearchValidationError:
        return HTMLResponse(
            '<p class="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100">'
            "단지 매물 페이지 cursor가 올바르지 않습니다.</p>",
            status_code=400,
        )
    result.diagnostics.loan_evaluation_time_ms += _enrich_listings_with_loans(result, applicant)
    favorite_listing_payloads = {
        item.article_id: _favorite_listing_payload(item) for item in result.items
    }
    page_url = request.url.remove_query_params("cursor")
    next_url = str(page_url.include_query_params(cursor=result.next_cursor)) if result.next_cursor else None
    response = templates.TemplateResponse(
        request,
        "listings/complex_listings_partial.html",
        context={
            "listings": result.items,
            "next_url": next_url,
            "complex_id": complex_id,
            "favorite_listing_payloads": favorite_listing_payloads,
        },
    )
    _log_search_diagnostics(result, started_at)
    return response
