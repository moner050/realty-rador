from decimal import Decimal

import pytest

from realty_radar.constants import TransactionType
from realty_radar.domain.loan.candidate_plan import LoanCandidatePlan
from realty_radar.domain.loan.entities import ApplicantProfile
from realty_radar.domain.loan.evaluator import LoanRuleEvaluator


@pytest.mark.parametrize(
    "applicant",
    [
        ApplicantProfile(annual_income=60_000_000),
        ApplicantProfile(annual_income=85_000_000, is_newlywed=True),
        ApplicantProfile(annual_income=70_000_000, is_first_home_buyer=True),
        ApplicantProfile(annual_income=100_000_000, child_count=2),
        ApplicantProfile(annual_income=200_000_000, has_newborn=True),
        ApplicantProfile(annual_income=50_000_000),
        ApplicantProfile(annual_income=75_000_000, is_newlywed=True),
    ],
)
def test_candidate_plan_is_a_superset_of_every_eligible_policy_result(applicant):
    evaluator = LoanRuleEvaluator()
    plan = LoanCandidatePlan.for_applicant(applicant)
    properties = [
        (TransactionType.SALE, 500_000_000, Decimal("84.9"), "서울특별시 강서구", 11),
        (TransactionType.SALE, 600_000_000, Decimal("120"), "서울특별시 강서구", 11),
        (TransactionType.SALE, 900_000_000, Decimal("120"), "부산광역시 남구", 26),
        (TransactionType.JEONSE, 300_000_000, Decimal("84.9"), "서울특별시 강서구", 11),
        (TransactionType.JEONSE, 400_000_000, Decimal("84.9"), "부산광역시 남구", 26),
        (TransactionType.MONTHLY_RENT, 500_000_000, Decimal("84.9"), "서울특별시 강서구", 11),
    ]

    for transaction, price, area, address, sido_code in properties:
        evaluations = (
            evaluator.evaluate_didimdol(transaction, price, area, address, applicant),
            evaluator.evaluate_bogumjari(transaction, price, area, address, applicant),
            evaluator.evaluate_neonatal_purchase(transaction, price, area, address, applicant),
            evaluator.evaluate_beotimmok(transaction, price, area, address, applicant),
        )
        if any(evaluation.is_eligible for evaluation in evaluations):
            trade_type = {
                TransactionType.SALE: 1,
                TransactionType.JEONSE: 2,
                TransactionType.MONTHLY_RENT: 3,
            }[transaction]
            assert plan.matches(
                trade_type=trade_type,
                primary_price=price,
                exclusive_area_x100=int(area * 100),
                sido_code=sido_code,
            )


def test_candidate_plan_is_empty_when_no_policy_can_accept_the_applicant():
    plan = LoanCandidatePlan.for_applicant(
        ApplicantProfile(
            is_homeless=False,
            annual_income=250_000_000,
            has_newborn=False,
        )
    )

    assert plan.branches == ()


def test_candidate_plan_separates_sale_and_rental_limits():
    plan = LoanCandidatePlan.for_applicant(
        ApplicantProfile(annual_income=70_000_000, is_newlywed=True)
    )

    assert [branch.trade_types for branch in plan.branches] == [(1,), (2, 3, 4)]
    assert plan.branches[0].capital_max_price == 600_000_000
    assert plan.branches[0].max_exclusive_area_x100 is None
    assert plan.branches[1].capital_max_price == 500_000_000
    assert plan.branches[1].non_capital_max_price == 400_000_000
    assert plan.branches[1].max_exclusive_area_x100 == 8500


@pytest.mark.parametrize("address", [None, "", "서울특별시 강서구"])
def test_candidate_plan_never_excludes_a_property_the_evaluator_treats_as_capital_area(address):
    applicant = ApplicantProfile(annual_income=50_000_000)
    evaluation = LoanRuleEvaluator().evaluate_beotimmok(
        TransactionType.JEONSE,
        300_000_000,
        Decimal("85"),
        address,
        applicant,
    )

    assert evaluation.is_eligible is True
    assert LoanCandidatePlan.for_applicant(applicant).matches(
        trade_type=2,
        primary_price=300_000_000,
        exclusive_area_x100=8500,
        sido_code=26,
        address=address,
    )


@pytest.mark.parametrize(
    ("method_name", "applicant", "transaction", "price", "area", "address", "sido_code", "trade_type"),
    [
        (
            "evaluate_didimdol",
            ApplicantProfile(annual_income=60_000_000),
            TransactionType.SALE,
            500_000_000,
            Decimal("85"),
            "서울특별시 강서구",
            11,
            1,
        ),
        (
            "evaluate_didimdol",
            ApplicantProfile(annual_income=85_000_000, is_newlywed=True),
            TransactionType.SALE,
            600_000_000,
            Decimal("85"),
            "부산광역시 해운대구",
            26,
            1,
        ),
        (
            "evaluate_bogumjari",
            ApplicantProfile(annual_income=70_000_000),
            TransactionType.SALE,
            600_000_000,
            Decimal("120"),
            "서울특별시 강서구",
            11,
            1,
        ),
        (
            "evaluate_bogumjari",
            ApplicantProfile(annual_income=90_000_000, child_count=1),
            TransactionType.SALE,
            600_000_000,
            Decimal("120"),
            "부산광역시 해운대구",
            26,
            1,
        ),
        (
            "evaluate_bogumjari",
            ApplicantProfile(annual_income=100_000_000, child_count=2),
            TransactionType.SALE,
            600_000_000,
            Decimal("120"),
            "부산광역시 해운대구",
            26,
            1,
        ),
        (
            "evaluate_neonatal_purchase",
            ApplicantProfile(annual_income=200_000_000, has_newborn=True),
            TransactionType.SALE,
            900_000_000,
            Decimal("120"),
            "서울특별시 강서구",
            11,
            1,
        ),
        (
            "evaluate_beotimmok",
            ApplicantProfile(annual_income=50_000_000),
            TransactionType.JEONSE,
            200_000_000,
            Decimal("85"),
            "부산광역시 해운대구",
            26,
            2,
        ),
        (
            "evaluate_beotimmok",
            ApplicantProfile(annual_income=50_000_000),
            TransactionType.MONTHLY_RENT,
            300_000_000,
            Decimal("85"),
            "서울특별시 강서구",
            11,
            3,
        ),
        (
            "evaluate_beotimmok",
            ApplicantProfile(annual_income=75_000_000, is_newlywed=True),
            TransactionType.JEONSE,
            500_000_000,
            Decimal("85"),
            "인천광역시 연수구",
            28,
            2,
        ),
        (
            "evaluate_beotimmok",
            ApplicantProfile(annual_income=75_000_000, child_count=2),
            TransactionType.MONTHLY_RENT,
            400_000_000,
            Decimal("85"),
            "부산광역시 해운대구",
            26,
            4,
        ),
    ],
)
def test_candidate_plan_includes_each_product_at_eligibility_boundaries(
    method_name,
    applicant,
    transaction,
    price,
    area,
    address,
    sido_code,
    trade_type,
):
    evaluation = getattr(LoanRuleEvaluator(), method_name)(
        transaction,
        price,
        area,
        address,
        applicant,
    )

    assert evaluation.is_eligible is True
    assert LoanCandidatePlan.for_applicant(applicant).matches(
        trade_type=trade_type,
        primary_price=price,
        exclusive_area_x100=int(area * 100),
        sido_code=sido_code,
        address=address,
    )
