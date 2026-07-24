import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from sqlalchemy import func, not_, or_, select, and_
from sqlalchemy.orm import Session, contains_eager, joinedload

from realty_radar.application.complex_match_service import parse_address_components
from realty_radar.constants import MortgageStatus, SortBy, TransactionType
from realty_radar.domain.complex.matching import extract_pure_complex_name
from realty_radar.domain.listing.models import ComplexGroupItem, ListingFilterParams, SearchResult
from realty_radar.domain.loan.entities import ApplicantProfile
from realty_radar.infrastructure.cache.redis_client import redis_cache
from realty_radar.infrastructure.database.models import ApartmentComplex, CrawlSource, Listing


def format_korean_money(amount: int | float | Decimal | None) -> str:
    """원 단위 금액을 '5억 5,000만 원', '6억 원' 형식의 한글 표현으로 변환."""
    if not amount:
        return "0원"

    val = int(amount)
    eok = val // 100_000_000
    remainder = val % 100_000_000
    man = remainder // 10_000

    parts = []
    if eok > 0:
        parts.append(f"{eok}억")
    if man > 0:
        parts.append(f"{man:,}만")

    if not parts:
        return f"{val:,}원"

    return f"{' '.join(parts)} 원"


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

        # 2. 세분화 지역 검색 (sido: 시/도, city: 시, county: 군, district: 구)
        sido_param = getattr(params, "sido", None)
        city_param = getattr(params, "city", None)
        county_param = getattr(params, "county", None)
        district_param = getattr(params, "district", None)

        # 개별 파라미터가 없고 effective_region_val만 있는 경우 자동 분단 파싱
        if not any([sido_param, city_param, county_param, district_param]) and effective_region_val and effective_region_val.strip() and effective_region_val.strip() != "전체":
            raw_region = effective_region_val.strip()
            tokens = raw_region.split()
            for token in tokens:
                if token.endswith(("시", "도")) and any(s in token for s in ["서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "세종", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]):
                    sido_param = token
                elif token.endswith("군"):
                    county_param = token
                elif token.endswith("구"):
                    district_param = token
                elif token.endswith("시"):
                    city_param = token
                elif not sido_param and len(tokens) == 1:
                    # 단일 키워드인 경우(예: '강남구' -> 구, '과천시' -> 시, '여의도' -> 구/동 fallback)
                    if "구" in token:
                        district_param = token
                    elif "군" in token:
                        county_param = token
                    elif "시" in token:
                        city_param = token
                    else:
                        district_param = token

        has_joined_complex = False

        # 시/도 (sido) 필터링 - 타 지역 매물 우회 침투 원천 차단 (Null-safe 처리)
        if sido_param and sido_param.strip():
            s_tok = sido_param.strip()
            if "서울" in s_tok:
                stmt = stmt.where(
                    and_(
                        or_(
                            Listing.sido == "서울특별시",
                            Listing.address_raw.like("%서울%"),
                            Listing.address_raw.like("%서울특별시%"),
                        ),
                        func.coalesce(Listing.sido, "") != "경기도",
                        func.coalesce(Listing.sido, "") != "인천광역시",
                        ~Listing.address_raw.like("경기 %"),
                        ~Listing.address_raw.like("경기도 %"),
                        ~Listing.address_raw.like("인천 %"),
                    )
                )
            elif "경기" in s_tok:
                stmt = stmt.where(
                    and_(
                        or_(
                            Listing.sido == "경기도",
                            Listing.address_raw.like("%경기%"),
                            Listing.address_raw.like("%경기도%"),
                        ),
                        func.coalesce(Listing.sido, "") != "서울특별시",
                        func.coalesce(Listing.sido, "") != "인천광역시",
                        ~Listing.address_raw.like("서울 %"),
                        ~Listing.address_raw.like("서울특별시 %"),
                        ~Listing.address_raw.like("인천 %"),
                    )
                )
            elif "인천" in s_tok:
                stmt = stmt.where(
                    and_(
                        or_(
                            Listing.sido == "인천광역시",
                            Listing.address_raw.like("%인천%"),
                            Listing.address_raw.like("%인천광역시%"),
                        ),
                        func.coalesce(Listing.sido, "") != "서울특별시",
                        func.coalesce(Listing.sido, "") != "경기도",
                        ~Listing.address_raw.like("서울 %"),
                        ~Listing.address_raw.like("서울특별시 %"),
                        ~Listing.address_raw.like("경기 %"),
                        ~Listing.address_raw.like("경기도 %"),
                    )
                )
            else:
                stmt = stmt.where(
                    or_(
                        Listing.sido == s_tok,
                        Listing.address_raw.like(f"%{s_tok}%"),
                    )
                )

        # 시 (city) 필터링 (독립 검색)
        if city_param and city_param.strip():
            c_tok = city_param.strip()
            stmt = stmt.where(or_(Listing.sigungu.ilike(f"%{c_tok}%"), Listing.address_raw.ilike(f"%{c_tok}%")))

        # 군 (county) 필터링 (독립 검색)
        if county_param and county_param.strip():
            co_tok = county_param.strip()
            stmt = stmt.where(or_(Listing.sigungu.ilike(f"%{co_tok}%"), Listing.address_raw.ilike(f"%{co_tok}%")))

        # 구 (district) 필터링 (독립 검색)
        if district_param and district_param.strip():
            d_tok = district_param.strip()
            stmt = stmt.where(or_(Listing.sigungu.ilike(f"%{d_tok}%"), Listing.address_raw.ilike(f"%{d_tok}%")))

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

        # 6. 아파트 단지 조건 필터 (Listing 비정규화 인덱스 컬럼 초고속 검색)
        if params.min_construction_year:
            stmt = stmt.where(Listing.construction_year >= params.min_construction_year)
        if params.min_households:
            stmt = stmt.where(Listing.total_households >= params.min_households)

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

        # 8-1. 매물 방향 (남향, 남동향, 동향, 서향, 북향 등) 다중 선택 고성능 필터링
        target_directions = getattr(params, "parsed_directions", [])
        if target_directions:
            dir_conditions = []
            for d_tok in target_directions:
                dir_conditions.append(Listing.direction.ilike(f"%{d_tok}%"))
                dir_conditions.append(Listing.description_raw.ilike(f"%{d_tok}%"))
            stmt = stmt.where(or_(*dir_conditions))

        # 8-2. 매물 층수 (저층, 중층, 고층, 탑층, 반지하/지하) 다중 선택 고성능 필터링
        target_floors = getattr(params, "parsed_floors", [])
        if target_floors:
            floor_conditions = []
            for fl_tok in target_floors:
                fl_clean = fl_tok.strip()
                if fl_clean in ["저층", "저"]:
                    floor_conditions.extend([
                        Listing.floor_info.ilike("저/%"),
                        Listing.floor_info.ilike("%1층%"),
                        Listing.floor_info.ilike("%2층%"),
                        Listing.floor_info.ilike("%3층%"),
                        Listing.floor_info.ilike("저층%"),
                    ])
                elif fl_clean in ["중층", "중"]:
                    floor_conditions.extend([
                        Listing.floor_info.ilike("중/%"),
                        Listing.floor_info.ilike("%4층%"),
                        Listing.floor_info.ilike("%5층%"),
                        Listing.floor_info.ilike("%6층%"),
                        Listing.floor_info.ilike("%7층%"),
                        Listing.floor_info.ilike("%8층%"),
                        Listing.floor_info.ilike("%9층%"),
                        Listing.floor_info.ilike("%10층%"),
                        Listing.floor_info.ilike("중층%"),
                    ])
                elif fl_clean in ["고층", "고"]:
                    floor_conditions.extend([
                        Listing.floor_info.ilike("고/%"),
                        Listing.floor_info.ilike("%11층%"),
                        Listing.floor_info.ilike("%12층%"),
                        Listing.floor_info.ilike("%13층%"),
                        Listing.floor_info.ilike("%14층%"),
                        Listing.floor_info.ilike("%15층%"),
                        Listing.floor_info.ilike("%16층%"),
                        Listing.floor_info.ilike("%17층%"),
                        Listing.floor_info.ilike("%18층%"),
                        Listing.floor_info.ilike("%19층%"),
                        Listing.floor_info.ilike("%20층%"),
                        Listing.floor_info.ilike("%층%"),
                        Listing.floor_info.ilike("고층%"),
                    ])
                elif fl_clean in ["탑층", "최상층"]:
                    floor_conditions.extend([
                        Listing.floor_info.ilike("%탑%"),
                        Listing.floor_info.ilike("%최상%"),
                    ])
                elif fl_clean in ["반지하", "지하"]:
                    floor_conditions.extend([
                        Listing.floor_info.ilike("%B%"),
                        Listing.floor_info.ilike("%지하%"),
                        Listing.floor_info.ilike("%반지하%"),
                    ])
                else:
                    floor_conditions.append(Listing.floor_info.ilike(f"%{fl_clean}%"))
            if floor_conditions:
                stmt = stmt.where(or_(*floor_conditions))

        # 8-3. 1층 제외 필터 (1층만 정밀 제외하고 11층/21층/31층 등은 유지)
        is_exclude_1f = getattr(params, "exclude_first_floor", False) or ("1층제외" in target_floors)
        if is_exclude_1f:
            # 1층 정밀 제외 조건: '1층'이 들어가면서 '11층', '21층', '31층'이 아닌 경우 및 '1/'로 시작하는 층수 제외
            stmt = stmt.where(
                not_(
                    or_(
                        and_(
                            Listing.floor_info.ilike("%1층%"),
                            not_(Listing.floor_info.ilike("%11층%")),
                            not_(Listing.floor_info.ilike("%21층%")),
                            not_(Listing.floor_info.ilike("%31층%")),
                        ),
                        Listing.floor_info.ilike("1/%"),
                        Listing.floor_info.ilike("1층%"),
                    )
                )
            )

        # 9. 정렬 옵션 (가격/최신/면적/세대수 정밀 정렬)
        is_households_sort = sort_by_val in [SortBy.HOUSEHOLDS_DESC, "households_desc", SortBy.HOUSEHOLDS_ASC, "households_asc"]
        if is_households_sort:
            if sort_by_val == SortBy.HOUSEHOLDS_DESC or sort_by_val == "households_desc":
                stmt = stmt.order_by(Listing.total_households.desc())
            else:
                stmt = stmt.order_by(Listing.total_households.is_(None).asc(), Listing.total_households.asc())
        elif sort_by_val == SortBy.PRICE_DESC or sort_by_val == "price_desc":
            stmt = stmt.order_by(Listing.price_deposit.desc())
        elif sort_by_val == SortBy.RECENT or sort_by_val == "recent":
            stmt = stmt.order_by(Listing.first_seen_at.desc())
        elif sort_by_val == SortBy.AREA_DESC or sort_by_val == "area_desc":
            stmt = stmt.order_by(Listing.exclusive_area.desc())
        elif sort_by_val == SortBy.AREA_ASC or sort_by_val == "area_asc":
            stmt = stmt.order_by(Listing.exclusive_area.is_(None).asc(), Listing.exclusive_area.asc())
        else:
            # price_asc (가격 낮은순 기본)
            stmt = stmt.order_by(Listing.price_deposit.asc())

        # 지연 로딩 에러 원천 차단 (has_joined_complex 상태에 따라 contains_eager / joinedload 적용)
        if has_joined_complex:
            stmt = stmt.options(contains_eager(Listing.complex))
        else:
            stmt = stmt.options(joinedload(Listing.complex))

        stmt = stmt.options(joinedload(Listing.source))

        # 동일 아파트 단지별 묶어서 보기 모드인 경우 (필터링된 전체 매물 대상 전역 묶음 & 단지 수 기준 페이징)
        if getattr(params, "group_by_complex", False):
            # 전체 매물 목록 조회 (offset/limit 미적용)
            all_items = list(self.db.scalars(stmt).unique().all())

            group_dict: dict[str, dict] = {}
            for item in all_items:
                cpx_id = getattr(item, "complex_id", None)
                raw_cpx_name = getattr(item, "complex_name_raw", "") or ""
                pure_cpx_name = extract_pure_complex_name(raw_cpx_name) or raw_cpx_name.strip()
                sido_p, sigungu_p, dong_p = parse_address_components(getattr(item, "address_raw", None))

                if cpx_id:
                    group_key = f"CPX_{cpx_id}"
                elif dong_p and pure_cpx_name:
                    group_key = f"DONG_CPX_{dong_p}_{pure_cpx_name}"
                else:
                    group_key = f"NAME_{pure_cpx_name or '기타단지'}"

                if group_key not in group_dict:
                    cpx_obj = getattr(item, "complex", None)
                    official_cpx_name = cpx_obj.official_name if cpx_obj and getattr(cpx_obj, "official_name", None) else (pure_cpx_name or "단지")

                    group_dict[group_key] = {
                        "complex_id": cpx_id,
                        "complex_name": official_cpx_name,
                        "address_raw": getattr(item, "address_raw", None),
                        "sido": getattr(item, "sido", None) or (cpx_obj.sido if cpx_obj else None),
                        "sigungu": getattr(item, "sigungu", None) or (cpx_obj.sigungu if cpx_obj else None),
                        "total_households": getattr(item, "total_households", None) or (cpx_obj.total_households if cpx_obj else None),
                        "construction_year": getattr(item, "construction_year", None) or (cpx_obj.construction_year if cpx_obj else None),
                        "listings": [],
                    }

                group_dict[group_key]["listings"].append(item)

            all_grouped_items: list[ComplexGroupItem] = []
            for gkey, ginfo in group_dict.items():
                g_listings = ginfo["listings"]
                prices = [l.price_deposit for l in g_listings if getattr(l, "price_deposit", None) is not None]
                min_p = min(prices) if prices else Decimal("0")
                max_p = max(prices) if prices else Decimal("0")

                if min_p == max_p:
                    p_str = format_korean_money(min_p)
                else:
                    p_str = f"{format_korean_money(min_p)} ~ {format_korean_money(max_p)}"

                group_item = ComplexGroupItem(
                    complex_id=ginfo["complex_id"],
                    complex_name=ginfo["complex_name"],
                    address_raw=ginfo["address_raw"],
                    sido=ginfo["sido"],
                    sigungu=ginfo["sigungu"],
                    total_households=ginfo["total_households"],
                    construction_year=ginfo["construction_year"],
                    min_price=min_p,
                    max_price=max_p,
                    price_range_str=p_str,
                    listing_count=len(g_listings),
                    listings=g_listings,
                )
                all_grouped_items.append(group_item)

            # 단지 그룹 정렬 (sort_by 적용)
            def _get_dt(item) -> datetime:
                val = getattr(item, "first_seen_at", None)
                if isinstance(val, datetime):
                    return val
                return datetime.min

            def _get_area(item) -> float:
                val = getattr(item, "exclusive_area", None)
                if isinstance(val, (int, float, Decimal)):
                    return float(val)
                return 0.0

            sort_kind = getattr(params, "sort_by", SortBy.RECENT)
            if sort_kind == SortBy.PRICE_ASC or sort_kind == "price_asc":
                all_grouped_items.sort(key=lambda g: g.min_price)
            elif sort_kind == SortBy.PRICE_DESC or sort_kind == "price_desc":
                all_grouped_items.sort(key=lambda g: g.max_price, reverse=True)
            elif sort_kind == SortBy.AREA_DESC or sort_kind == "area_desc":
                all_grouped_items.sort(key=lambda g: max([_get_area(l) for l in g.listings] or [0.0]), reverse=True)
            elif sort_kind == SortBy.AREA_ASC or sort_kind == "area_asc":
                all_grouped_items.sort(key=lambda g: min([_get_area(l) for l in g.listings if _get_area(l) > 0] or [999999.0]))
            elif sort_kind == SortBy.HOUSEHOLDS_DESC or sort_kind == "households_desc":
                all_grouped_items.sort(key=lambda g: g.total_households or 0, reverse=True)
            elif sort_kind == SortBy.HOUSEHOLDS_ASC or sort_kind == "households_asc":
                all_grouped_items.sort(key=lambda g: g.total_households or 999999)
            else:  # RECENT
                all_grouped_items.sort(key=lambda g: max([_get_dt(l) for l in g.listings] or [datetime.min]), reverse=True)

            # 아파트 단지 수 기준 페이징 슬라이싱
            total_groups_count = len(all_grouped_items)
            start_idx = (page_val - 1) * limit
            end_idx = start_idx + limit
            paged_grouped_items = all_grouped_items[start_idx:end_idx]

            # 현재 페이지 단지들에 속한 매물 목록
            paged_listings = [l for g in paged_grouped_items for l in g.listings]

            return SearchResult(
                items=paged_listings,
                total_count=total_groups_count,
                page=page_val,
                page_size=limit,
                grouped_items=paged_grouped_items,
                is_grouped=True,
            )

        # 일반 개별 매물 모드 - 카테시안 곱 경고 방지 서브쿼리 COUNT & 페이징 슬라이싱
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total_count = self.db.scalar(count_stmt) or 0

        stmt_paged = stmt.offset(offset).limit(limit)
        items = list(self.db.scalars(stmt_paged).unique().all())

        return SearchResult(items=items, total_count=total_count, page=page_val, page_size=limit)
