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
    """사이트 간 동일 매물 추정 및 중복 판정 서비스 (인메모리 버킷팅 기반 초고속 배치 처리)."""

    def __init__(self, db: Session):
        self.db = db

    def calculate_similarity(self, listing_a: Listing, listing_b: Listing) -> Decimal:
        """두 매물 간 동일 매물 가중치 점수 (0~100) 산출."""
        if listing_a.id == listing_b.id:
            return Decimal("100.00")

        if listing_a.source_id == listing_b.source_id:
            if listing_a.external_listing_id == listing_b.external_listing_id:
                return Decimal("100.00")
            return Decimal("0.00")

        score = 0.0

        if listing_a.complex_id and listing_b.complex_id and listing_a.complex_id == listing_b.complex_id:
            score += 40.0

        if listing_a.transaction_type == listing_b.transaction_type:
            score += 10.0

        if listing_a.exclusive_area and listing_b.exclusive_area:
            diff = abs(listing_a.exclusive_area - listing_b.exclusive_area)
            if diff <= Decimal("0.5"):
                score += 15.0

        if listing_a.price_deposit and listing_b.price_deposit and listing_a.price_deposit == listing_b.price_deposit:
            score += 15.0
        elif listing_a.price_monthly and listing_b.price_monthly and listing_a.price_monthly == listing_b.price_monthly:
            score += 15.0

        if listing_a.floor_info and listing_b.floor_info and listing_a.floor_info == listing_b.floor_info:
            score += 10.0

        if listing_a.description_raw and listing_b.description_raw:
            desc_sim = fuzz.ratio(listing_a.description_raw, listing_b.description_raw)
            score += (desc_sim / 100.0) * 10.0

        return Decimal(str(round(score, 2)))

    def find_duplicates_in_batch(self, listings: list[Listing]) -> dict[int, list[DedupMatchResult]]:
        """배치 수집된 매물 목록에 대해 SQL 쿼리 0회 인메모리 버킷팅 기반 중복 추정."""
        if not listings:
            return {}

        # (complex_id, transaction_type) 키 기반 인메모리 버킷 분할
        buckets: dict[tuple[int | None, str | None], list[Listing]] = {}
        for l in listings:
            if not l.complex_id:
                continue
            key = (l.complex_id, l.transaction_type)
            if key not in buckets:
                buckets[key] = []
            buckets[key].append(l)

        results_map: dict[int, list[DedupMatchResult]] = {}

        for key, bucket_items in buckets.items():
            if len(bucket_items) < 2:
                continue

            for i in range(len(bucket_items)):
                target = bucket_items[i]
                target_results = []
                for j in range(i + 1, len(bucket_items)):
                    cand = bucket_items[j]
                    score = self.calculate_similarity(target, cand)
                    if score >= Decimal("70.00"):
                        res = DedupMatchResult(
                            target_listing_id=target.id,
                            matched_listing_id=cand.id,
                            similarity_score=score,
                            is_duplicate=score >= Decimal("85.00"),
                        )
                        target_results.append(res)
                if target_results:
                    target_results.sort(key=lambda r: r.similarity_score, reverse=True)
                    results_map[target.id] = target_results

        return results_map

    def find_duplicates_for_listing(self, target_listing_id: int) -> list[DedupMatchResult]:
        """특정 매물 단건과 동일할 가능성이 높은 타 사이트 매물 목록 검색."""
        stmt = select(Listing).where(Listing.id == target_listing_id)
        target = self.db.scalar(stmt)

        if not target or not target.complex_id:
            return []

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
