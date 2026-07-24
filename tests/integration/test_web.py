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
from realty_radar.web.auth import SESSION_COOKIE_NAME, create_session_token
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
        test_client.cookies.set(SESSION_COOKIE_NAME, create_session_token("admin"))
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


def test_settings_page(client: TestClient):
    """설정 페이지 HTML 렌더링 및 콤마 필터 에러가 없는지 검증."""
    response = client.get("/settings")
    assert response.status_code == 200
    assert "개인 자격 및 정책대출 조건 설정" in response.text
    assert "개인 또는 부부합산 연소득" in response.text


def test_update_settings(client: TestClient):
    """설정 페이지 값 수정 시 정상 변경 확인."""
    data = {
        "is_homeless": "true",
        "annual_income": "75000000",
        "net_assets": "350000000",
        "is_newlywed": "true",
        "is_first_home_buyer": "false",
        "child_count": "1",
    }
    response = client.post("/settings", data=data)
    assert response.status_code == 200
    assert "성공적으로 저장되었습니다" in response.text
    assert "75,000,000" in response.text

