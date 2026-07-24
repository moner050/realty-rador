# [Plan] 새로고침 시 필터 상태 지속 유지 고도화 계획

## 1. 개요
사용자가 웹페이지에서 시/도, 시, 군, 구, 거래유형, 가격 범위, 전용면적 등 검색 필터를 지정한 뒤 **새로고침(F5)**을 하거나 다른 페이지를 다녀와도 **필터 설정이 그대로 유지**되도록 개선합니다.

---

## 2. 해결 방안 (URL Query Sync + LocalStorage Dual-Backup)

1. **HTMX URL 동기화 (`hx-push-url="true"`)**:
   - `index.html` 내 `#search-filter-form` 폼에 `hx-push-url="true"` 속성을 지정하여, HTMX AJAX 검색 요청 시마다 브라우저 주소창(URL) 쿼리 스트링(`?sido=경기도&city=과천시...`)이 자동 갱신되도록 설정.
   - 새로고침(F5) 시 URL 쿼리 파라미터가 서버 백엔드로 전달되어 `parse_search_filter`에서 `ListingSearchFilter` DTO로 100% 파싱 및 Jinja2 템플릿의 `filters` 파라미터에 의존하여 폼이 기존 선택 값 그대로 렌더링됨.

2. **LocalStorage 2차 자동 보존 & 복원**:
   - 필터 변경 시 `localStorage.setItem('realty_radar_filter_state', ...)`로 현재 설정값을 저장.
   - URL 파라미터 없이 메인 페이지(`/`)에 첫 진입하였을 때, 기존 저장된 `localStorage` 값이 존재하면 폼 상태를 자동으로 복원하고 1회 검색 실행.
   - '필터 초기화' 클릭 시 `localStorage` 항목도 함께 리셋.

3. **Jinja2 템플릿 폼 요소 100% 복원 점검**:
   - `index.html` 내의 모든 input, select, checkbox, slider 요소들이 `filters` 객체의 속성값과 정확히 1:1 대응하여 선택 상태(`selected`, `checked`, `value`)를 보존하는지 검증.

---

## 3. 작업 파일
- `src/realty_radar/web/templates/listings/index.html`
- `docs/walkthrough_region_filter.md` 업데이트
- 검증: `python -m pytest` 및 웹 동작 테스트
