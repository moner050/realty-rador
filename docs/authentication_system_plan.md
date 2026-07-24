# 관리자 로그인 인증 및 수집현황 권한 제어 시스템 설계 계획서

## 1. 개요 및 기능 목적

### 1) 기능 목적
- 로그인한 관리자만 **[수집 현황]** (`/jobs`) 및 **[설정]** (`/settings`) 메뉴에 접근하여 스크래핑 작업을 실행 및 관리할 수 있도록 보호합니다.
- 비로그인 사용자는 네비게이션 바에서 [수집 현황] 메뉴가 노출되지 않으며, URL 직입 시 로그인 페이지(`/login`)로 자동으로 안전하게 리다이렉트 처리합니다.

---

## 2. 세부 구현 사항

### 1) 설정 및 DTO 확장 (`config.py`)
- `admin_username: str = "admin"`
- `admin_password: str = "admin1234"` (환경변수 `.env`로 자유롭게 변경 가능)
- `secret_key: str = "realty-radar-secret-key-2026"`

### 2) 인증 헬퍼 및 세션 쿠키 검증 (`web/auth.py`)
- 쿠키 기반 `realty_session` 서명 토큰 생성 및 검증 로직.
- `is_authenticated(request)` 헬퍼 함수 작성.
- `require_auth(request)` 의존성: 비인증 시 `RedirectResponse(url="/login", status_code=303)` 처리.

### 3) 로그인 / 로그아웃 라우터 및 뷰 (`web/routes/auth.py`, `login.html`)
- `GET /login`: 다크모드 로그인 UI 렌더링.
- `POST /login`: 아이디/비밀번호 검증 및 세션 쿠키 설정 후 `/jobs` 이동.
- `GET /logout`: 쿠키 제거 후 메인 페이지 리다이렉트.

### 4) 수집 현황 및 설정 라우터 접근 권한 보호 (`crawl_jobs.py`, `settings.py`)
- `/jobs` 및 `/settings` 관련 모든 엔드포인트에 `require_auth` 권한 보호 적용.

### 5) 네비게이션 바 UI 조건부 렌더링 (`base.html`)
- `is_authenticated` 값에 따라 [수집 현황], [설정], [로그아웃] vs [로그인] 버튼 동적 전환.

---

## 3. 검증 계획
1. `tests/integration/test_auth.py` 작성:
   - 비로그인 상태에서 `/jobs` 접근 시 `/login`으로 303 리다이렉트 검증.
   - 올바른 아이디/비밀번호로 `POST /login` 시 로그인 성공 및 쿠키 발급 검증.
   - 로그아웃 동작 검증.
2. pytest 전체 54개 이상 유닛/통합 테스트 100% 통과 확인.
