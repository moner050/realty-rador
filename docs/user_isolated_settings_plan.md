# [Plan] 사용자별 설정 격리(User-Isolated Multi-User Persistence) 고도화 계획

## 1. 개요 및 원인 분석
기존 단일 파일(`data/user_profile.json`) 방식은 여러 사용자가 동시에 접근하여 개인 조건 설정을 저장을 할 경우, 다른 사용자의 설정값을 덮어쓰는(Overwriting) 충돌 문제가 발생할 수 있습니다.

이를 해결하기 위해 **로그인된 사용자 계정명(`username`) 또는 세션 식별자 단위로 설정 파일을 완전히 격리하여 독립 저장/로드**되도록 개선합니다.

---

## 2. 세부 구현 계획

### 1) 사용자 식별 헬퍼 함수 구현 (`src/realty_radar/web/auth.py`)
- `get_current_username(request: Request) -> str`: 요청 쿠키에서 현재 로그인 유저 식별자(`username`)를 추출 (미로그인 시 'guest_user' 또는 세션 ID 기반 분리).

### 2) 사용자별 프로필 영구 저장소 분리 (`src/realty_radar/web/routes/settings.py`)
- 저장 경로: `data/user_profiles/{username}.json`
- `load_user_profile(username: str = "admin") -> ApplicantProfile`
- `save_user_profile(profile: ApplicantProfile, username: str = "admin") -> None`
- `/settings` GET/POST 및 `/` (홈 검색) 호출 시 요청 사용자의 `username`에 알맞은 독자적인 프로필을 로드/저장 처리.

### 3) 단위 테스트 보강 (`tests/unit/test_settings_persistence.py`)
- 다중 사용자(User A, User B) 독립 저장 및 서로 간 간섭이 없는지 정밀 검증 케이스 추가.

---

## 3. 검증
- `python -m pytest` 실행 및 다중 사용자 독립성 테스트 확인.
