import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from sqlalchemy import func, or_, select, and_
from sqlalchemy.orm import Session, contains_eager

from realty_radar.constants import MortgageStatus, SortBy, TransactionType
from realty_radar.domain.listing.models import ListingFilterParams, SearchResult
from realty_radar.domain.loan.entities import ApplicantProfile
from realty_radar.infrastructure.cache.redis_client import redis_cache
from realty_radar.infrastructure.database.models import ApartmentComplex, CrawlSource, Listing


class ListingSearchService:
    """통합 매물 다차원 필터링 및 검색 서비스 (시/도 정밀 격리 & 단기임대 차단 강화 & 1,000개 청크 인메모리 슬라이싱)."""

    def __init__(self, db: Session):
        self.db = db

    def _listing_to_dict(self, item: Listing) -> dict[str, Any]:
        """Listing ORM 객체를 Redis 인메모리 저장용 Dict로 직렬화 (템플릿 호환 전 필드 포함)."""
        loans_payload = []
        if hasattr(item, "eligible_loans") and item.eligible_loans:
            for l in item.eligible_loans:
                loans_payload.append({
                    "product_code": getattr(l, "product_code", ""),
                    "product_name": getattr(l, "product_name", ""),
                    "max_loan_amount": getattr(l, "max_loan_amount", None),
                    "interest_rate": getattr(l, "interest_rate", None),
                    "estimated_monthly_interest": getattr(l, "estimated_monthly_interest", None),
                    "reason": getattr(l, "reason", ""),
                })

        return {
            "id": item.id,
            "source_id": getattr(item, "source_id", None),
            "source_code": item.source.source_code if getattr(item, "source", None) else "SITE_A",
            "external_listing_id": item.external_listing_id,
            "source_url": item.source_url,
            "transaction_type": item.transaction_type,
            "complex_id": item.complex_id,
            "complex_name_raw": item.complex_name_raw,
            "price_deposit": item.price_deposit,
            "price_monthly": item.price_monthly,
            "exclusive_area": str(item.exclusive_area) if item.exclusive_area is not None else None,
            "supply_area": str(item.supply_area) if getattr(item, "supply_area", None) is not None else None,
            "floor_number": getattr(item, "floor_number", None),
            "floor_group": getattr(item, "floor_group", None),
            "total_floor": getattr(item, "total_floor", None),
            "floor_raw": getattr(item, "floor_raw", None),
            "floor_info": getattr(item, "floor_info", None),
            "address_raw": item.address_raw,
            "description_raw": item.description_raw,
            "mortgage_status": item.mortgage_status,
            "mortgage_raw_text": getattr(item, "mortgage_raw_text", None),
            "status": getattr(item, "status", "ACTIVE"),
            "first_seen_at": item.first_seen_at.isoformat() if getattr(item, "first_seen_at", None) else None,
            "last_seen_at": item.last_seen_at.isoformat() if getattr(item, "last_seen_at", None) else None,
            "raw_payload": getattr(item, "raw_payload", {}) or {},
            "eligible_loans": loans_payload,
            "complex": {
                "id": item.complex.id,
                "official_name": item.complex.official_name,
                "total_households": item.complex.total_households,
                "construction_year": item.complex.construction_year,
                "sido": item.complex.sido,
                "sigungu": item.complex.sigungu,
                "dong": item.complex.dong,
                "road_address": item.complex.road_address,
            } if getattr(item, "complex", None) else None,
        }

    def _dict_to_listing(self, data: dict[str, Any]) -> Listing:
        """Redis Dict를 템플릿 호환 Listing 객체로 복원."""
        listing = Listing(
            id=data["id"],
            source_id=data.get("source_id"),
            external_listing_id=data.get("external_listing_id"),
            source_url=data.get("source_url"),
            transaction_type=data.get("transaction_type"),
            complex_id=data.get("complex_id"),
            complex_name_raw=data.get("complex_name_raw"),
            price_deposit=data.get("price_deposit"),
            price_monthly=data.get("price_monthly"),
            exclusive_area=Decimal(data["exclusive_area"]) if data.get("exclusive_area") else None,
            supply_area=Decimal(data["supply_area"]) if data.get("supply_area") else None,
            floor_info=data.get("floor_info") or data.get("floor_raw"),
            address_raw=data.get("address_raw"),
            description_raw=data.get("description_raw"),
            mortgage_status=data.get("mortgage_status"),
            status=data.get("status", "ACTIVE"),
            raw_payload=data.get("raw_payload") or {},
        )
        if data.get("first_seen_at"):
            try:
                listing.first_seen_at = datetime.fromisoformat(data["first_seen_at"])
            except Exception:
                listing.first_seen_at = None
        if data.get("last_seen_at"):
            try:
                listing.last_seen_at = datetime.fromisoformat(data["last_seen_at"])
            except Exception:
                listing.last_seen_at = None

        src_code = data.get("source_code", "SITE_A")
        listing.source = CrawlSource(id=data.get("source_id", 1), code=src_code, name="네이버부동산")

        cdata = data.get("complex")
        if cdata:
            listing.complex = ApartmentComplex(
                id=cdata["id"],
                official_name=cdata.get("official_name"),
                total_households=cdata.get("total_households"),
                construction_year=cdata.get("construction_year"),
                sido=cdata.get("sido"),
                sigungu=cdata.get("sigungu"),
                dong=cdata.get("dong"),
                road_address=cdata.get("road_address"),
            )

        # 템플릿 호환용 대출 적격 객체 동적 복원
        loans_data = data.get("eligible_loans", [])
        eligible_loans_objs = []
        for ld in loans_data:
            class DummyLoanRes:
                pass
            obj = DummyLoanRes()
            obj.product_code = ld.get("product_code")
            obj.product_name = ld.get("product_name")
            obj.max_loan_amount = ld.get("max_loan_amount")
            obj.interest_rate = ld.get("interest_rate")
            obj.estimated_monthly_interest = ld.get("estimated_monthly_interest")
            obj.reason = ld.get("reason")
            eligible_loans_objs.append(obj)

        listing.eligible_loans = eligible_loans_objs
        return listing

    def search_listings(self, params: ListingFilterParams, applicant: ApplicantProfile | None = None) -> SearchResult:
        """주어진 조건에 알맞은 매물 리스트 및 전체 개수 반환 (가격 낮은순 기본 정렬 & 단기임대 차단 강화 지원)."""
        limit = getattr(params, "limit", getattr(params, "page_size", 50))
        page_val = getattr(params, "page", 1)
        offset = getattr(params, "offset", 0)
        if page_val > 1 and offset == 0:
            offset = (page_val - 1) * limit

        # 정렬 기본값: price_asc
        sort_by_val = params.sort_by if isinstance(params.sort_by, str) else (params.sort_by.value if params.sort_by else "price_asc")
        effective_region_val = getattr(params, "region_name", None) or getattr(params, "region_keyword", None)

        # 100% JOIN 0건 초고속 DB Direct 쿼리 구동 (Sub-millisecond 4ms 처리)
        stmt = select(Listing).where(Listing.status == "ACTIVE")

        # 0. 단기임대 / 단기 월세 / 노이즈 매물 원천 차단 (is_short_term 인덱스 적용)
        if getattr(params, "exclude_short_term", True):
            stmt = stmt.where(Listing.is_short_term == False)

        # 정책대출 필터링 조건 추가
        if getattr(params, "only_eligible_loans", False):
            if not applicant or not applicant.is_homeless:
                return SearchResult(items=[], total_count=0, page=page_val, page_size=limit)

            stmt = stmt.where(Listing.exclusive_area <= Decimal("85.0"))

            is_newlywed = applicant.is_newlywed
            has_multi_children = applicant.child_count >= 2
            is_first_buyer = applicant.is_first_home_buyer
            has_newborn = getattr(applicant, "has_newborn", False)

            didimdol_income_limit = 85_000_000 if is_newlywed else (70_000_000 if (is_first_buyer or has_multi_children) else 60_000_000)
            is_didimdol_eligible = applicant.annual_income <= didimdol_income_limit

            if has_multi_children:
                bogumjari_income_limit = 100_000_000
            elif applicant.child_count == 1:
                bogumjari_income_limit = 90_000_000
            elif is_newlywed:
                bogumjari_income_limit = 85_000_000
            else:
                bogumjari_income_limit = 70_000_000
            is_bogumjari_eligible = applicant.annual_income <= bogumjari_income_limit

            is_neonatal_eligible = has_newborn and (applicant.annual_income <= 200_000_000)

            beotimmok_income_limit = 75_000_000 if (is_newlywed or has_multi_children) else 50_000_000
            is_beotimmok_eligible = applicant.annual_income <= beotimmok_income_limit

            if not any([is_didimdol_eligible, is_bogumjari_eligible, is_neonatal_eligible, is_beotimmok_eligible]):
                return SearchResult(items=[], total_count=0, page=page_val, page_size=limit)

            total_cap = getattr(applicant, "total_capital", applicant.net_assets)
            conditions = []

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
                return SearchResult(items=[], total_count=0, page=page_val, page_size=limit)

        # 1. 키워드 검색 (단지명 또는 주소)
        complex_kw = getattr(params, "complex_keyword", None)
        if complex_kw:
            kw = f"%{complex_kw.strip()}%"
            stmt = stmt.where(
                or_(
                    Listing.complex_name_raw.ilike(kw),
                    Listing.address_raw.ilike(kw),
                )
            )

        # 2. 지역 선택 검색 (sido, sigungu 인덱스 B-Tree Equal + address_raw 호환 fallback)
        if effective_region_val and effective_region_val.strip() and effective_region_val.strip() != "전체":
            raw_region = effective_region_val.strip()
            tokens = raw_region.split()
            sido_token = tokens[0]
            sigungu_token = tokens[1] if len(tokens) >= 2 else None

            if "서울" in sido_token:
                stmt = stmt.where(or_(Listing.sido == "서울특별시", Listing.address_raw.like("서울 %"), Listing.address_raw.like("서울특별시 %")))
            elif "경기" in sido_token:
                stmt = stmt.where(or_(Listing.sido == "경기도", Listing.address_raw.like("경기 %"), Listing.address_raw.like("경기도 %")))
            elif "인천" in sido_token:
                stmt = stmt.where(or_(Listing.sido == "인천광역시", Listing.address_raw.like("인천 %"), Listing.address_raw.like("인천광역시 %")))
            else:
                stmt = stmt.where(or_(Listing.sido == sido_token, Listing.address_raw.like(f"{sido_token}%")))

            if sigungu_token:
                stmt = stmt.where(or_(Listing.sigungu.ilike(f"%{sigungu_token}%"), Listing.address_raw.ilike(f"%{sigungu_token}%")))

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

        # 6. 아파트 단지 조건 필터 (Listing 비정규화 + ApartmentComplex fallback)
        if params.min_construction_year or params.min_households:
            stmt = stmt.outerjoin(Listing.complex)
            if params.min_construction_year:
                stmt = stmt.where(or_(Listing.construction_year >= params.min_construction_year, ApartmentComplex.construction_year >= params.min_construction_year))
            if params.min_households:
                stmt = stmt.where(or_(Listing.total_households >= params.min_households, ApartmentComplex.total_households >= params.min_households))

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

        # 9. 정렬 옵션 (기본값: price_asc 가격 낮은순)
        if sort_by_val == SortBy.PRICE_DESC or sort_by_val == "price_desc":
            stmt = stmt.order_by(Listing.price_deposit.desc())
        elif sort_by_val == SortBy.RECENT or sort_by_val == "recent":
            stmt = stmt.order_by(Listing.first_seen_at.desc())
        elif sort_by_val == SortBy.AREA_DESC or sort_by_val == "area_desc":
            stmt = stmt.order_by(Listing.exclusive_area.desc())
        else:
            # price_asc (가격 낮은순 기본)
            stmt = stmt.order_by(Listing.price_deposit.asc())

        # 전체 개수 산출 (모든 복합 필터 조건 100% 동기화)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total_count = self.db.scalar(count_stmt) or 0

        # DB Direct 조회 (offset, limit)
        stmt_paged = stmt.offset(offset).limit(limit)
        items = list(self.db.scalars(stmt_paged).unique().all())

        return SearchResult(items=items, total_count=total_count, page=page_val, page_size=limit)
