from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from realty_radar.application.crawl_job_service import CrawlJobService
from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.constants import MortgageStatus, TransactionType
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.jinja_filters import register_jinja_filters

router = APIRouter()
templates = Jinja2Templates(directory="src/realty_radar/web/templates")
register_jinja_filters(templates)


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
    sort_by: str = Query("recent"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ListingSearchFilter:
    """쿼리 파라미터로부터 ListingSearchFilter DTO 객체 안전 파싱."""
    trans_enum = TransactionType(transaction_type) if transaction_type and transaction_type != "" else None
    mortgage_enum = MortgageStatus(mortgage_status) if mortgage_status and mortgage_status != "" else None

    return ListingSearchFilter(
        complex_keyword=complex_keyword if complex_keyword != "" else None,
        region_keyword=region_keyword if region_keyword != "" else None,
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
        sort_by=sort_by if sort_by != "" else "recent",
        page=page,
        page_size=page_size,
    )


@router.get("/", response_class=HTMLResponse, name="home")
def index(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[ListingSearchFilter, Depends(parse_search_filter)],
):
    """홈 메인 페이지 (진행도 위젯 서머리 및 검색 결과 렌더링)."""
    search_service = ListingSearchService(db)
    result = search_service.search_listings(filters)

    job_service = CrawlJobService(db)
    crawl_summary = job_service.get_progress_summary()

    return templates.TemplateResponse(
        request=request,
        name="listings/index.html",
        context={
            "result": result,
            "filters": filters,
            "crawl_summary": crawl_summary,
        },
    )


@router.get("/listings/search", response_class=HTMLResponse, name="search_listings_partial")
def search_listings_partial(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    filters: Annotated[ListingSearchFilter, Depends(parse_search_filter)],
):
    """HTMX 요청용 매물 리스트 부분(partial) HTML 렌더링."""
    search_service = ListingSearchService(db)
    result = search_service.search_listings(filters)

    return templates.TemplateResponse(
        request=request,
        name="listings/list_partial.html",
        context={
            "result": result,
            "filters": filters,
        },
    )
