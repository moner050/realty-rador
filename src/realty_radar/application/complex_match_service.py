from datetime import datetime
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.constants import MatchMethod
from realty_radar.domain.complex.entities import ComplexMatchResult
from realty_radar.domain.complex.matching import ComplexMatchEngine, normalize_complex_name
from realty_radar.infrastructure.database.models import ApartmentComplex, ComplexAlias, Listing


class ComplexMatchService:
    """매물의 원본 단지명을 아파트 단지 DB와 연결하는 매칭 서비스."""

    def __init__(self, db: Session):
        self.db = db
        self.engine = ComplexMatchEngine()

    def _safe_confidence(self, score: Decimal) -> Decimal:
        """MySQL DECIMAL(5,2) 컬럼 상한선(99.99) 안전 보장."""
        if score > Decimal("99.99"):
            return Decimal("99.99")
        if score < Decimal("0.00"):
            return Decimal("0.00")
        return score

    def match_listing_complex(self, listing_id: int) -> ComplexMatchResult:
        """단일 매물의 complex_id 매칭 수행 및 저장."""
        try:
            stmt = select(Listing).where(Listing.id == listing_id)
            listing = self.db.scalar(stmt)

            if not listing or not listing.complex_name_raw:
                return ComplexMatchResult(
                    complex_id=None,
                    match_score=Decimal("0.00"),
                    match_method=MatchMethod.FUZZY,
                )

            norm_name = normalize_complex_name(listing.complex_name_raw)

            # 1. complex_alias 등록 테이블에서 일치 확인
            alias_stmt = select(ComplexAlias).where(ComplexAlias.normalized_alias == norm_name)
            alias = self.db.scalar(alias_stmt)

            if alias:
                listing.complex_id = alias.complex_id
                self.db.commit()
                return ComplexMatchResult(
                    complex_id=alias.complex_id,
                    match_score=self._safe_confidence(Decimal("99.99")),
                    match_method=MatchMethod(alias.match_method),
                    alias_used=alias.alias_name,
                )

            # 2. apartment_complex 전체 후보 검색
            complexes_stmt = select(ApartmentComplex)
            complexes = self.db.scalars(complexes_stmt).all()

            candidates = [
                {
                    "id": c.id,
                    "official_name": c.official_name,
                    "normalized_name": c.normalized_name,
                    "road_address": c.road_address,
                }
                for c in complexes
            ]

            result = self.engine.evaluate_candidates(
                target_name=listing.complex_name_raw,
                target_address=listing.address_raw,
                candidates=candidates,
            )

            if result.complex_id:
                listing.complex_id = result.complex_id

                # complex_alias 자동 생성 또는 업서트
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
            else:
                # 매칭에 실패한 경우 신규 단지 생성
                new_complex = ApartmentComplex(
                    official_name=listing.complex_name_raw,
                    normalized_name=norm_name,
                    road_address=listing.address_raw,
                )
                self.db.add(new_complex)
                self.db.flush()

                listing.complex_id = new_complex.id
                result.complex_id = new_complex.id
                result.match_score = Decimal("99.99")
                result.match_method = MatchMethod.NAME_EXACT

            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise
