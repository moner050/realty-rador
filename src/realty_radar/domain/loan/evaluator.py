from decimal import Decimal

from realty_radar.constants import TransactionType
from realty_radar.domain.loan.entities import (
    ApplicantProfile,
    LoanEligibilityStatus,
    LoanEvaluationResult,
)


class LoanRuleEvaluator:
    """디딤돌, 보금자리론, 신생아 특례, 버팀목 대출 조건 종합 평가 엔진."""

    def _is_capital_area(self, address: str | None) -> bool:
        """주소 기반 서울/수도권(서울, 경기, 인천) 포함 여부 판단."""
        if not address:
            return True  # 주소 미정 시 안전하게 수도권 기준 적용
        cleaned = address.strip()
        capital_keywords = ["서울", "경기", "인천", "서울특별시", "경기도", "인천광역시"]
        return any(kw in cleaned for kw in capital_keywords)

    def evaluate_didimdol(
        self,
        transaction_type: TransactionType,
        price: int | None,
        exclusive_area: Decimal | None,
        address: str | None = None,
        applicant: ApplicantProfile | None = None,
    ) -> LoanEvaluationResult:
        """내집마련 디딤돌 대출 조건 평가 (수도권 LTV 70% 제한 및 방공제 5,500만 원 차감 적용)."""
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

        is_newlywed = applicant and applicant.is_newlywed
        has_multi_children = applicant and applicant.child_count >= 2
        is_first_buyer = applicant and applicant.is_first_home_buyer
        is_capital = self._is_capital_area(address)

        # 2. 대상 주택가 상한 (신혼/다자녀 6억 원, 일반/생애최초 5억 원)
        max_price_limit = 600_000_000 if (is_newlywed or has_multi_children) else 500_000_000
        if price > max_price_limit:
            return LoanEvaluationResult(
                product_code="DIDIMDOL",
                product_name="내집마련 디딤돌대출",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason=f"매매가가 대출 한도 기준({max_price_limit // 100_000_000}억 원)을 초과합니다.",
            )

        # 3. LTV 및 방공제 계산 (수도권은 생애최초도 70% 제한 + 방공제 5.5천만원 차감)
        ltv_ratio = 0.70
        if not is_capital and is_first_buyer:
            ltv_ratio = 0.80

        raw_ltv_loan = int(int(price) * ltv_ratio)
        deduction = 55_000_000 if is_capital else 0
        possible_ltv_loan = max(0, raw_ltv_loan - deduction)

        # 디딤돌 규격 한도 (일반 2억, 생애최초 2.4억, 신혼/다자녀 3.2억 원)
        if is_newlywed or has_multi_children:
            spec_max_loan = 320_000_000
        elif is_first_buyer:
            spec_max_loan = 240_000_000
        else:
            spec_max_loan = 200_000_000

        final_loan_amount = min(spec_max_loan, possible_ltv_loan)

        # 사용자 조건 미입력 시 매물 조건만 평가
        if not applicant:
            rate = 2.65
            monthly = int(final_loan_amount * rate / 100 / 12)
            return LoanEvaluationResult(
                product_code="DIDIMDOL",
                product_name="내집마련 디딤돌대출",
                status=LoanEligibilityStatus.PROPERTY_ELIGIBLE,
                max_loan_amount=final_loan_amount,
                reason="매물 조건 충족 (개인 자격 확인 필요)",
                interest_rate=rate,
                estimated_monthly_interest=monthly,
            )

        # 4. 개인 자격 평가 (무주택 세대주 & 소득 기준)
        if not applicant.is_homeless:
            return LoanEvaluationResult(
                product_code="DIDIMDOL",
                product_name="내집마련 디딤돌대출",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason="무주택 세대주 조건 미충족",
            )

        income_limit = 60_000_000
        if is_newlywed:
            income_limit = 85_000_000
        elif is_first_buyer or has_multi_children:
            income_limit = 70_000_000

        if applicant.annual_income > income_limit:
            return LoanEvaluationResult(
                product_code="DIDIMDOL",
                product_name="내집마련 디딤돌대출",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason=f"소득 기준({income_limit // 10_000}만 원)을 초과합니다.",
            )

        # 금리 산출 (소득 기준 차등)
        if applicant.annual_income <= 20_000_000:
            didimdol_rate = 2.15
        elif applicant.annual_income <= 40_000_000:
            didimdol_rate = 2.45
        elif applicant.annual_income <= 60_000_000:
            didimdol_rate = 2.65
        else:
            didimdol_rate = 3.0

        monthly_interest = int(final_loan_amount * didimdol_rate / 100 / 12)

        return LoanEvaluationResult(
            product_code="DIDIMDOL",
            product_name="내집마련 디딤돌대출",
            status=LoanEligibilityStatus.ELIGIBLE,
            max_loan_amount=final_loan_amount,
            reason="정책대출 신청 적격 조건 충족",
            interest_rate=didimdol_rate,
            estimated_monthly_interest=monthly_interest,
        )

    def evaluate_bogumjari(
        self,
        transaction_type: TransactionType,
        price: int | None,
        exclusive_area: Decimal | None,
        address: str | None = None,
        applicant: ApplicantProfile | None = None,
    ) -> LoanEvaluationResult:
        """보금자리론 조건 평가 (방공제 미차감, 6억 이하 주택, 최대 4.2억 원)."""
        if transaction_type != TransactionType.SALE or not price:
            return LoanEvaluationResult(
                product_code="BOGUMJARI",
                product_name="보금자리론",
                status=LoanEligibilityStatus.UNKNOWN,
                reason="매매가 정보가 부족합니다.",
            )

        # 1. 대상 주택가 상한 (6억 원 이하)
        if price > 600_000_000:
            return LoanEvaluationResult(
                product_code="BOGUMJARI",
                product_name="보금자리론",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason="매매가가 대출 한도 기준(6억 원)을 초과합니다.",
            )

        is_newlywed = applicant and applicant.is_newlywed
        has_multi_children = applicant and applicant.child_count >= 2
        is_first_buyer = applicant and applicant.is_first_home_buyer
        is_capital = self._is_capital_area(address)

        # 2. LTV 계산 (방공제 미차감 / 수도권 생애최초 70% 제한)
        ltv_ratio = 0.70
        if not is_capital and is_first_buyer:
            ltv_ratio = 0.80

        possible_ltv_loan = int(int(price) * ltv_ratio)

        # 보금자리론 규격 한도 (일반 3.6억, 다자녀 4.0억, 생애최초 4.2억 원)
        if is_first_buyer:
            spec_max_loan = 420_000_000
        elif has_multi_children:
            spec_max_loan = 400_000_000
        else:
            spec_max_loan = 360_000_000

        final_loan_amount = min(spec_max_loan, possible_ltv_loan)

        if not applicant:
            rate = 3.95
            monthly = int(final_loan_amount * rate / 100 / 12)
            return LoanEvaluationResult(
                product_code="BOGUMJARI",
                product_name="보금자리론",
                status=LoanEligibilityStatus.PROPERTY_ELIGIBLE,
                max_loan_amount=final_loan_amount,
                reason="매물 조건 충족 (개인 자격 확인 필요)",
                interest_rate=rate,
                estimated_monthly_interest=monthly,
            )

        # 3. 소득 한도 평가 (일반 7천만 / 신혼 8.5천만 / 1자녀 9천만 / 2자녀+ 1억 원)
        income_limit = 70_000_000
        if applicant.child_count >= 2:
            income_limit = 100_000_000
        elif applicant.child_count == 1:
            income_limit = 90_000_000
        elif is_newlywed:
            income_limit = 85_000_000

        if applicant.annual_income > income_limit:
            return LoanEvaluationResult(
                product_code="BOGUMJARI",
                product_name="보금자리론",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason=f"소득 기준({income_limit // 10_000}만 원)을 초과합니다.",
            )

        rate = 3.95
        monthly_interest = int(final_loan_amount * rate / 100 / 12)

        return LoanEvaluationResult(
            product_code="BOGUMJARI",
            product_name="보금자리론",
            status=LoanEligibilityStatus.ELIGIBLE,
            max_loan_amount=final_loan_amount,
            reason="정책대출 신청 적격 조건 충족",
            interest_rate=rate,
            estimated_monthly_interest=monthly_interest,
        )

    def evaluate_neonatal_purchase(
        self,
        transaction_type: TransactionType,
        price: int | None,
        exclusive_area: Decimal | None,
        address: str | None = None,
        applicant: ApplicantProfile | None = None,
    ) -> LoanEvaluationResult:
        """신생아 특례대출(구입) 조건 평가 (9억 이하 주택, 소득 2.0억 원 이하, 최대 5.0억 원)."""
        if transaction_type != TransactionType.SALE or not price:
            return LoanEvaluationResult(
                product_code="NEONATAL_PURCHASE",
                product_name="신생아 특례대출(구입)",
                status=LoanEligibilityStatus.UNKNOWN,
                reason="매매가 정보가 부족합니다.",
            )

        # 1. 대상 주택가 상한 (9억 원 이하)
        if price > 900_000_000:
            return LoanEvaluationResult(
                product_code="NEONATAL_PURCHASE",
                product_name="신생아 특례대출(구입)",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason="매매가가 대출 한도 기준(9억 원)을 초과합니다.",
            )

        is_first_buyer = applicant and applicant.is_first_home_buyer
        is_capital = self._is_capital_area(address)

        ltv_ratio = 0.70
        if not is_capital and is_first_buyer:
            ltv_ratio = 0.80

        possible_ltv_loan = int(int(price) * ltv_ratio)
        final_loan_amount = min(500_000_000, possible_ltv_loan)

        if not applicant:
            rate = 2.50
            monthly = int(final_loan_amount * rate / 100 / 12)
            return LoanEvaluationResult(
                product_code="NEONATAL_PURCHASE",
                product_name="신생아 특례대출(구입)",
                status=LoanEligibilityStatus.PROPERTY_ELIGIBLE,
                max_loan_amount=final_loan_amount,
                reason="매물 조건 충족 (2년 이내 출산 가구 확인 필요)",
                interest_rate=rate,
                estimated_monthly_interest=monthly,
            )

        # 2. 2년 이내 출산 가구 조건 및 소득 기준 (2.0억 원 이하)
        if not applicant.has_newborn:
            return LoanEvaluationResult(
                product_code="NEONATAL_PURCHASE",
                product_name="신생아 특례대출(구입)",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason="2년 이내 출산(신생아) 가구 조건 미충족",
            )

        if applicant.annual_income > 200_000_000:
            return LoanEvaluationResult(
                product_code="NEONATAL_PURCHASE",
                product_name="신생아 특례대출(구입)",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason="소득 기준(2.0억 원)을 초과합니다.",
            )

        rate = 2.50
        monthly_interest = int(final_loan_amount * rate / 100 / 12)

        return LoanEvaluationResult(
            product_code="NEONATAL_PURCHASE",
            product_name="신생아 특례대출(구입)",
            status=LoanEligibilityStatus.ELIGIBLE,
            max_loan_amount=final_loan_amount,
            reason="정책대출 신청 적격 조건 충족",
            interest_rate=rate,
            estimated_monthly_interest=monthly_interest,
        )

    def evaluate_beotimmok(
        self,
        transaction_type: TransactionType,
        deposit: int | None,
        exclusive_area: Decimal | None,
        address: str | None = None,
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

        is_newlywed = applicant and applicant.is_newlywed
        has_multi_children = applicant and applicant.child_count >= 2
        is_capital = self._is_capital_area(address)

        # 보증금 한도: 신혼/다자녀 수도권 5억(비수도권 4억), 일반 수도권 3억(비수도권 2억)
        if is_newlywed or has_multi_children:
            max_deposit_limit = 500_000_000 if is_capital else 400_000_000
        else:
            max_deposit_limit = 300_000_000 if is_capital else 200_000_000

        if deposit > max_deposit_limit:
            return LoanEvaluationResult(
                product_code="BEOTIMMOK",
                product_name="버팀목 전세자금대출",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason=f"보증금이 기준({max_deposit_limit // 100_000_000}억 원)을 초과합니다.",
            )

        if not applicant:
            base_loan = 120_000_000
            rate = 2.1
            monthly = int(base_loan * rate / 100 / 12)
            return LoanEvaluationResult(
                product_code="BEOTIMMOK",
                product_name="버팀목 전세자금대출",
                status=LoanEligibilityStatus.PROPERTY_ELIGIBLE,
                max_loan_amount=base_loan,
                reason="매물 조건 충족 (개인 자격 확인 필요)",
                interest_rate=rate,
                estimated_monthly_interest=monthly,
            )

        # 소득 한도: 신혼/다자녀 7.5천만 원 이하, 일반 5.0천만 원 이하
        income_limit = 75_000_000 if (is_newlywed or has_multi_children) else 50_000_000
        if applicant.annual_income > income_limit:
            return LoanEvaluationResult(
                product_code="BEOTIMMOK",
                product_name="버팀목 전세자금대출",
                status=LoanEligibilityStatus.INELIGIBLE,
                reason=f"소득 기준({income_limit // 10_000}만 원)을 초과합니다.",
            )

        # 한도: 신혼 3억, 일반 1.2억 (수도권)
        beotimmok_max_loan = 300_000_000 if is_newlywed else 120_000_000

        if applicant.annual_income <= 20_000_000:
            beotimmok_rate = 1.8
        elif applicant.annual_income <= 40_000_000:
            beotimmok_rate = 2.1
        else:
            beotimmok_rate = 2.4

        beotimmok_monthly = int(beotimmok_max_loan * beotimmok_rate / 100 / 12)

        return LoanEvaluationResult(
            product_code="BEOTIMMOK",
            product_name="버팀목 전세자금대출",
            status=LoanEligibilityStatus.ELIGIBLE,
            max_loan_amount=beotimmok_max_loan,
            reason="정책대출 신청 적격 조건 충족",
            interest_rate=beotimmok_rate,
            estimated_monthly_interest=beotimmok_monthly,
        )
