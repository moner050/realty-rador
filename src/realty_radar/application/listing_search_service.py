from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, contains_eager

from realty_radar.constants import MortgageStatus, SortBy, TransactionType
from realty_radar.domain.listing.models import ListingFilterParams, SearchResult
from realty_radar.domain.loan.entities import ApplicantProfile
from realty_radar.infrastructure.database.models import ApartmentComplex, CrawlSource, Listing


class ListingSearchService:
    """통합 매물 다차원 필터링 및 검색 서비스."""

    def __init__(self, db: Session):
        self.db = db

    def search_listings(self, params: ListingFilterParams, applicant: ApplicantProfile | None = None) -> SearchResult:
        """주어진 조건에 알맞은 매물 리스트 및 전체 개수 반환."""
        # 단일 LEFT OUTER JOIN 문으로 고정하여 다중 조인 꼬임 방지
        stmt = (
            select(Listing)
            .outerjoin(Listing.complex)
            .outerjoin(Listing.source)
            .options(
                contains_eager(Listing.complex),
                contains_eager(Listing.source),
            )
            .where(Listing.status == "ACTIVE")
        )

        # 정책대출 필터링 조건 추가
        if getattr(params, "only_eligible_loans", False):
            # 1. 정책 대출은 무주택자만 대상임
            if not applicant or not applicant.is_homeless:
                return SearchResult(items=[], total_count=0, page=getattr(params, "page", 1), page_size=getattr(params, "limit", getattr(params, "page_size", 20)))

            # 2. 모든 정책 대출은 전용면적 85㎡ 이하 매물만 대상임
            stmt = stmt.where(Listing.exclusive_area <= Decimal("85.0"))

            # 3. 소득 한도 및 개인/신혼/신생아 자격 반영
            is_newlywed = applicant.is_newlywed
            has_multi_children = applicant.child_count >= 2
            is_first_buyer = applicant.is_first_home_buyer
            has_newborn = getattr(applicant, "has_newborn", False)

            # (1) 디딤돌 소득 조건 (일반 6천, 생초/2자녀+ 7천, 신혼 8.5천)
            didimdol_income_limit = 85_000_000 if is_newlywed else (70_000_000 if (is_first_buyer or has_multi_children) else 60_000_000)
            is_didimdol_eligible = applicant.annual_income <= didimdol_income_limit

            # (2) 보금자리론 소득 조건 (일반 7천, 신혼 8.5천, 1자녀 9천, 2자녀+ 1억)
            if has_multi_children:
                bogumjari_income_limit = 100_000_000
            elif applicant.child_count == 1:
                bogumjari_income_limit = 90_000_000
            elif is_newlywed:
                bogumjari_income_limit = 85_000_000
            else:
                bogumjari_income_limit = 70_000_000
            is_bogumjari_eligible = applicant.annual_income <= bogumjari_income_limit

            # (3) 신생아 특례구입 소득 조건 (2년 이내 출산 가구 & 2억 원 이하)
            is_neonatal_eligible = has_newborn and (applicant.annual_income <= 200_000_000)

            # (4) 버팀목 전세 소득 조건 (일반/청년 5천, 신혼/다자녀 7.5천)
            beotimmok_income_limit = 75_000_000 if (is_newlywed or has_multi_children) else 50_000_000
            is_beotimmok_eligible = applicant.annual_income <= beotimmok_income_limit

            if not any([is_didimdol_eligible, is_bogumjari_eligible, is_neonatal_eligible, is_beotimmok_eligible]):
                return SearchResult(items=[], total_count=0, page=getattr(params, "page", 1), page_size=getattr(params, "limit", getattr(params, "page_size", 20)))

            total_cap = getattr(applicant, "total_capital", applicant.net_assets)
            conditions = []

            # 매매(SALE) 상한 한도 계산
            sale_limits = []

            if is_didimdol_eligible:
                didimdol_price_limit = 600_000_000 if (is_newlywed or has_multi_children) else 500_000_000
                didimdol_max_loan = 320_000_000 if (is_newlywed or has_multi_children) else (240_000_000 if is_first_buyer else 200_000_000)
                sale_limits.append(min(didimdol_price_limit, total_cap + didimdol_max_loan))

            if is_bogumjari_eligible:
                bogumjari_price_limit = 600_000_000
                bogumjari_max_loan = 420_000_000 if is_first_buyer else (400_000_000 if has_multi_children else 360_000_000)
                sale_limits.append(min(bogumjari_price_limit, total_cap + bogumjari_max_loan))

            if is_neonatal_eligible:
                neonatal_price_limit = 900_000_000
                neonatal_max_loan = 500_000_000
                sale_limits.append(min(neonatal_price_limit, total_cap + neonatal_max_loan))

            if sale_limits:
                max_sale_limit = max(sale_limits)
                conditions.append(
                    (Listing.transaction_type == TransactionType.SALE.value) &
                    (Listing.price_deposit <= max_sale_limit)
                )

            # 전세/월세(JEONSE/MONTHLY_RENT) 상한 한도 계산
            if is_beotimmok_eligible:
                beotimmok_deposit_limit = 500_000_000 if (is_newlywed or has_multi_children) else 300_000_000
                beotimmok_max_loan = 300_000_000 if is_newlywed else 120_000_000
                purchasable_rent_limit = min(beotimmok_deposit_limit, total_cap + beotimmok_max_loan)
                conditions.append(
                    (Listing.transaction_type.in_([TransactionType.JEONSE.value, TransactionType.MONTHLY_RENT.value])) &
                    (Listing.price_deposit <= purchasable_rent_limit)
                )

            if conditions:
                stmt = stmt.where(or_(*conditions))
            else:
                return SearchResult(items=[], total_count=0, page=getattr(params, "page", 1), page_size=getattr(params, "limit", getattr(params, "page_size", 20)))

        # 1. 키워드 검색 (단지명 또는 주소)
        complex_kw = getattr(params, "complex_keyword", None)
        if complex_kw:
            kw = f"%{complex_kw.strip()}%"
            stmt = stmt.where(
                or_(
                    Listing.complex_name_raw.ilike(kw),
                    Listing.address_raw.ilike(kw),
                    ApartmentComplex.official_name.ilike(kw),
                )
            )

        # 2. 지역 선택 검색 (시/도, 시/군/구 전용 주소 정밀 필터링)
        region_kw_val = getattr(params, "region_name", None) or getattr(params, "region_keyword", None)
        if region_kw_val and region_kw_val.strip():
            raw_region = region_kw_val.strip()
            tokens = raw_region.split()
            region_conditions = []

            if len(tokens) >= 2:
                sido_token = tokens[0]
                sigungu_token = tokens[1]

                sido_variants = [sido_token]
                if "서울" in sido_token:
                    sido_variants = ["서울", "서울시", "서울특별시"]
                elif "경기" in sido_token:
                    sido_variants = ["경기", "경기도"]
                elif "인천" in sido_token:
                    sido_variants = ["인천", "인천시", "인천광역시"]

                for s_var in sido_variants:
                    pat = f"%{s_var}%{sigungu_token}%"
                    region_conditions.append(Listing.address_raw.ilike(pat))
                    region_conditions.append(ApartmentComplex.road_address.ilike(pat))

                stmt = stmt.where(or_(*region_conditions))
            else:
                token = tokens[0]
                sido_variants = [token]
                if "서울" in token:
                    sido_variants = ["서울", "서울시", "서울특별시"]
                elif "경기" in token:
                    sido_variants = ["경기", "경기도"]
                elif "인천" in token:
                    sido_variants = ["인천", "인천시", "인천광역시"]

                for s_var in sido_variants:
                    region_conditions.append(Listing.address_raw.ilike(f"%{s_var}%"))
                    region_conditions.append(ApartmentComplex.road_address.ilike(f"%{s_var}%"))

                stmt = stmt.where(or_(*region_conditions))

        # 3. 거래 유형 필터
        if params.transaction_type:
            stmt = stmt.where(Listing.transaction_type == params.transaction_type.value)

        # 4. 가격 및 전월세 보증금/월세액 범위 필터
        if params.min_price is not None:
            stmt = stmt.where(Listing.price_deposit >= params.min_price)
        if params.max_price is not None:
            stmt = stmt.where(Listing.price_deposit <= params.max_price)

        min_dep = getattr(params, "min_deposit", None)
        if min_dep is not None:
            stmt = stmt.where(Listing.price_deposit >= min_dep)

        max_dep = getattr(params, "max_deposit", None)
        if max_dep is not None:
            stmt = stmt.where(Listing.price_deposit <= max_dep)

        max_mrent = getattr(params, "max_monthly_rent", None)
        if max_mrent is not None:
            stmt = stmt.where(Listing.price_monthly <= max_mrent)

        # 5. 전용면적 범위 필터
        if params.min_exclusive_area is not None:
            stmt = stmt.where(Listing.exclusive_area >= params.min_exclusive_area)
        if params.max_exclusive_area is not None:
            stmt = stmt.where(Listing.exclusive_area <= params.max_exclusive_area)

        # 6. 아파트 단지 조건 필터 (준공연도, 세대수)
        if params.min_construction_year:
            stmt = stmt.where(ApartmentComplex.construction_year >= params.min_construction_year)
        if params.min_households:
            stmt = stmt.where(ApartmentComplex.total_households >= params.min_households)

        # 7. 융자 상태 조건
        if params.mortgage_status:
            stmt = stmt.where(Listing.mortgage_status == params.mortgage_status.value)
        elif getattr(params, "exclude_unknown_mortgage", False):
            stmt = stmt.where(Listing.mortgage_status != MortgageStatus.UNKNOWN.value)

        # 8. 수집 기간 및 수집 출처 필터
        if params.recent_days:
            since = datetime.now() - timedelta(days=params.recent_days)
            stmt = stmt.where(Listing.first_seen_at >= since)

        src_code = getattr(params, "source_code", None)
        if src_code:
            stmt = stmt.where(CrawlSource.code == src_code)

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

        page_val = getattr(params, "page", 1)
        return SearchResult(items=list(results), total_count=total_count, page=page_val, page_size=limit)
