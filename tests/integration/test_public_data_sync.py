import asyncio
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.enrichment.public_data.sync_service import PublicDataSyncService
from realty_radar.infrastructure.database.models import ApartmentComplex, Base


@pytest.fixture(name="db_session")
def db_session_fixture():
    """StaticPool 인메모리 DB 픽스처."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSession()

    c1 = ApartmentComplex(official_name="여의도 시범아파트", normalized_name="여의도시범아파트")
    session.add(c1)
    session.commit()

    try:
        yield session
    finally:
        session.close()


def test_public_data_sync_service(db_session):
    """PublicDataSyncService 공공데이터 수집 및 준공연도 동기화 테스트."""
    sync_service = PublicDataSyncService(db_session)
    result = asyncio.run(sync_service.sync_complex_public_data(complex_id=1))

    assert result["status"] == "success"
    assert result["fetched_trades_count"] >= 1
