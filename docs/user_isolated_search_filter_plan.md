# [Plan] 검색 필터링 설정 사용자별 이원화(비로그인: 로컬스토리지 / 로그인: 서버계정 파일) 고도화 계획

## 1. 개요
사용자의 자격 조건 설정뿐만 아니라 **매물 검색 필터링 조건(시/군/구, 거래유형, 가격 범위, 전용면적, 세대수, 정렬 등)** 역시 다음과 같이 완전히 이원화하여 처리합니다:
- **비로그인 사용자**: 브라우저의 `localStorage` 기반으로 검색 필터 상태 유지.
- **로그인 사용자**: 서버의 계정 파일(`data/user_profiles/{username}_filter.json`)에 영구 보존하여, 다른 기기/브라우저에서 로그인하더라도 본인의 맞춤 검색 필터링 조건이 100% 자동 복원되도록 고도화.

---

## 2. 세부 구현 계획

### 1) DTO 직렬화 및 서버 파일 저장소 구현 (`src/realty_radar/web/routes/settings.py` & `home.py`)
- `ListingSearchFilter.to_dict()` 및 `from_dict()` 지원 (`filters.py` 또는 `settings.py`)
- `save_user_search_filter(filter_params: ListingSearchFilter, username: str)`
- `load_user_search_filter(username: str) -> ListingSearchFilter | None`
- 저장 경로: `data/user_profiles/{username}_filter.json`

### 2) 메인 검색 라우터 연동 (`src/realty_radar/web/routes/home.py`)
- 로그인된 사용자가 URL 쿼리 파라미터 없이 메인 페이지(`/`)에 접속한 경우:
  - 서버에 저장된 사용자 맞춤 필터(`load_user_search_filter`)가 존재하면 이를 기본 템플릿 `filters` 객체로 주입.
- 매물 검색(`/listings/search` 및 `/`) 수행 시 로그인된 사용자라면 변경된 필터를 서버 파일(`save_user_search_filter`)에 자동 업데이트.

### 3) 프론트엔드 연동 (`src/realty_radar/web/templates/listings/index.html`)
- 비로그인 사용자는 기존처럼 클라이언트 `localStorage`에 유지.
- 로그인 사용자는 서버가 주입한 `filters` 값으로 폼이 100% 렌더링되도록 동작.

---

## 3. 검증
- `tests/unit/test_search_filter_persistence.py` 추가 및 `python -m pytest` (gradle) 전체 실행.
