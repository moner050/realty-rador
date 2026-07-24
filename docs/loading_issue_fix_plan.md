# 홈페이지 무한 로딩 원인 분석 및 해결 계획서

홈페이지 접속 시 "로딩중..." 마스크만 지속되고 결과가 출력되지 않는 현상에 대한 원인 분석 및 수정 계획입니다.

## 원인 분석

1. **백엔드 미정의 변수 참조 (NameError 및 500 에러)**
   - `src/realty_radar/web/routes/home.py` 파일의 `_enrich_listings_with_loans` 함수 내부에서 정의되지 않은 `session_user_profile` 변수를 직접 참조하고 있습니다.
   - `_enrich_listings_with_loans` 호출 시 `applicant` 객체가 전달되지 않아 대출 적격성 평가 중 예외가 발생하거나 500 서버 내부 오류가 유발됩니다.

2. **HTMX 비동기 요청 실패 시 로딩 마스크 미해제**
   - `index.html`에서 `hx-indicator="#search-loading-indicator"`를 사용하여 필터 변경 및 검색 시 로딩 인디케이터를 띄우지만, 백엔드 500 에러 또는 서버 비정상 종료 시 HTMX 이벤트 실패 핸들링이 없어서 로딩 인디케이터가 해제되지 않고 멈춰있는 현상이 발생합니다.

3. **웹 서버 프로세스 종료**
   - 백엔드 서버(uvicorn)가 비정상 종료된 경우, 프론트엔드의 비동기 HTMX 요청이 응답을 받지 못하여 로딩 상태가 유지됩니다.

---

## 주요 변경 사항

### [Backend] `src/realty_radar/web/routes/home.py`
- `_enrich_listings_with_loans` 함수 파라미터에 `applicant: ApplicantProfile | None = None` 추가.
- 내부 `session_user_profile` 변수를 인자로 전달받은 `applicant`로 변경.
- `index` 및 `search_listings` 라우터 함수에서 `_enrich_listings_with_loans(result, db, current_profile)`로 인자 정상 전달.

### [Frontend] `src/realty_radar/web/templates/listings/index.html`
- HTMX 에러 핸들러(`htmx:responseError`, `htmx:sendError`)를 추가하여 서버 500 에러 또는 네트워크 오류 발생 시 로딩 인디케이터를 숨기고 알림 메시지를 표출하도록 보완.

---

## 검증 계획

### 자동화 검증 (Gradle)
- `gradle test` 및 `gradle check` 명령어를 수행하여 pytest 및 linter 검증 통과 확인.
