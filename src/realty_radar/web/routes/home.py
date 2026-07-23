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
from realty_radar.web.jinja_filters import register_jinja_filters
from realty_radar.web.routes.settings import session_user_profile

router = APIRouter()
templates = Jinja2Templates(directory="src/realty_radar/web/templates")
register_jinja_filters(templates)


def _enrich_listings_with_loans(result: Any, db: Session) -> None:
    """검색된 매물 목록에 대해 순수 인메모리 빠른 정책 대출 평가 결과를 바인딩 (N+1 DB 쿼리 제거)."""
    if not result or not getattr(result, "items", None):
        return
    evaluator = LoanRuleEvaluator()
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
                applicant=session_user_profile,
            )
            bogumjari_res = evaluator.evaluate_bogumjari(
                transaction_type=tx_type,
                price=item.price_deposit,
                exclusive_area=item.exclusive_area,
                address=item.address_raw,
                applicant=session_user_profile,
            )
            neonatal_res = evaluator.evaluate_neonatal_purchase(
                transaction_type=tx_type,
                price=item.price_deposit,
                exclusive_area=item.exclusive_area,
                address=item.address_raw,
                applicant=session_user_profile,
            )
            beotimmok_res = evaluator.evaluate_beotimmok(
                transaction_type=tx_type,
                deposit=item.price_deposit,
                exclusive_area=item.exclusive_area,
                address=item.address_raw,
                applicant=session_user_profile,
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
        exclude_short_term=exclude_short_term,
    )


@router.get("/", response_class=HTMLResponse, name="home")
def index(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[ListingSearchFilter, Depends(parse_search_filter)],
):
    """홈 메인 페이지 (진행도 위젯 서머리 및 검색 결과 렌더링)."""
    search_service = ListingSearchService(db)
    result = search_service.search_listings(filters, applicant=session_user_profile)
    _enrich_listings_with_loans(result, db)

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
            "applicant": session_user_profile,
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
    result = search_service.search_listings(filters, applicant=session_user_profile)
    _enrich_listings_with_loans(result, db)

    return templates.TemplateResponse(
        request,
        "listings/list_partial.html",
        context={
            "result": result,
            "listings": result.items,
            "total_count": result.total_count,
            "page": result.page,
            "page_size": result.page_size,
            "total_pages": (result.total_count + result.page_size - 1) // result.page_size if result.page_size else 1,
            "filters": filters,
            "applicant": session_user_profile,
        },
    )
