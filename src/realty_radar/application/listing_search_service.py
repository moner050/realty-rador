from datetime import datetime, timedelta
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from realty_radar.constants import MortgageStatus, SortBy
from realty_radar.domain.listing.models import ListingFilterParams, SearchResult
from realty_radar.infrastructure.database.models import ApartmentComplex, Listing


class ListingSearchService:
    """통합 매물 다차원 필터링 및 검색 서비스."""

    def __init__(self, db: Session):
        self.db = db

    def search_listings(self, params: ListingFilterParams) -> SearchResult:
        """주어진 조건에 알맞은 매물 리스트 및 전체 개수 반환."""
        stmt = (
            select(Listing)
            .options(
                joinedload(Listing.complex),
                joinedload(Listing.source),
            )
            .where(Listing.status == "ACTIVE")
        )

        # 1. 키워드 검색 (단지명 또는 주소)
        complex_kw = getattr(params, "complex_keyword", None)
        if complex_kw:
            kw = f"%{complex_kw.strip()}%"
            stmt = stmt.outerjoin(Listing.complex).where(
                or_(
                    Listing.complex_name_raw.ilike(kw),
                    Listing.address_raw.ilike(kw),
                    ApartmentComplex.official_name.ilike(kw),
                )
            )

        # 2. 지역 선택 검색 (시/도, 시/군/구)
        region_kw_val = getattr(params, "region_name", None) or getattr(params, "region_keyword", None)
        if region_kw_val:
            rkw = f"%{region_kw_val.strip()}%"
            stmt = stmt.outerjoin(Listing.complex).where(
                or_(
                    Listing.address_raw.ilike(rkw),
                    ApartmentComplex.road_address.ilike(rkw),
                    Listing.complex_name_raw.ilike(rkw),
                )
            )

        # 3. 거래 유형 필터
        if params.transaction_type:
            stmt = stmt.where(Listing.transaction_type == params.transaction_type.value)

        # 4. 가격 범위 필터 (매매가/보증금)
        if params.min_price is not None:
            stmt = stmt.where(Listing.price_deposit >= params.min_price)
        if params.max_price is not None:
            stmt = stmt.where(Listing.price_deposit <= params.max_price)

        # 5. 전용면적 범위 필터
        if params.min_exclusive_area is not None:
            stmt = stmt.where(Listing.exclusive_area >= params.min_exclusive_area)
        if params.max_exclusive_area is not None:
            stmt = stmt.where(Listing.exclusive_area <= params.max_exclusive_area)

        # 6. 아파트 단지 조건 필터 (준공연도, 세대수)
        if params.min_construction_year or params.min_households:
            stmt = stmt.outerjoin(Listing.complex)
            if params.min_construction_year:
                stmt = stmt.where(ApartmentComplex.construction_year >= params.min_construction_year)
            if params.min_households:
                stmt = stmt.where(ApartmentComplex.total_households >= params.min_households)

        # 7. 융자 상태 조건
        if params.mortgage_status:
            stmt = stmt.where(Listing.mortgage_status == params.mortgage_status.value)
        elif getattr(params, "exclude_unknown_mortgage", False):
            stmt = stmt.where(Listing.mortgage_status != MortgageStatus.UNKNOWN.value)

        # 8. 수집 기간 필터
        if params.recent_days:
            since = datetime.now() - timedelta(days=params.recent_days)
            stmt = stmt.where(Listing.first_seen_at >= since)

        # 9. 정렬 옵션
        sort_val = params.sort_by
        if sort_val == SortBy.PRICE_ASC or sort_val == "price_asc":
            stmt = stmt.order_by(Listing.price_deposit.asc())
        elif sort_val == SortBy.PRICE_DESC or sort_val == "price_desc":
            stmt = stmt.order_by(Listing.price_deposit.desc())
        elif sort_val == SortBy.AREA_DESC or sort_val == "area_desc":
            stmt = stmt.order_by(Listing.exclusive_area.desc())
        else:
            stmt = stmt.order_by(Listing.first_seen_at.desc())

        # 전체 개수 산출 (카티시안 곱 경고 방지)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total_count = self.db.scalar(count_stmt) or 0

        # 페이징
        limit = getattr(params, "limit", getattr(params, "page_size", 50))
        offset = getattr(params, "offset", 0)
        if hasattr(params, "page") and params.page > 1 and offset == 0:
            offset = (params.page - 1) * limit

        stmt = stmt.offset(offset).limit(limit)
        results = self.db.scalars(stmt).unique().all()

        return SearchResult(items=list(results), total_count=total_count)
