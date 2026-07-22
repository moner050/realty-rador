from sqlalchemy import select
from sqlalchemy.orm import Session

from realty_radar.constants import TransactionType
from realty_radar.domain.loan.entities import ApplicantProfile, LoanEvaluationResult
from realty_radar.domain.loan.evaluator import LoanRuleEvaluator
from realty_radar.infrastructure.database.models import Listing


class LoanEvaluationService:
    """특정 매물의 정부 정책 대출 적격성 종합 평가 서비스."""

    def __init__(self, db: Session):
        self.db = db
        self.evaluator = LoanRuleEvaluator()

    def evaluate_listing_loans(
        self,
        listing_id: int,
        applicant: ApplicantProfile | None = None,
    ) -> list[LoanEvaluationResult]:
        """단일 매물에 대해 가능한 정책 대출 목록 및 적격 상태 산출."""
        stmt = select(Listing).where(Listing.id == listing_id)
        listing = self.db.scalar(stmt)

        if not listing:
            return []

        trans_type = TransactionType(listing.transaction_type)
        results: list[LoanEvaluationResult] = []
        address = listing.address_raw

        if trans_type == TransactionType.SALE:
            didimdol_res = self.evaluator.evaluate_didimdol(
                transaction_type=trans_type,
                price=listing.sale_price,
                exclusive_area=listing.exclusive_area,
                address=address,
                applicant=applicant,
            )
            bogumjari_res = self.evaluator.evaluate_bogumjari(
                transaction_type=trans_type,
                price=listing.sale_price,
                exclusive_area=listing.exclusive_area,
                address=address,
                applicant=applicant,
            )
            neonatal_res = self.evaluator.evaluate_neonatal_purchase(
                transaction_type=trans_type,
                price=listing.sale_price,
                exclusive_area=listing.exclusive_area,
                address=address,
                applicant=applicant,
            )
            results.extend([didimdol_res, bogumjari_res, neonatal_res])
        elif trans_type in [TransactionType.JEONSE, TransactionType.MONTHLY_RENT]:
            beotimmok_res = self.evaluator.evaluate_beotimmok(
                transaction_type=trans_type,
                deposit=listing.deposit,
                exclusive_area=listing.exclusive_area,
                address=address,
                applicant=applicant,
            )
            results.append(beotimmok_res)

        return results
