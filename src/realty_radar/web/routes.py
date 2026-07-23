from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.constants import MortgageStatus, SortBy, TransactionType
from realty_radar.domain.listing.models import ListingFilterParams
from realty_radar.infrastructure.database.session import get_db

router = APIRouter()
templates = Jinja2Templates(directory="src/realty_radar/web/templates")


@router.get("/", response_class=HTMLResponse)
async def home_page(
    request: Request,
    complex_keyword: Optional[str] = Query(None),
    region_name: Optional[str] = Query(None),
    transaction_type: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    min_exclusive_area: Optional[float] = Query(None),
    max_exclusive_area: Optional[float] = Query(None),
    min_construction_year: Optional[int] = Query(None),
    min_households: Optional[int] = Query(None),
    mortgage_status: Optional[str] = Query(None),
    exclude_unknown_mortgage: bool = Query(False),
    recent_days: Optional[int] = Query(None),
    sort_by: str = Query("recent"),
    group_by_complex: bool = Query(False),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """메인 통합 매물 검색 페이지 HTML 렌더링."""
    search_service = ListingSearchService(db)

    tx_enum = TransactionType(transaction_type) if transaction_type else None
    mt_enum = MortgageStatus(mortgage_status) if mortgage_status else None
    sort_enum = SortBy(sort_by) if sort_by else SortBy.RECENT

    limit = 20
    offset = (page - 1) * limit

    params = ListingFilterParams(
        complex_keyword=complex_keyword,
        region_name=region_name,
        transaction_type=tx_enum,
        min_price=min_price,
        max_price=max_price,
        min_exclusive_area=min_exclusive_area,
        max_exclusive_area=max_exclusive_area,
        min_construction_year=min_construction_year,
        min_households=min_households,
        mortgage_status=mt_enum,
        exclude_unknown_mortgage=exclude_unknown_mortgage,
        recent_days=recent_days,
        sort_by=sort_enum,
        limit=limit,
        offset=offset,
        group_by_complex=group_by_complex,
    )

    search_res = search_service.search_listings(params)
    total_pages = max(1, (search_res.total_count + limit - 1) // limit)

    return templates.TemplateResponse(
        "listings/index.html",
        {
            "request": request,
            "listings": search_res.items,
            "total_count": search_res.total_count,
            "current_page": page,
            "total_pages": total_pages,
            "filters": params,
            "search_res": search_res,
            "result": search_res,
        },
    )


@router.get("/listings/search", response_class=HTMLResponse)
async def search_listings_partial(
    request: Request,
    complex_keyword: Optional[str] = Query(None),
    region_name: Optional[str] = Query(None),
    transaction_type: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    min_exclusive_area: Optional[float] = Query(None),
    max_exclusive_area: Optional[float] = Query(None),
    min_construction_year: Optional[int] = Query(None),
    min_households: Optional[int] = Query(None),
    mortgage_status: Optional[str] = Query(None),
    exclude_unknown_mortgage: bool = Query(False),
    recent_days: Optional[int] = Query(None),
    sort_by: str = Query("recent"),
    group_by_complex: bool = Query(False),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """HTMX 비동기 리스트 조각 HTML 렌더링."""
    search_service = ListingSearchService(db)

    tx_enum = TransactionType(transaction_type) if transaction_type else None
    mt_enum = MortgageStatus(mortgage_status) if mortgage_status else None
    sort_enum = SortBy(sort_by) if sort_by else SortBy.RECENT

    limit = 20
    offset = (page - 1) * limit

    params = ListingFilterParams(
        complex_keyword=complex_keyword,
        region_name=region_name,
        transaction_type=tx_enum,
        min_price=min_price,
        max_price=max_price,
        min_exclusive_area=min_exclusive_area,
        max_exclusive_area=max_exclusive_area,
        min_construction_year=min_construction_year,
        min_households=min_households,
        mortgage_status=mt_enum,
        exclude_unknown_mortgage=exclude_unknown_mortgage,
        recent_days=recent_days,
        sort_by=sort_enum,
        limit=limit,
        offset=offset,
        group_by_complex=group_by_complex,
    )

    print(f"[DEBUG_ROUTE] group_by_complex received: {group_by_complex} (type: {type(group_by_complex)})")
    search_res = search_service.search_listings(params)
    print(f"[DEBUG_ROUTE] search_res.is_grouped: {search_res.is_grouped}, len(grouped_items): {len(search_res.grouped_items)}")
    total_pages = max(1, (search_res.total_count + limit - 1) // limit)

    return templates.TemplateResponse(
        "listings/list_partial.html",
        {
            "request": request,
            "listings": search_res.items,
            "total_count": search_res.total_count,
            "current_page": page,
            "total_pages": total_pages,
            "filters": params,
            "search_res": search_res,
            "result": search_res,
        },
    )
