import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models import (
    ApartmentComplex,
    Base,
    ComplexAlias,
    CrawlJob,
    CrawlSchedule,
    CrawlSource,
    Listing,
    ListingSnapshot,
)
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.main import app


@pytest.fixture(name="client")
def client_fixture():
    """StaticPool 기반 인메모리 SQLite DB 픽스처."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # 인메모리 DB 테이블 생성
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


def test_healthcheck(client: TestClient):
    """헬스체크 API 응답 검증."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_home_index(client: TestClient):
    """홈 검색 메인 페이지 HTML 렌더링 검증."""
    response = client.get("/")
    assert response.status_code == 200
    assert "통합 매물 검색" in response.text
    assert "Realty Radar" in response.text
