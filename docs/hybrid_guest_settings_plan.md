# [Plan] 비로그인 사용자 로컬스토리지 & 로그인 사용자 서버 영구보존 하이브리드 설정 계획

## 1. 개요
사용자의 개인 자격 조건 설정(`/settings`)을 다음과 같이 이원화(Hybrid)하여 처리합니다:
- **로그인 사용자**: 기존처럼 서버의 유저 계정 파일(`data/user_profiles/{username}.json`)에 영구 저장.
- **비로그인 사용자**: 브라우저의 `localStorage` 및 `guest_profile` 쿠키에 저장하여, 비로그인 상태에서도 본인의 설정에 맞추어 매물 검색 및 대출 적격성 평가를 지속적으로 이용할 수 있도록 고도화.

---

## 2. 세부 구현 내용

### 1) 설정 라우트 접근 제어 및 하이브리드 보존 (`src/realty_radar/web/routes/settings.py`)
- `/settings` 라우트의 강제 로그인 의존성(`require_authentication`)을 제거하여 비로그인 사용자도 설정 페이지 접근 허용.
- `update_settings` 라우터:
  - **로그인 상태**: `save_user_profile(profile, username)` 서버 파일 저장.
  - **비로그인 상태**: `guest_profile` 암호화/JSON 쿠키 저장 및 클라이언트 `localStorage` 연동.

### 2) 사용자 프로필 조회 헬퍼 보강 (`src/realty_radar/web/routes/settings.py`)
- `get_request_user_profile(request: Request) -> ApplicantProfile`:
  - 1순위: 로그인 사용자 ➔ 서버 파일 `load_user_profile(username)`
  - 2순위: 비로그인 사용자 ➔ 요청 쿠키 `guest_profile` 파싱 복원
  - 3순위: 기본 `ApplicantProfile()`

### 3) 메인 검색 연동 (`src/realty_radar/web/routes/home.py`)
- `index` 및 `search_listings`에서 `get_request_user_profile(request)`를 호출하여 로그인 여부와 관계없이 사용자의 설정 프로필을 반영한 대출 평가 및 필터링 수행.

### 4) 설정 페이지 프론트엔드 연동 (`src/realty_radar/web/templates/settings/index.html`)
- 비로그인 사용자가 설정 제출 시 JS에서 `localStorage.setItem('realty_radar_guest_profile', ...)` 저장 및 `guest_profile` 쿠키 동기화 처리.

---

## 3. 작업 순서
1. `docs/hybrid_guest_settings_plan.md` 생성
2. `src/realty_radar/web/routes/settings.py` 수정
3. `src/realty_radar/web/routes/home.py` 수정
4. `src/realty_radar/web/templates/settings/index.html` JS 추가
5. 단위 및 통합 테스트 작성 (`tests/unit/test_guest_settings_hybrid.py`)
6. `python -m pytest` (gradle) 검증 실행
