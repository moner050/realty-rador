import re
from decimal import Decimal
from rapidfuzz import fuzz

from realty_radar.constants import MatchMethod
from realty_radar.domain.complex.entities import ComplexMatchResult


def normalize_complex_name(raw_name: str | None) -> str:
    """단지명 정규화 (괄호, 특수문자, 동 번호/차수/단지 키워드 제거 및 공백 정규화)."""
    if not raw_name:
        return ""

    # 1. 괄호 내용 제거 (예: "여의도 시범 (아파트)" -> "여의도 시범")
    clean = re.sub(r"\([^)]*\)", "", raw_name)

    # 2. 동/차수/단지 표현 정규화 (예: "1동", "2차", "단지" 제거)
    clean = re.sub(r"\d+동|\d+차|\d+단지|단지", "", clean)

    # 3. 특수문자 제거
    clean = re.sub(r"[^\w\s가-힣a-zA-Z0-9]", "", clean)

    # 4. 공백 정규화
    clean = " ".join(clean.split()).strip()

    return clean


class ComplexMatchEngine:
    """단지 매칭 우선순위 가중치 점수 계산 엔진."""

    @staticmethod
    def calculate_match_score(
        target_name: str,
        target_address: str | None,
        candidate_official_name: str,
        candidate_normalized_name: str,
        candidate_address: str | None = None,
    ) -> tuple[Decimal, MatchMethod]:
        """두 단지명 및 주소 정보의 매칭 점수 (0~99.99)와 매칭 방식 산출."""
        
        # 0. 지역 불일치 검증 (시/도 또는 시/군/구가 다르면 매칭 원천 차단)
        if target_address and candidate_address:
            def get_sido(addr: str) -> str:
                addr_clean = addr.strip()
                if "서울" in addr_clean:
                    return "서울"
                if "경기" in addr_clean:
                    return "경기"
                if "인천" in addr_clean:
                    return "인천"
                parts = addr_clean.split()
                return parts[0] if parts else ""

            def get_sigungu(addr: str) -> str:
                parts = addr.strip().split()
                return parts[1] if len(parts) > 1 else ""

            target_sido = get_sido(target_address)
            candidate_sido = get_sido(candidate_address)
            if target_sido and candidate_sido and target_sido != candidate_sido:
                return Decimal("0.00"), MatchMethod.FUZZY

            target_sigungu = get_sigungu(target_address)
            candidate_sigungu = get_sigungu(candidate_address)
            if target_sigungu and candidate_sigungu and target_sigungu != candidate_sigungu:
                return Decimal("0.00"), MatchMethod.FUZZY

        norm_target = normalize_complex_name(target_name)

        # 1. 주소 및 단지명 완전 일치 (+99.99점)
        if target_address and candidate_address and target_address.strip() == candidate_address.strip():
            return Decimal("99.99"), MatchMethod.ADDRESS_EXACT

        # 2. 정규화 단지명 완전 일치 (+95.00점)
        if norm_target and norm_target == candidate_normalized_name:
            return Decimal("95.00"), MatchMethod.NAME_EXACT

        # 3. RapidFuzz 유사도 계산 (+0~80점)
        similarity = fuzz.ratio(norm_target, candidate_normalized_name)
        score = Decimal(str(min(99.99, round(similarity * 0.9, 2))))

        return score, MatchMethod.FUZZY

    def evaluate_candidates(
        self,
        target_name: str,
        target_address: str | None,
        candidates: list[dict],
    ) -> ComplexMatchResult:
        """후보 단지 목록에서 최고의 매칭 단지 선별."""
        best_score = Decimal("0.00")
        best_complex_id = None
        best_method = MatchMethod.FUZZY

        for cand in candidates:
            score, method = self.calculate_match_score(
                target_name=target_name,
                target_address=target_address,
                candidate_official_name=cand["official_name"],
                candidate_normalized_name=cand["normalized_name"],
                candidate_address=cand.get("road_address"),
            )

            if score > best_score:
                best_score = score
                best_complex_id = cand["id"]
                best_method = method

        requires_review = Decimal("75.00") <= best_score < Decimal("90.00")
        matched_id = best_complex_id if best_score >= Decimal("75.00") else None

        return ComplexMatchResult(
            complex_id=matched_id,
            match_score=best_score,
            match_method=best_method,
            requires_manual_review=requires_review,
        )
