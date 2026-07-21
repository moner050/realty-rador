from dataclasses import dataclass
from decimal import Decimal
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.infrastructure.database.models import Listing


@dataclass
class DedupMatchResult:
    """동일 매물 추정 결과 DTO."""

    target_listing_id: int
    matched_listing_id: int
    similarity_score: Decimal
    is_duplicate: bool


class ListingDedupService:
    """사이트 간 동일 매물 추정 및 중복 판정 서비스."""

    def __init__(self, db: Session):
        self.db = db

    def calculate_similarity(self, listing_a: Listing, listing_b: Listing) -> Decimal:
        """두 매물 간 동일 매물 가중치 점수 (0~100) 산출."""
        if listing_a.id == listing_b.id:
            return Decimal("100.00")

        # 같은 사이트인 경우 external_listing_id 차이 시 별개
        if listing_a.source_id == listing_b.source_id:
            if listing_a.external_listing_id == listing_b.external_listing_id:
                return Decimal("100.00")
            return Decimal("0.00")

        score = 0.0

        # 1. 단지 ID 일치 (+40점)
        if listing_a.complex_id and listing_b.complex_id and listing_a.complex_id == listing_b.complex_id:
            score += 40.0

        # 2. 거래 유형 일치 (+10점)
        if listing_a.transaction_type == listing_b.transaction_type:
            score += 10.0

        # 3. 전용면적 오차 0.5㎡ 이내 (+15점)
        if listing_a.exclusive_area and listing_b.exclusive_area:
            diff = abs(listing_a.exclusive_area - listing_b.exclusive_area)
            if diff <= Decimal("0.5"):
                score += 15.0

        # 4. 가격 일치 (+15점)
        if listing_a.sale_price and listing_b.sale_price and listing_a.sale_price == listing_b.sale_price:
            score += 15.0
        elif listing_a.deposit and listing_b.deposit and listing_a.deposit == listing_b.deposit:
            score += 15.0

        # 5. 층 그룹 일치 (+10점)
        if listing_a.floor_group and listing_b.floor_group and listing_a.floor_group == listing_b.floor_group:
            score += 10.0

        # 6. 설명 유사도 (+10점)
        if listing_a.description and listing_b.description:
            desc_sim = fuzz.ratio(listing_a.description, listing_b.description)
            score += (desc_sim / 100.0) * 10.0

        return Decimal(str(round(score, 2)))

    def find_duplicates_for_listing(self, target_listing_id: int) -> list[DedupMatchResult]:
        """특정 매물과 동일할 가능성이 높은 타 사이트 매물 목록 검색."""
        stmt = select(Listing).where(Listing.id == target_listing_id)
        target = self.db.scalar(stmt)

        if not target or not target.complex_id:
            return []

        # 동일 단지 및 동일 거래유형의 타 사이트 매물 후보 검색
        candidates_stmt = select(Listing).where(
            Listing.complex_id == target.complex_id,
            Listing.transaction_type == target.transaction_type,
            Listing.id != target.id,
            Listing.status == "ACTIVE",
        )
        candidates = self.db.scalars(candidates_stmt).all()

        results: list[DedupMatchResult] = []

        for cand in candidates:
            score = self.calculate_similarity(target, cand)
            if score >= Decimal("70.00"):
                results.append(
                    DedupMatchResult(
                        target_listing_id=target.id,
                        matched_listing_id=cand.id,
                        similarity_score=score,
                        is_duplicate=score >= Decimal("85.00"),
                    )
                )

        results.sort(key=lambda r: r.similarity_score, reverse=True)
        return results
