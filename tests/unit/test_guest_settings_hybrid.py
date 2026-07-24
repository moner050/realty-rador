import urllib.parse
from fastapi.testclient import TestClient

from realty_radar.web.main import app
from realty_radar.web.routes.settings import GUEST_COOKIE_NAME, load_user_profile, save_user_profile

client = TestClient(app)


def test_hybrid_guest_and_user_settings(tmp_path, monkeypatch):
    """비로그인 게스트(쿠키/로컬스토리지) 및 로그인 사용자 하이브리드 보존 정밀 테스트."""
    profiles_dir = tmp_path / "user_profiles"
    monkeypatch.setattr("realty_radar.web.routes.settings.PROFILES_DIR", profiles_dir)

    # 1. 비로그인 사용자 /settings GET 접속 가능 여부 (303 리다이렉트가 아닌 200 OK 응답 검증)
    response = client.get("/settings")
    assert response.status_code == 200
    assert "개인 자격 및 정책대출 조건 설정" in response.text

    # 2. 비로그인 사용자 설정 POST 저장 ➔ guest_profile 쿠키 발급 검증
    post_data = {
        "is_homeless": "true",
        "annual_income": "85000000",
        "net_assets": "500000000",
        "is_newlywed": "true",
        "child_count": "2",
    }
    res_post = client.post("/settings", data=post_data)
    assert res_post.status_code == 200
    assert GUEST_COOKIE_NAME in res_post.cookies

    # 3. 비로그인 게스트 쿠키가 들어있는 상태로 메인 검색(/) 접근 ➔ 쿠키 프로필 파싱 반영 검증
    cookie_val = res_post.cookies[GUEST_COOKIE_NAME]
    res_home = client.get("/", cookies={GUEST_COOKIE_NAME: cookie_val})
    assert res_home.status_code == 200

    # 4. 로그인 사용자는 독립된 서버 파일 저장 검증
    from realty_radar.domain.loan.entities import ApplicantProfile

    profile_user1 = ApplicantProfile(annual_income=90_000_000, net_assets=600_000_000)
    save_user_profile(profile_user1, username="admin")

    loaded_admin = load_user_profile("admin")
    assert loaded_admin.annual_income == 90_000_000
    assert loaded_admin.net_assets == 600_000_000
