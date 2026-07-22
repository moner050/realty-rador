# 작업 계획서: 상단 고정 서머리 바 및 미니 페이지네이션 구현

## 1. 개요
매물 목록을 아래로 스크롤하더라도 검색 통계 서머리 바(전체 건수, 신규, 페이지 정보)가 상단에 고정되도록 디자인하고, 해당 고정 바에 미니 페이지 이동 버튼을 추가합니다.

## 2. 상세 작업 계획
- 위치: `src/realty_radar/web/templates/listings/list_partial.html`
- 상단 서머리 뱃지 요소에 `sticky top-16 z-40 bg-slate-900/90 backdrop-blur` 스타일 적용.
- 페이지 표시 영역 우측에 HTMX 미니 이전/다음 버튼(`hx-get="/listings/search?page=N"`, `hx-include="#search-filter-form"`) 추가.

## 3. 검증 계획
- `pytest tests/integration/test_web_search_htmx.py` 테스트 실행.
- 브라우저 스크롤 동작 및 스티키 헤더 미니 페이징 이동 버튼 동작 확인.

## 4. 수행 결과 보고
- **상단 스티키 고정 레이아웃 적용**: `list_partial.html` 서머리 바에 `sticky top-16 z-40 bg-slate-900/90 backdrop-blur-md` 스타일을 지정하여 매물 목록 스크롤 시에도 헤더 하단에 고정되도록 구현하였습니다.
- **미니 페이지 이동 컨트롤 추가**: 고정 바 우측 페이지 표시 영역 옆에 미니 이전/다음 버튼(`<`/`>`)을 추가하고, HTMX 연동(`hx-include="#search-filter-form"`)으로 스크롤 도중에도 필터 조건을 유지하며 즉시 페이지를 전환할 수 있게 제작했습니다.
- **테스트 검증**: 39개 전체 테스트를 실행하여 오류 없이 통과(`39 passed`)함을 확인하였습니다.
