from realty_radar.domain.loan.entities import ApplicantProfile, PromissoryNoteEntry
from realty_radar.web.routes.settings import load_user_profile, save_user_profile


def test_multi_user_isolated_settings_persistence(tmp_path, monkeypatch):
    """다중 사용자(User A, User B) 조건 설정의 완전히 독립된 격리 영구 보존 테스트."""
    profiles_dir = tmp_path / "user_profiles"
    monkeypatch.setattr("realty_radar.web.routes.settings.PROFILES_DIR", profiles_dir)

    # 1. User A 설정 구성 및 저장
    profile_a = ApplicantProfile(
        is_homeless=True,
        annual_income=70_000_000,
        net_assets=350_000_000,
        is_newlywed=True,
        child_count=1,
    )
    save_user_profile(profile_a, username="user_a")

    # 2. User B 설정 구성 및 저장 (다른 값으로 입력)
    profile_b = ApplicantProfile(
        is_homeless=False,
        annual_income=120_000_000,
        net_assets=800_000_000,
        is_newlywed=False,
        child_count=3,
        use_promissory_note=True,
        promissory_notes=[PromissoryNoteEntry(name="이순신", amount=100_000_000)],
    )
    save_user_profile(profile_b, username="user_b")

    # 3. 각각 개별 로드 및 독립성 검증
    loaded_a = load_user_profile(username="user_a")
    loaded_b = load_user_profile(username="user_b")

    # User A 검증
    assert loaded_a.is_homeless is True
    assert loaded_a.annual_income == 70_000_000
    assert loaded_a.net_assets == 350_000_000
    assert loaded_a.is_newlywed is True
    assert loaded_a.child_count == 1
    assert loaded_a.use_promissory_note is False

    # User B 검증 (User A의 설정에 덮어씌워지지 않고 독립 보존됨)
    assert loaded_b.is_homeless is False
    assert loaded_b.annual_income == 120_000_000
    assert loaded_b.net_assets == 800_000_000
    assert loaded_b.is_newlywed is False
    assert loaded_b.child_count == 3
    assert loaded_b.use_promissory_note is True
    assert len(loaded_b.promissory_notes) == 1
    assert loaded_b.promissory_notes[0].name == "이순신"
    assert loaded_b.promissory_notes[0].amount == 100_000_000
