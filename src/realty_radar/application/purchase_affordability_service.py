"""Purchase-affordability calculations based on current policy-loan estimates."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Any, Iterable

from realty_radar.domain.loan.entities import ApplicantProfile, LoanEvaluationResult


PURCHASE_TERM_MONTHS = 360


@dataclass(frozen=True, slots=True)
class PurchaseAffordabilityResult:
    selected_loan: LoanEvaluationResult | None
    closing_cost_reserve: int
    required_cash: int
    monthly_principal_and_interest: int
    monthly_management_cost: int
    existing_monthly_debt_payment: int
    total_monthly_housing_cost: int
    cash_budget_met: bool | None
    monthly_budget_met: bool | None
    is_affordable: bool | None


class PurchaseAffordabilityService:
    def calculate(
        self,
        listing: Any,
        evaluations: Iterable[LoanEvaluationResult],
        applicant: ApplicantProfile,
    ) -> PurchaseAffordabilityResult | None:
        if getattr(listing, "trade_type", None) != 1:
            return None
        price = int(getattr(listing, "primary_price", 0) or 0)
        if price <= 0:
            return None

        selected_loan = self._select_loan(evaluations)
        loan_amount = int(selected_loan.max_loan_amount) if selected_loan is not None else 0
        annual_rate = float(selected_loan.interest_rate) if selected_loan is not None else 0.0
        closing_cost_reserve = self._closing_cost_reserve(price, applicant.closing_cost_reserve_bps)
        required_cash = max(0, price - loan_amount) + closing_cost_reserve
        monthly_principal_and_interest = self._monthly_payment(loan_amount, annual_rate)
        monthly_management_cost = int(getattr(listing, "monthly_management_cost", 0) or 0)
        existing_monthly_debt_payment = int(applicant.existing_monthly_debt_payment or 0)
        total_monthly_housing_cost = (
            monthly_principal_and_interest + monthly_management_cost + existing_monthly_debt_payment
        )
        cash_budget_met = (
            applicant.available_cash >= required_cash if applicant.available_cash is not None else None
        )
        monthly_budget_met = (
            total_monthly_housing_cost <= applicant.max_monthly_housing_cost
            if applicant.max_monthly_housing_cost is not None
            else None
        )
        is_affordable = (
            cash_budget_met and monthly_budget_met
            if cash_budget_met is not None and monthly_budget_met is not None
            else None
        )
        return PurchaseAffordabilityResult(
            selected_loan=selected_loan,
            closing_cost_reserve=closing_cost_reserve,
            required_cash=required_cash,
            monthly_principal_and_interest=monthly_principal_and_interest,
            monthly_management_cost=monthly_management_cost,
            existing_monthly_debt_payment=existing_monthly_debt_payment,
            total_monthly_housing_cost=total_monthly_housing_cost,
            cash_budget_met=cash_budget_met,
            monthly_budget_met=monthly_budget_met,
            is_affordable=is_affordable,
        )

    @staticmethod
    def _select_loan(evaluations: Iterable[LoanEvaluationResult]) -> LoanEvaluationResult | None:
        candidates = [
            evaluation
            for evaluation in evaluations
            if evaluation.is_eligible
            and evaluation.max_loan_amount is not None
            and evaluation.max_loan_amount > 0
            and evaluation.interest_rate is not None
        ]
        return min(
            candidates,
            key=lambda evaluation: (
                -int(evaluation.max_loan_amount or 0),
                Decimal(str(evaluation.interest_rate)),
                evaluation.product_code,
            ),
            default=None,
        )

    @staticmethod
    def _closing_cost_reserve(price: int, reserve_bps: int) -> int:
        return int(
            (Decimal(price) * max(0, int(reserve_bps)) / Decimal(10_000)).to_integral_value(
                rounding=ROUND_CEILING
            )
        )

    @staticmethod
    def _monthly_payment(principal: int, annual_rate: float, term_months: int = PURCHASE_TERM_MONTHS) -> int:
        if principal <= 0:
            return 0
        monthly_rate = Decimal(str(annual_rate)) / Decimal(1200)
        if monthly_rate == 0:
            return int(
                (Decimal(principal) / term_months).quantize(Decimal(1), rounding=ROUND_HALF_UP)
            )
        factor = (Decimal(1) + monthly_rate) ** term_months
        payment = Decimal(principal) * monthly_rate * factor / (factor - Decimal(1))
        return int(payment.quantize(Decimal(1), rounding=ROUND_HALF_UP))
