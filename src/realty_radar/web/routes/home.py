from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.constants import MortgageStatus, TransactionType
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.domain.loan.evaluator import LoanRuleEvaluator
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.auth import is_authenticated
from realty_radar.web.jinja_filters import register_jinja_filters
from realty_radar.web.routes.settings import load_user_profile

router = APIRouter()
templates = Jinja2Templates(directory="src/realty_radar/web/templates")
register_jinja_filters(templates)


_GLOBAL_LOAN_EVALUATOR = LoanRuleEvaluator()


def _enrich_listings_with_loans(result: Any, db: Session, applicant: Any = None) -> None:
    """매물 목록에 대해 인메모리 대출 평가 결과 바인딩."""
    if not result or not getattr(result, "items", None):
        return
    evaluator = _GLOBAL_LOAN_EVALUATOR
    for item in result.items:
        try:
            tx_type = item.transaction_type
            if isinstance(tx_type, str):
                tx_type = TransactionType(tx_type)

            didimdol_res = evaluator.evaluate_didimdol(
                transaction_type=tx_type,
                price=item.price_deposit,
                exclusive_area=item.exclusive_area,
                address=item.address_raw,
                applicant=applicant,
            )
            bogumjari_res = evaluator.evaluate_bogumjari(
                transaction_type=tx_type,
                price=item.price_deposit,
                exclusive_area=item.exclusive_area,
                address=item.address_raw,
                applicant=applicant,
            )
            neonatal_res = evaluator.evaluate_neonatal_purchase(
                transaction_type=tx_type,
                price=item.price_deposit,
                exclusive_area=item.exclusive_area,
                address=item.address_raw,
                applicant=applicant,
            )
            beotimmok_res = evaluator.evaluate_beotimmok(
                transaction_type=tx_type,
                deposit=item.price_deposit,
                exclusive_area=item.exclusive_area,
                address=item.address_raw,
                applicant=applicant,
            )

            all_evals = [didimdol_res, bogumjari_res, neonatal_res, beotimmok_res]
            item.eligible_loans = [res for res in all_evals if res.is_eligible]
        except Exception:
            item.eligible_loans = []


def _to_int(val: str | int | None) -> int | None:
    """빈 문자열("") 또는 None을 안전하게 int로 변환."""
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _to_decimal(val: str | float | Decimal | None) -> Decimal | None:
    """빈 문자열("") 또는 None을 안전하게 Decimal로 변환."""
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


def parse_search_filter(
    complex_keyword: str | None = Query(None),
    region_name: str | None = Query(None),
    region_keyword: str | None = Query(None),
    sido: str | None = Query(None),
    city: str | None = Query(None),
    county: str | None = Query(None),
    district: str | None = Query(None),
    transaction_type: str | None = Query(None),
    min_price: str | None = Query(None),
    max_price: str | None = Query(None),
    min_deposit: str | None = Query(None),
    max_deposit: str | None = Query(None),
    max_monthly_rent: str | None = Query(None),
    min_exclusive_area: str | None = Query(None),
    max_exclusive_area: str | None = Query(None),
    mortgage_status: str | None = Query(None),
    exclude_unknown_mortgage: bool = Query(False),
    min_construction_year: str | None = Query(None),
    min_households: str | None = Query(None),
    recent_days: str | None = Query(None),
    source_code: str | None = Query(None),
    sort_by: str = Query("price_asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    only_eligible_loans: bool = Query(False),
    exclude_short_term: bool = Query(True),
    group_by_complex: bool = Query(False),
    direction: str | None = Query(None),
    directions: list[str] | None = Query(None),
    floor: str | None = Query(None),
    floors: list[str] | None = Query(None),
    exclude_first_floor: bool = Query(False),
) -> ListingSearchFilter:
    """쿼리 파라미터로부터 ListingSearchFilter DTO 객체 안전 파싱 (기본 정렬: 가격 낮은순)."""
    trans_enum = TransactionType(transaction_type) if transaction_type and transaction_type != "" else None
    mortgage_enum = MortgageStatus(mortgage_status) if mortgage_status and mortgage_status != "" else None

    # region_name(hidden input)과 region_keyword 중 유효한 값 통합
    effective_region = None
    if region_name and region_name.strip():
        effective_region = region_name.strip()
    elif region_keyword and region_keyword.strip():
        effective_region = region_keyword.strip()

    return ListingSearchFilter(
        complex_keyword=complex_keyword if complex_keyword != "" else None,
        region_keyword=effective_region,
        region_name=effective_region,
        sido=sido if sido and sido != "" else None,
        city=city if city and city != "" else None,
        county=county if county and county != "" else None,
        district=district if district and district != "" else None,
        transaction_type=trans_enum,
        min_price=_to_int(min_price),
        max_price=_to_int(max_price),
        min_deposit=_to_int(min_deposit),
        max_deposit=_to_int(max_deposit),
        max_monthly_rent=_to_int(max_monthly_rent),
        min_exclusive_area=_to_decimal(min_exclusive_area),
        max_exclusive_area=_to_decimal(max_exclusive_area),
        mortgage_status=mortgage_enum,
        exclude_unknown_mortgage=exclude_unknown_mortgage,
        min_construction_year=_to_int(min_construction_year),
        min_households=_to_int(min_households),
        recent_days=_to_int(recent_days),
        source_code=source_code if source_code != "" else None,
        sort_by=sort_by if sort_by != "" else "price_asc",
        page=page,
        page_size=page_size,
        only_eligible_loans=only_eligible_loans,
        direction=direction if direction and direction != "" else None,
        directions=directions,
        floor=floor if floor and floor != "" else None,
        floors=floors,
        exclude_first_floor=exclude_first_floor,
        exclude_short_term=exclude_short_term,
        group_by_complex=group_by_complex,
    )


from realty_radar.web.auth import SESSION_COOKIE_NAME, is_authenticated, verify_session_token
from realty_radar.web.routes.settings import get_request_user_profile, load_user_search_filter, save_user_search_filter


@router.get("/", response_class=HTMLResponse, name="home")
def index(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[ListingSearchFilter, Depends(parse_search_filter)],
):
    """홈 메인 페이지 (진행도 위젯 서머리 및 검색 결과 렌더링)."""
    search_service = ListingSearchService(db)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_token(token)

    # URL 쿼리 파라미터가 없고 로그인 사용자인 경우 저장된 사용자 필터 복원
    if username and not request.query_params:
        saved_filter = load_user_search_filter(username)
        if saved_filter:
            filters = saved_filter
    elif username:
        save_user_search_filter(filters, username)

    current_profile = get_request_user_profile(request)
    result = search_service.search_listings(filters, applicant=current_profile)
    _enrich_listings_with_loans(result, db, current_profile)

    return templates.TemplateResponse(
        request,
        "listings/index.html",
        context={
            "result": result,
            "listings": result.items,
            "total_count": result.total_count,
            "page": result.page,
            "page_size": result.page_size,
            "total_pages": (result.total_count + result.page_size - 1) // result.page_size if result.page_size else 1,
            "filters": filters,
            "applicant": current_profile,
            "is_authenticated": is_authenticated(request),
        },
    )


@router.get("/listings/search", response_class=HTMLResponse, name="search_listings")
def search_listings(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[ListingSearchFilter, Depends(parse_search_filter)],
):
    """HTMX 비동기 부분 갱신 전용 매물 검색 라우터."""
    search_service = ListingSearchService(db)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session_token(token)
    if username:
        save_user_search_filter(filters, username)

    current_profile = get_request_user_profile(request)
    result = search_service.search_listings(filters, applicant=current_profile)
    _enrich_listings_with_loans(result, db, current_profile)

    is_htmx = request.headers.get("HX-Request") == "true"
    template_name = "listings/list_partial.html" if is_htmx else "listings/index.html"

    return templates.TemplateResponse(
        request,
        template_name,
        context={
            "result": result,
            "listings": result.items,
            "total_count": result.total_count,
            "page": result.page,
            "page_size": result.page_size,
            "total_pages": (result.total_count + result.page_size - 1) // result.page_size if result.page_size else 1,
            "filters": filters,
            "applicant": current_profile,
            "is_authenticated": is_authenticated(request),
        },
    )
