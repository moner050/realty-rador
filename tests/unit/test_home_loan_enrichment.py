from types import SimpleNamespace

from realty_radar.domain.listing.models import SearchResult
from realty_radar.domain.loan.entities import (
    ApplicantProfile,
    LoanEligibilityStatus,
    LoanEvaluationResult,
)
from realty_radar.web.routes import home


def test_render_enrichment_reuses_policy_results_computed_during_search(monkeypatch):
    cached = LoanEvaluationResult(
        product_code="BEOTIMMOK",
        product_name="버팀목",
        status=LoanEligibilityStatus.ELIGIBLE,
        max_loan_amount=100_000_000,
    )
    listing = SimpleNamespace(
        article_id=1,
        trade_type=2,
        primary_price=200_000_000,
        exclusive_area_x100=8400,
        address="서울특별시 강서구",
        loan_evaluations=[cached],
    )
    result = SearchResult(items=[listing], next_cursor=None, has_more=False)

    class UnexpectedEvaluator:
        def __getattr__(self, _name):
            raise AssertionError("cached policy evaluations must be reused")

    monkeypatch.setattr(home, "_LOAN_EVALUATOR", UnexpectedEvaluator())

    home._enrich_listings_with_loans(result, ApplicantProfile(annual_income=40_000_000))

    assert listing.loan_evaluations[0] is cached
    assert listing.eligible_loans == [cached]
    assert listing.other_loans == []
