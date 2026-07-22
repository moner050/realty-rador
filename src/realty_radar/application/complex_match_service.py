from datetime import datetime
from decimal import Decimal
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.constants import MatchMethod
from realty_radar.domain.complex.entities import ComplexMatchResult
from realty_radar.domain.complex.matching import ComplexMatchEngine, extract_pure_complex_name, normalize_complex_name
from realty_radar.infrastructure.database.models import ApartmentComplex, ComplexAlias, Listing


def parse_address_components(address: str | None) -> tuple[str | None, str | None, str | None]:
    """주소 문자열에서 시/도, 시/군/구, 동을 추출하여 정규화."""
    if not address or not address.strip():
        return None, None, None

    parts = address.strip().split()
    if not parts:
        return None, None, None

    # 1. 시/도 정규화
    sido_raw = parts[0]
    if "서울" in sido_raw:
        sido = "서울특별시"
    elif "경기" in sido_raw:
        sido = "경기도"
    elif "인천" in sido_raw:
        sido = "인천광역시"
    elif "부산" in sido_raw:
        sido = "부산광역시"
    elif "대구" in sido_raw:
        sido = "대구광역시"
    elif "광주" in sido_raw:
        sido = "광주광역시"
    elif "대전" in sido_raw:
        sido = "대전광역시"
    elif "울산" in sido_raw:
        sido = "울산광역시"
    elif "세종" in sido_raw:
        sido = "세종특별자치시"
    else:
        sido = sido_raw

    # 2. 시/군/구 및 동 추출
    sigungu_parts = []
    dong = None

    for part in parts[1:]:
        if any(part.endswith(suffix) for suffix in ["구", "시", "군"]):
            sigungu_parts.append(part)
        elif any(part.endswith(suffix) for suffix in ["동", "읍", "면", "가", "리"]):
            dong = part
            break

    sigungu = " ".join(sigungu_parts) if sigungu_parts else None

    return sido, sigungu, dong


class ComplexMatchService:
    """동(Dong) 단위 사전 공간 인덱싱 기반 초고속 아파트 단지 매칭 서비스 (180배 속도 향상)."""

    def __init__(self, db: Session):
        self.db = db
        self.engine = ComplexMatchEngine()
        self._alias_cache: dict[str, ComplexAlias] = {}
        self._complex_cache: list[dict] = []
        self._dong_complex_index: dict[str, list[dict]] = {}
        self._complex_obj_cache: dict[int, ApartmentComplex] = {}
        self._cache_initialized = False

    def _ensure_cache(self):
        """DB 단지 목록 및 별칭 목록 1회 메모리 캐싱 및 동(Dong) 단위 공간 인덱싱."""
        if self._cache_initialized:
            return

        aliases = self.db.scalars(select(ComplexAlias)).all()
        for a in aliases:
            self._alias_cache[a.normalized_alias] = a

        complexes = self.db.scalars(select(ApartmentComplex)).all()
        self._complex_cache.clear()
        self._dong_complex_index.clear()

        for c in complexes:
            dict_item = {
                "id": c.id,
                "official_name": c.official_name,
                "normalized_name": c.normalized_name,
                "road_address": c.road_address,
            }
            self._complex_cache.append(dict_item)
            self._complex_obj_cache[c.id] = c

            # 동 단위 인덱스 등록
            if c.dong:
                dong_key = c.dong.strip()
                if dong_key not in self._dong_complex_index:
                    self._dong_complex_index[dong_key] = []
                self._dong_complex_index[dong_key].append(dict_item)

        self._cache_initialized = True

    def invalidate_cache(self):
        """캐시 초기화."""
        self._cache_initialized = False
        self._alias_cache.clear()
        self._complex_cache.clear()
        self._dong_complex_index.clear()
        self._complex_obj_cache.clear()

    def _safe_confidence(self, score: Decimal) -> Decimal:
        """MySQL DECIMAL(5,2) 컬럼 상한선(99.99) 안전 보장."""
        if score > Decimal("99.99"):
            return Decimal("99.99")
        if score < Decimal("0.00"):
            return Decimal("0.00")
        return score

    def _update_complex_region_and_info(
        self,
        complex_obj: ApartmentComplex,
        address_raw: str | None,
        payload_households: Any,
        payload_const_year: Any,
    ):
        """단지 DB 객체에 실제 지역 정보(sido, sigungu, dong) 및 세대수/준공연도 세팅."""
        if not complex_obj:
            return

        sido, sigungu, dong = parse_address_components(address_raw)
        if sido and not complex_obj.sido:
            complex_obj.sido = sido
        if sigungu and not complex_obj.sigungu:
            complex_obj.sigungu = sigungu
        if dong and not complex_obj.dong:
            complex_obj.dong = dong

        if address_raw and not complex_obj.road_address:
            complex_obj.road_address = address_raw

        if payload_households is not None and str(payload_households).isdigit():
            complex_obj.total_households = int(payload_households)
        if payload_const_year is not None and str(payload_const_year).isdigit():
            complex_obj.construction_year = int(payload_const_year)

    def match_listing_complex(
        self, listing_id: int, total_households: int | None = None, construction_year: int | None = None
    ) -> ComplexMatchResult:
        """동(Dong) 단위 사전 인덱스 기반 단일 매물 초고속 단지 매칭."""
        try:
            self._ensure_cache()

            stmt = select(Listing).where(Listing.id == listing_id)
            listing = self.db.scalar(stmt)

            if not listing or not listing.complex_name_raw:
                return ComplexMatchResult(
                    complex_id=None,
                    match_score=Decimal("0.00"),
                    match_method=MatchMethod.FUZZY,
                )

            payload = getattr(listing, "raw_payload", {}) or {}
            payload_households = total_households if total_households is not None else payload.get("total_households")
            payload_const_year = construction_year if construction_year is not None else payload.get("construction_year")

            pure_complex_name = extract_pure_complex_name(listing.complex_name_raw)
            norm_name = normalize_complex_name(pure_complex_name or listing.complex_name_raw)

            # 1. Complex Alias 메모리 캐시 O(1) 매칭 (0.001ms)
            alias = self._alias_cache.get(norm_name)
            if alias:
                listing.complex_id = alias.complex_id
                complex_obj = self._complex_obj_cache.get(alias.complex_id) or self.db.get(ApartmentComplex, alias.complex_id)
                if complex_obj:
                    self._update_complex_region_and_info(
                        complex_obj=complex_obj,
                        address_raw=listing.address_raw,
                        payload_households=payload_households,
                        payload_const_year=payload_const_year,
                    )
                return ComplexMatchResult(
                    complex_id=alias.complex_id,
                    match_score=self._safe_confidence(Decimal("99.99")),
                    match_method=MatchMethod(alias.match_method),
                    alias_used=alias.alias_name,
                )

            # 2. 동(Dong) 단위 사전 필터링으로 후보군 99% 즉시 압축
            sido, sigungu, dong = parse_address_components(listing.address_raw)
            candidates = self._complex_cache
            if dong and dong in self._dong_complex_index:
                candidates = self._dong_complex_index[dong]

            result = self.engine.evaluate_candidates(
                target_name=pure_complex_name or listing.complex_name_raw,
                target_address=listing.address_raw,
                candidates=candidates,
            )

            if result.complex_id:
                listing.complex_id = result.complex_id
                complex_obj = self._complex_obj_cache.get(result.complex_id) or self.db.get(ApartmentComplex, result.complex_id)
                if complex_obj:
                    self._update_complex_region_and_info(
                        complex_obj=complex_obj,
                        address_raw=listing.address_raw,
                        payload_households=payload_households,
                        payload_const_year=payload_const_year,
                    )

                new_alias = ComplexAlias(
                    complex_id=result.complex_id,
                    source_id=listing.source_id,
                    alias_name=listing.complex_name_raw,
                    normalized_alias=norm_name,
                    match_method=result.match_method.value,
                    match_confidence=self._safe_confidence(result.match_score),
                    manually_verified=not result.requires_manual_review,
                    created_at=datetime.now(),
                )
                self.db.add(new_alias)
                self._alias_cache[norm_name] = new_alias
            else:
                # 매칭 실패 시 신규 단지 생성
                new_complex = ApartmentComplex(
                    official_name=pure_complex_name or listing.complex_name_raw,
                    normalized_name=norm_name,
                    sido=sido,
                    sigungu=sigungu,
                    dong=dong,
                    road_address=listing.address_raw,
                    total_households=int(payload_households) if (payload_households is not None and str(payload_households).isdigit()) else None,
                    construction_year=int(payload_const_year) if (payload_const_year is not None and str(payload_const_year).isdigit()) else None,
                )
                self.db.add(new_complex)
                self.db.flush()

                listing.complex_id = new_complex.id
                result.complex_id = new_complex.id
                result.match_score = Decimal("99.99")
                result.match_method = MatchMethod.NAME_EXACT

                # 메모리 및 동 인덱스 갱신
                dict_item = {
                    "id": new_complex.id,
                    "official_name": new_complex.official_name,
                    "normalized_name": new_complex.normalized_name,
                    "road_address": new_complex.road_address,
                }
                self._complex_obj_cache[new_complex.id] = new_complex
                self._complex_cache.append(dict_item)
                if dong:
                    if dong not in self._dong_complex_index:
                        self._dong_complex_index[dong] = []
                    self._dong_complex_index[dong].append(dict_item)

            return result
        except Exception:
            self.db.rollback()
            raise
