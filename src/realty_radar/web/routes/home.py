"""v2 keyset listing search routes."""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.domain.listing.filters import ListingSearchFilter
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


def _code_list(values: list[str] | None) -> list[int] | None:
    parsed = [int(token) for value in values or [] for token in value.split(",") if token.strip().isdigit()]
    return parsed or None


def parse_search_filter(
    region_code: str | None = Query(None),
    sido_code: str | None = Query(None),
    sigungu_code: str | None = Query(None),
    complex_keyword: str | None = Query(None),
    transaction_type: str | None = Query(None),
    min_price: str | None = Query(None),
    max_price: str | None = Query(None),
    max_monthly_rent: str | None = Query(None),
    min_exclusive_area: str | None = Query(None),
    max_exclusive_area: str | None = Query(None),
    min_construction_year: str | None = Query(None),
    min_households: str | None = Query(None),
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
    transaction = TRADE_TYPE_CODES.get((transaction_type or "").upper())
    return ListingSearchFilter(
        region_code=_optional_int(region_code),
        sido_code=_optional_int(sido_code),
        sigungu_code=_optional_int(sigungu_code),
        complex_keyword=complex_keyword.strip() if complex_keyword and complex_keyword.strip() else None,
        trade_type=transaction,
        min_price=_optional_int(min_price),
        max_price=_optional_int(max_price),
        max_monthly_rent=_optional_int(max_monthly_rent),
        min_exclusive_area=_optional_decimal(min_exclusive_area),
        max_exclusive_area=_optional_decimal(max_exclusive_area),
        min_construction_year=_optional_int(min_construction_year),
        min_households=_optional_int(min_households),
        direction_codes=_code_list(direction_codes),
        floor_bands=_code_list(floor_bands),
        sort_by=sort_by,
        page_size=page_size,
        cursor=cursor,
        exclude_short_term=exclude_short_term,
        exclude_first_floor=exclude_first_floor,
        group_by_complex=group_by_complex,
        only_eligible_loans=only_eligible_loans,
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
    next_url = str(request.url.include_query_params(cursor=result.next_cursor)) if result.next_cursor else None
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
        },
    )


@router.get("/", response_class=HTMLResponse, name="home")
def index(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[ListingSearchFilter, Depends(parse_search_filter)],
):
    return _render_result(request, db, filters, "listings/index.html")


@router.get("/listings/search", response_class=HTMLResponse, name="search_listings")
def search_listings(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[ListingSearchFilter, Depends(parse_search_filter)],
):
    template_name = "listings/list_partial.html" if request.headers.get("HX-Request") == "true" else "listings/index.html"
    return _render_result(request, db, filters, template_name)
