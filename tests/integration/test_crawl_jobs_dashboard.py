from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models import Base
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.auth import SESSION_COOKIE_NAME, create_session_token
from realty_radar.web.main import app


@pytest.fixture
def jobs_client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token("dashboard-test"))
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_metro_post_enqueues_batch_and_returns_progress_fragment(jobs_client: TestClient):
    response = jobs_client.post("/api/crawl-jobs/metro", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert 'id="metro-progress"' in response.text
    assert "worker 대기 중" in response.text
    assert "서울" in response.text
    assert 'disabled aria-disabled="true"' in response.text


def test_jobs_dashboard_renders_disabled_metro_button_and_sigungu_statuses(jobs_client: TestClient):
    jobs_client.post("/api/crawl-jobs/metro")

    response = jobs_client.get("/jobs")

    assert response.status_code == 200
    assert 'action="/api/crawl-jobs/metro"' in response.text
    assert "수도권 전체 수동 수집" in response.text
    assert "시/군/구별 진행 현황" in response.text
    assert "disabled" in response.text
    assert 'hx-trigger="every 5s"' in response.text
