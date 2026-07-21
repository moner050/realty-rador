from decimal import Decimal
from realty_radar.constants import TransactionType
from realty_radar.domain.loan.entities import ApplicantProfile, LoanEligibilityStatus
from realty_radar.domain.loan.evaluator import LoanRuleEvaluator


def test_didimdol_property_only_evaluation():
    """매물 정보만 있는 경우 디딤돌 대출 PROPERTY_ELIGIBLE 평가 테스트."""
    evaluator = LoanRuleEvaluator()

    res = evaluator.evaluate_didimdol(
        transaction_type=TransactionType.SALE,
        price=450_000_000,
        exclusive_area=Decimal("84.97"),
        applicant=None,
    )

    assert res.status == LoanEligibilityStatus.PROPERTY_ELIGIBLE
    assert res.product_code == "DIDIMDOL"


def test_didimdol_full_applicant_eligible_evaluation():
    """신청자 소득 및 무주택 조건 포함 디딤돌 대출 ELIGIBLE 평가 테스트."""
    evaluator = LoanRuleEvaluator()
    applicant = ApplicantProfile(
        is_homeless=True,
        annual_income=55_000_000,
        is_newlywed=True,
    )

    res = evaluator.evaluate_didimdol(
        transaction_type=TransactionType.SALE,
        price=550_000_000,  # 신혼 6억 이하 충족
        exclusive_area=Decimal("84.97"),
        applicant=applicant,
    )

    assert res.status == LoanEligibilityStatus.ELIGIBLE
    assert res.max_loan_amount == 300_000_000


def test_didimdol_income_exceeded_ineligible():
    """소득 기준 초과 시 INELIGIBLE 평가 테스트."""
    evaluator = LoanRuleEvaluator()
    applicant = ApplicantProfile(
        is_homeless=True,
        annual_income=90_000_000,  # 8.5천만 초과
        is_newlywed=True,
    )

    res = evaluator.evaluate_didimdol(
        transaction_type=TransactionType.SALE,
        price=450_000_000,
        exclusive_area=Decimal("84.97"),
        applicant=applicant,
    )

    assert res.status == LoanEligibilityStatus.INELIGIBLE
