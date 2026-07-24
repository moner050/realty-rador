import pytest
from fastapi import status
from fastapi.testclient import TestClient

from realty_radar.config import settings
from realty_radar.web.auth import SESSION_COOKIE_NAME, create_session_token
from realty_radar.web.main import app


def test_unauthenticated_access_to_jobs_redirects_to_login():
    """비로그인 사용자가 /jobs 접근 시 /login으로 303 리다이렉트되어 거부되는지 검증."""
    client = TestClient(app, follow_redirects=False)
    response = client.get("/jobs")

    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers.get("location") == "/login"


def test_login_failure_with_wrong_password():
    """잘못된 비밀번호 입력 시 로그인 실패 메시지 반환 검증."""
    client = TestClient(app)
    response = client.post(
        "/login",
        data={"username": "admin", "password": "wrongpassword123"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "아이디 또는 비밀번호가 올바르지 않습니다." in response.text


def test_successful_login_and_logout_flow():
    """정상 로그인 후 세션 쿠키 발급, /jobs 접근 허용 및 로그아웃 흐름 검증."""
    client = TestClient(app, follow_redirects=False)

    # 1. 로그인 POST
    login_resp = client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )
    assert login_resp.status_code == status.HTTP_303_SEE_OTHER
    assert login_resp.headers.get("location") == "/jobs"
    assert SESSION_COOKIE_NAME in login_resp.cookies

    # 2. 쿠키를 지닌 상태에서 /jobs 접근
    session_token = login_resp.cookies[SESSION_COOKIE_NAME]
    client.cookies.set(SESSION_COOKIE_NAME, session_token)
    jobs_resp = client.get("/jobs")
    assert jobs_resp.status_code == status.HTTP_200_OK
    assert "수집 현황" in jobs_resp.text
    assert "로그아웃" in jobs_resp.text

    # 3. 로그아웃 GET
    logout_resp = client.get("/logout")
    assert logout_resp.status_code == status.HTTP_303_SEE_OTHER
    assert logout_resp.headers.get("location") == "/"
