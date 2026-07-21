from typing import Annotated
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.domain.analytics.price_comparison import PriceComparisonEngine
from realty_radar.infrastructure.database.models import ApartmentComplex, Listing
from realty_radar.infrastructure.database.session import get_db

router = APIRouter(prefix="/complexes", tags=["complexes"])
templates = Jinja2Templates(directory="src/realty_radar/web/templates")


@router.get("/{complex_id}", response_class=HTMLResponse, name="complex_detail")
def get_complex_detail(
    complex_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """아파트 단지 상세 정보, 매물 목록 및 실거래가 시세 비교 뷰."""
    stmt = select(ApartmentComplex).where(ApartmentComplex.id == complex_id)
    complex_item = db.scalar(stmt)

    if not complex_item:
        raise HTTPException(status_code=404, detail="해당 아파트 단지를 찾을 수 없습니다.")

    # 단지 소속 ACTIVE 매물 목록 조회
    listings_stmt = select(Listing).where(
        Listing.complex_id == complex_id,
        Listing.listing_status == "ACTIVE",
    ).order_by(Listing.first_seen_at.desc())

    listings = db.scalars(listings_stmt).all()

    # 시세 비교 MOCK 실거래가 목록 (예시: 6억 3500만원 평균)
    mock_trade_prices = [630_000_000, 640_000_000]
    avg_trade_price = sum(mock_trade_prices) // len(mock_trade_prices)

    # 각 매물별 실거래 대비 비교 분석
    analyzed_listings = []
    for item in listings:
        comp_res = PriceComparisonEngine.compare_price(item.sale_price, mock_trade_prices)
        analyzed_listings.append({
            "listing": item,
            "comparison": comp_res,
        })

    return templates.TemplateResponse(
        request=request,
        name="complexes/detail.html",
        context={
            "complex": complex_item,
            "analyzed_listings": analyzed_listings,
            "listing_count": len(listings),
            "avg_trade_price": avg_trade_price,
        },
    )


@router.post("/match", response_class=HTMLResponse, name="manual_complex_match")
def manual_complex_match(
    listing_id: Annotated[int, Form()],
    complex_id: Annotated[int, Form()],
    db: Annotated[Session, Depends(get_db)],
):
    """매물의 단지 ID를 수동 매핑 및 연결."""
    listing = db.scalar(select(Listing).where(Listing.id == listing_id))
    if not listing:
        raise HTTPException(status_code=404, detail="매물을 찾을 수 없습니다.")

    listing.complex_id = complex_id
    db.commit()

    return HTMLResponse(content=f'<span class="text-xs text-emerald-400 font-semibold">단지 연결 완료 (ID: {complex_id})</span>')
