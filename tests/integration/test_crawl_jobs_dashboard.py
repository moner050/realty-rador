from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models import Base
from realty_radar.infrastructure.database.models.v2 import UserAccount
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.auth import SESSION_COOKIE_NAME, create_session_token, hash_password
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

    with factory() as session:
        admin_user = UserAccount(
            username="dashboard-test",
            password_hash=hash_password("admin1234"),
            role="ADMIN",
        )
        session.add(admin_user)
        session.commit()

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


def test_metro_post_enqueues_only_the_selected_municipality_jobs(jobs_client: TestClient):
    response = jobs_client.post(
        "/api/crawl-jobs/metro",
        data={"sido_code": "41", "municipality": "수원시"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "총 4곳" in response.text
    assert "수원시 장안구" in response.text
    assert "수원시 영통구" in response.text
    assert "성남시 분당구" not in response.text


def test_jobs_dashboard_renders_disabled_metro_button_and_sigungu_statuses(jobs_client: TestClient):
    jobs_client.post("/api/crawl-jobs/metro")

    response = jobs_client.get("/jobs")

    assert response.status_code == 200
    assert 'action="/api/crawl-jobs/metro"' in response.text
    assert "수도권 아파트 수집 현황" in response.text
    assert "SITE_A 수집 작업" not in response.text
    assert "수도권 아파트 수동 수집" in response.text
    assert 'id="metro-sido-select" name="sido_code"' in response.text
    assert 'id="metro-municipality-select" name="municipality"' in response.text
    assert 'id="metro-district-select" name="sigungu_code"' in response.text
    assert "시/군/구별 진행 현황" in response.text
    assert "disabled" in response.text
    assert 'hx-trigger="every 5s"' in response.text


def test_user_role_blocked_from_jobs_dashboard():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    with factory() as session:
        normal_user = UserAccount(
            username="normal-user",
            password_hash=hash_password("user1234"),
            role="USER",
        )
        session.add(normal_user)
        session.commit()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, create_session_token("normal-user"))

    try:
        response = client.get("/jobs")
        assert response.status_code == 403
        assert "관리자(ADMIN) 권한이 필요합니다." in response.text
    finally:
        app.dependency_overrides.clear()
