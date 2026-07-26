from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.constants import TransactionType
from realty_radar.domain.loan.entities import ApplicantProfile, LoanEvaluationResult
from realty_radar.domain.loan.evaluator import LoanRuleEvaluator
from realty_radar.infrastructure.database.models import ListingCurrent


class LoanEvaluationService:
    """v2 article_id 기준 정책대출 평가 서비스."""

    def __init__(self, db: Session):
        self.db = db
        self.evaluator = LoanRuleEvaluator()

    def evaluate_listing_loans(self, article_id: int, applicant: ApplicantProfile | None = None) -> list[LoanEvaluationResult]:
        listing = self.db.scalar(select(ListingCurrent).where(ListingCurrent.article_id == article_id))
        if listing is None:
            return []
        transaction = {1: TransactionType.SALE, 2: TransactionType.JEONSE, 3: TransactionType.MONTHLY_RENT, 4: TransactionType.MONTHLY_RENT}.get(listing.trade_type)
        if transaction is None:
            return []
        area = Decimal(listing.exclusive_area_x100) / 100
        if transaction == TransactionType.SALE:
            return [
                self.evaluator.evaluate_didimdol(transaction, listing.primary_price, area, listing.address, applicant),
                self.evaluator.evaluate_bogumjari(transaction, listing.primary_price, area, listing.address, applicant),
                self.evaluator.evaluate_neonatal_purchase(transaction, listing.primary_price, area, listing.address, applicant),
            ]
        return [self.evaluator.evaluate_beotimmok(transaction, listing.primary_price, area, listing.address, applicant)]
