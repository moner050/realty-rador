from types import SimpleNamespace

from realty_radar.domain.loan.entities import ApplicantProfile, LoanEligibilityStatus, LoanEvaluationResult


def sale_listing(*, price: int, management_cost: int | None = None):
    return SimpleNamespace(trade_type=1, primary_price=price, monthly_management_cost=management_cost)


def eligible(product_code: str, amount: int, rate: float):
    return LoanEvaluationResult(
        product_code=product_code,
        product_name=product_code,
        status=LoanEligibilityStatus.ELIGIBLE,
        max_loan_amount=amount,
        interest_rate=rate,
    )


def test_calculator_uses_largest_eligible_loan_then_lower_rate_for_ties():
    from realty_radar.application.purchase_affordability_service import PurchaseAffordabilityService

    result = PurchaseAffordabilityService().calculate(
        sale_listing(price=600_000_000, management_cost=180_000),
        [eligible("DIDIMDOL", 360_000_000, 2.65), eligible("BOGUMJARI", 360_000_000, 3.95)],
        ApplicantProfile(
            available_cash=300_000_000,
            existing_monthly_debt_payment=200_000,
            max_monthly_housing_cost=2_000_000,
            closing_cost_reserve_bps=200,
        ),
    )

    assert result.selected_loan.product_code == "DIDIMDOL"
    assert result.closing_cost_reserve == 12_000_000
    assert result.required_cash == 252_000_000
    assert result.monthly_principal_and_interest == 1_450_670
    assert result.total_monthly_housing_cost == 1_830_670
    assert result.cash_budget_met is True
    assert result.monthly_budget_met is True
    assert result.is_affordable is True


def test_calculator_returns_indeterminate_affordability_for_missing_limits():
    from realty_radar.application.purchase_affordability_service import PurchaseAffordabilityService

    result = PurchaseAffordabilityService().calculate(sale_listing(price=500_000_000), [], ApplicantProfile())

    assert result.required_cash == 510_000_000
    assert result.monthly_principal_and_interest == 0
    assert result.cash_budget_met is None
    assert result.monthly_budget_met is None
    assert result.is_affordable is None


def test_zero_interest_loan_is_split_evenly_over_360_months():
    from realty_radar.application.purchase_affordability_service import PurchaseAffordabilityService

    result = PurchaseAffordabilityService().calculate(
        sale_listing(price=120_000_000), [eligible("ZERO", 120_000_000, 0)], ApplicantProfile()
    )

    assert result.monthly_principal_and_interest == 333_333
