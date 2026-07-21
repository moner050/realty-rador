import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models import Base
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.main import app


@pytest.fixture(name="client")
def client_fixture():
    """StaticPool 인메모리 DB 및 TestClient 픽스처."""
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_search_listings_partial_api(client: TestClient):
    """HTMX partial 라우트 (/listings/search) 정상 응답 검증."""
    response = client.get("/listings/search?transaction_type=SALE&min_price=1000000")
    assert response.status_code == 200
    assert "검색 통계 서머리 뱃지" in response.text or "전체" in response.text
