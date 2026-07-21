from datetime import datetime
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.loan_evaluation_service import LoanEvaluationService
from realty_radar.constants import TransactionType
from realty_radar.domain.loan.entities import ApplicantProfile, LoanEligibilityStatus
from realty_radar.infrastructure.database.models import Base, CrawlSource, Listing


@pytest.fixture(name="db_session")
def db_session_fixture():
    """StaticPool 인메모리 DB 픽스처."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSession()

    source = CrawlSource(code="SITE_A", name="사이트A", base_url="https://site-a.com", adapter_name="adapter_a")
    session.add(source)
    session.flush()

    listing_sale = Listing(
        source_id=source.id,
        external_listing_id="LOAN-SALE-1",
        source_url="https://site-a.com/loan/1",
        complex_name_raw="여의도 시범아파트",
        transaction_type=TransactionType.SALE.value,
        sale_price=480_000_000,
        exclusive_area=Decimal("79.5"),
        listing_status="ACTIVE",
        first_seen_at=datetime.now(),
        last_seen_at=datetime.now(),
    )
    session.add(listing_sale)
    session.commit()

    try:
        yield session
    finally:
        session.close()


def test_loan_evaluation_service_didimdol(db_session):
    """LoanEvaluationService 매매 매물 디딤돌 대출 평가 통합 테스트."""
    service = LoanEvaluationService(db_session)
    applicant = ApplicantProfile(is_homeless=True, annual_income=50_000_000)

    results = service.evaluate_listing_loans(listing_id=1, applicant=applicant)

    assert len(results) == 1
    assert results[0].product_code == "DIDIMDOL"
    assert results[0].status == LoanEligibilityStatus.ELIGIBLE
