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
        address="서울특별시 동대문구 답십리동",
        applicant=applicant,
    )

    assert res.status == LoanEligibilityStatus.ELIGIBLE
    # 수도권 LTV 70%: 5.5억 * 0.7 = 3.85억 - 방공제 0.55억 = 3.3억 -> 신혼 규격 최대 3.2억 적용
    assert res.max_loan_amount == 320_000_000


def test_didimdol_first_buyer_capital_area_deduction():
    """수도권 주택 디딤돌 생애최초 2.4억 한도 및 방공제 차감 평가 테스트."""
    evaluator = LoanRuleEvaluator()
    applicant = ApplicantProfile(
        is_homeless=True,
        annual_income=65_000_000,  # 생애최초 소득 7천만 이하 충족
        is_first_home_buyer=True,
    )

    res = evaluator.evaluate_didimdol(
        transaction_type=TransactionType.SALE,
        price=400_000_000,  # 4억
        exclusive_area=Decimal("59.9"),
        address="경기도 안산시 단원구",
        applicant=applicant,
    )

    # 4억 * 70%(수도권 LTV) = 2.8억 - 방공제 5,500만 = 2.25억 (생초 규격 한도 2.4억 이하이므로 2.25억)
    assert res.status == LoanEligibilityStatus.ELIGIBLE
    assert res.max_loan_amount == 225_000_000


def test_bogumjari_eligible_evaluation():
    """보금자리론 적격성 및 방공제 미차감 평가 테스트."""
    evaluator = LoanRuleEvaluator()
    applicant = ApplicantProfile(
        is_homeless=True,
        annual_income=68_000_000,
        is_first_home_buyer=True,
    )

    res = evaluator.evaluate_bogumjari(
        transaction_type=TransactionType.SALE,
        price=580_000_000,  # 6억 이하
        exclusive_area=Decimal("84.9"),
        address="서울특별시 마포구",
        applicant=applicant,
    )

    assert res.status == LoanEligibilityStatus.ELIGIBLE
    # 수도권 LTV 70%: 5.8억 * 0.7 = 4.06억 (방공제 차감 없음) <= 생초 한도 4.2억
    assert res.max_loan_amount == 406_000_000


def test_neonatal_purchase_eligible_evaluation():
    """신생아 특례대출 9억 이하 매물 및 소득 1.3억/맞벌이 2억 이하 적격성 평가 테스트."""
    evaluator = LoanRuleEvaluator()
    applicant = ApplicantProfile(
        is_homeless=True,
        annual_income=120_000_000,  # 외벌이 1.3억 이하
        has_newborn=True,  # 2년 이내 출산 가구
    )

    res = evaluator.evaluate_neonatal_purchase(
        transaction_type=TransactionType.SALE,
        price=850_000_000,  # 9억 이하
        exclusive_area=Decimal("84.9"),
        address="서울특별시 강남구",
        applicant=applicant,
    )

    assert res.status == LoanEligibilityStatus.ELIGIBLE
    # 수도권 LTV 70%: 8.5억 * 0.7 = 5.95억 -> 최신 2025.06 개정 상한 한도 4.0억 적용
    assert res.max_loan_amount == 400_000_000


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
