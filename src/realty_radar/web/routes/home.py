"""v2 keyset listing search routes."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.crawler.adapters.site_a.region_codes import SIDO_CODES, SIGUNGU_CODES
from realty_radar.domain.listing.filters import ListingSearchFilter, ListingSearchValidationError
from realty_radar.domain.loan.evaluator import LoanRuleEvaluator
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.auth import SESSION_COOKIE_NAME, is_authenticated, verify_session_token
from realty_radar.web.jinja_filters import register_jinja_filters
from realty_radar.web.routes.settings import get_request_user_profile, load_user_search_filter, save_user_search_filter


router = APIRouter()
templates = Jinja2Templates(directory="src/realty_radar/web/templates")
register_jinja_filters(templates)
_LOAN_EVALUATOR = LoanRuleEvaluator()

TRADE_TYPE_CODES = {"SALE": 1, "JEONSE": 2, "MONTHLY_RENT": 3, "SHORT_TERM": 4}
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
    return [
        {
            "name": sido_name,
            "code": int(sido_code) // 100_000_000,
            "sigungu": [
                {"name": sigungu_name, "code": int(sigungu_code) // 100_000}
                for sigungu_name, sigungu_code in SIGUNGU_CODES[sido_name].items()
            ],
        }
        for sido_name, sido_code in SIDO_CODES.items()
    ]


def _region_labels() -> tuple[dict[int, str], dict[int, str]]:
    return (
        {int(code) // 100_000_000: name for name, code in SIDO_CODES.items()},
        {
            int(code) // 100_000: name
            for sigungu in SIGUNGU_CODES.values()
            for name, code in sigungu.items()
        },
    )


def parse_search_filter(
    region_code: str | None = Query(None),
    sido_code: str | None = Query(None),
    sigungu_code: str | None = Query(None),
    complex_keyword: str | None = Query(None),
    transaction_type: str | None = Query(None),
    transaction_types: list[str] | None = Query(None),
    trade_types: list[str] | None = Query(None),
    min_price: str | None = Query(None),
    max_price: str | None = Query(None),
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
    parsed_recent_days = _optional_int(recent_days)
    if parsed_recent_days is None:
        parsed_recent_days = _optional_int(recent_days_custom)
    parsed_exclude_short_term = _request_bool(exclude_short_term, True)
    if trades and 4 in trades:
        parsed_exclude_short_term = False
    return ListingSearchFilter(
        region_code=_optional_int(region_code),
        sido_code=_optional_int(sido_code),
        sigungu_code=_optional_int(sigungu_code),
        complex_keyword=(keyword.strip() if (keyword := _request_string(complex_keyword)) and keyword.strip() else None),
        trade_type=trades[0] if trades and len(trades) == 1 else None,
        trade_types=trades,
        min_price=parsed_min_price if parsed_min_price is not None else _optional_int(min_deposit),
        max_price=parsed_max_price if parsed_max_price is not None else _optional_int(max_deposit),
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


def _enrich_listings_with_loans(result, applicant) -> None:
    for item in result.items:
        transaction_type = {1: "SALE", 2: "JEONSE", 3: "MONTHLY_RENT", 4: "MONTHLY_RENT"}.get(item.trade_type)
        if transaction_type is None:
            item.eligible_loans = []
            continue
        try:
            from realty_radar.constants import TransactionType

            tx = TransactionType(transaction_type)
            area = Decimal(item.exclusive_area_x100) / 100
            evaluations = (
                _LOAN_EVALUATOR.evaluate_didimdol(tx, item.primary_price, area, item.address, applicant),
                _LOAN_EVALUATOR.evaluate_bogumjari(tx, item.primary_price, area, item.address, applicant),
                _LOAN_EVALUATOR.evaluate_neonatal_purchase(tx, item.primary_price, area, item.address, applicant),
                _LOAN_EVALUATOR.evaluate_beotimmok(tx, item.primary_price, area, item.address, applicant),
            )
            item.eligible_loans = [evaluation for evaluation in evaluations if evaluation.is_eligible]
        except Exception:
            item.eligible_loans = []


def _render_result(request: Request, db: Session, filters: ListingSearchFilter, template_name: str):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_token(token)
    if username and not request.query_params:
        filters = load_user_search_filter(username) or filters
    elif username:
        save_user_search_filter(filters, username)
    applicant = get_request_user_profile(request)
    result = ListingSearchService(db).search_listings(filters, applicant=applicant)
    _enrich_listings_with_loans(result, applicant)
    next_url = str(request.url.include_query_params(cursor=result.next_cursor, append="1")) if result.next_cursor else None
    sido_labels, sigungu_labels = _region_labels()
    return templates.TemplateResponse(
        request,
        template_name,
        context={
            "result": result,
            "listings": result.items,
            "filters": filters,
            "next_url": next_url,
            "applicant": applicant,
            "is_authenticated": is_authenticated(request),
            "region_options": _region_options(),
            "sort_options": SORT_OPTIONS,
            "sido_labels": sido_labels,
            "sigungu_labels": sigungu_labels,
        },
    )


def _render_search_error(request: Request, filters: ListingSearchFilter, *, is_htmx: bool):
    sido_labels, sigungu_labels = _region_labels()
    context = {
        "filters": filters,
        "region_options": _region_options(),
        "sort_options": SORT_OPTIONS,
        "sido_labels": sido_labels,
        "sigungu_labels": sigungu_labels,
        "is_authenticated": is_authenticated(request),
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
