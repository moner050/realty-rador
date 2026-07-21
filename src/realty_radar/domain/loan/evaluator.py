from decimal import Decimal

from realty_radar.constants import TransactionType
from realty_radar.domain.loan.entities import (
    ApplicantProfile,
    LoanEligibilityStatus,
    LoanEvaluationResult,
)


class LoanRuleEvaluator:
    """디딤돌, 버팀목, 신생아 특례대출 조건 평가 엔진."""

    def evaluate_didimdol(
        self,
        transaction_type: TransactionType,
        price: int | None,
        exclusive_area: Decimal | None,
        applicant: ApplicantProfile | None = None,
    ) -> LoanEvaluationResult:
        """내집마련 디딤돌 대출 조건 평가."""
        if transaction_type != TransactionType.SALE or not price or not exclusive_area:
            return LoanEvaluationResult(
                product_code="DIDIMDOL",
                product_name="내집마련 디딤돌대출",
                status=LoanEligibilityStatus.UNKNOWN,
                reason="매매가 또는 전용면적 정보가 부족합니다.",
            )

        # 1. 면적 조건 (85㎡ 이하)
        if exclusive_area > Decimal("85.0"):
            return LoanEvaluationResult(
                product_code="DIDIMDOL",
                product_name="내집마련 디딤돌대출",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason="전용면적 85㎡를 초과합니다.",
            )

        # 2. 매매가 기준 (신혼/다자녀 6억, 일반 5억)
        max_price_limit = 600_000_000 if (applicant and (applicant.is_newlywed or applicant.child_count >= 2)) else 500_000_000
        if price > max_price_limit:
            return LoanEvaluationResult(
                product_code="DIDIMDOL",
                product_name="내집마련 디딤돌대출",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason=f"매매가가 대출 한도 기준({max_price_limit // 100_000_000}억 원)을 초과합니다.",
            )

        # 사용자 조건 미입력 시 매물 조건만 충족
        if not applicant:
            return LoanEvaluationResult(
                product_code="DIDIMDOL",
                product_name="내집마련 디딤돌대출",
                status=LoanEligibilityStatus.PROPERTY_ELIGIBLE,
                max_loan_amount=250_000_000,
                reason="매물 조건 충족 (개인 자격 확인 필요)",
            )

        # 3. 개인 조건 평가
        if not applicant.is_homeless:
            return LoanEvaluationResult(
                product_code="DIDIMDOL",
                product_name="내집마련 디딤돌대출",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason="무주택 세대주 조건 미충족",
            )

        income_limit = 60_000_000
        if applicant.is_newlywed:
            income_limit = 85_000_000
        elif applicant.is_first_home_buyer or applicant.child_count >= 2:
            income_limit = 70_000_000

        if applicant.annual_income > income_limit:
            return LoanEvaluationResult(
                product_code="DIDIMDOL",
                product_name="내집마련 디딤돌대출",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason=f"부부합산 소득이 기준({income_limit // 10_000}만 원)을 초과합니다.",
            )

        return LoanEvaluationResult(
            product_code="DIDIMDOL",
            product_name="내집마련 디딤돌대출",
            status=LoanEligibilityStatus.ELIGIBLE,
            max_loan_amount=300_000_000 if applicant.is_newlywed else 250_000_000,
            reason="정책대출 신청 적격 조건 충족",
        )

    def evaluate_beotimmok(
        self,
        transaction_type: TransactionType,
        deposit: int | None,
        exclusive_area: Decimal | None,
        applicant: ApplicantProfile | None = None,
    ) -> LoanEvaluationResult:
        """버팀목 전세자금 대출 조건 평가."""
        if transaction_type not in [TransactionType.JEONSE, TransactionType.MONTHLY_RENT] or not deposit or not exclusive_area:
            return LoanEvaluationResult(
                product_code="BEOTIMMOK",
                product_name="버팀목 전세자금대출",
                status=LoanEligibilityStatus.UNKNOWN,
                reason="보증금 또는 면적 정보가 부족합니다.",
            )

        if exclusive_area > Decimal("85.0"):
            return LoanEvaluationResult(
                product_code="BEOTIMMOK",
                product_name="버팀목 전세자금대출",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason="전용면적 85㎡를 초과합니다.",
            )

        max_deposit_limit = 400_000_000 if (applicant and (applicant.is_newlywed or applicant.child_count >= 2)) else 300_000_000
        if deposit > max_deposit_limit:
            return LoanEvaluationResult(
                product_code="BEOTIMMOK",
                product_name="버팀목 전세자금대출",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason=f"보증금이 기준({max_deposit_limit // 100_000_000}억 원)을 초과합니다.",
            )

        if not applicant:
            return LoanEvaluationResult(
                product_code="BEOTIMMOK",
                product_name="버팀목 전세자금대출",
                status=LoanEligibilityStatus.PROPERTY_ELIGIBLE,
                max_loan_amount=120_000_000,
                reason="매물 조건 충족 (개인 자격 확인 필요)",
            )

        income_limit = 75_000_000 if applicant.is_newlywed else 50_000_000
        if applicant.annual_income > income_limit:
            return LoanEvaluationResult(
                product_code="BEOTIMMOK",
                product_name="버팀목 전세자금대출",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason=f"소득 기준({income_limit // 10_000}만 원)을 초과합니다.",
            )

        return LoanEvaluationResult(
            product_code="BEOTIMMOK",
            product_name="버팀목 전세자금대출",
            status=LoanEligibilityStatus.ELIGIBLE,
            max_loan_amount=200_000_000 if applicant.is_newlywed else 120_000_000,
            reason="정책대출 신청 적격 조건 충족",
        )
