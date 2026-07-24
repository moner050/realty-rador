# 필터 검색 후 새로고침 시 CSS 깨짐 (FOUC / Partial HTML 노출) 수정 계획서

필터 검색 후 페이지를 새로고침(F5)할 때 전체 CSS 및 레이아웃이 유실되어 화면이 깨져 노출되는 원인을 파악하고 완벽히 수정하는 계획서입니다.

---

## 1. 원인 분석

- HTMX 검색 요청 시 브라우저 주소창이나 히스토리에 `/listings/search?...` URL이 업데이트될 수 있습니다.
- 이 상태에서 사용자가 **페이지 새로고침(F5)** 을 누르면 브라우저는 `HX-Request: true` 헤더 없이 일반 풀 페이지 GET 요청을 보냅니다.
- 기존 백엔드 라우터(`search_listings`)는 요청 헤더 구별 없이 무조건 조각 HTML 템플릿(`list_partial.html`)만 응답하였습니다.
- 이로 인해 `<head>` 태그 및 Tailwind CSS CDN이 유실된 조각 HTML만 응답받아 새로고침 시 화면 전체 CSS가 깨져 보이는 버그가 발생했습니다.

---

## 2. 주요 수정 내용

### [Backend] `src/realty_radar/web/routes/home.py`
- `search_listings` endpoints에서 `HX-Request` 헤더 분기 추가:
  ```python
  is_htmx = request.headers.get("HX-Request") == "true"
  template_name = "listings/list_partial.html" if is_htmx else "listings/index.html"
  ```
- HTMX 비동기 갱신일 때만 `list_partial.html`을 응답하고, 새로고침/직접 URL 접속 시 전체 CSS가 내장된 `index.html` 풀 페이지를 응답하도록 스마트 템플릿 스위칭 연동.

---

## 3. 검증 계획
- pytest 및 gradle 검증 수행 (`test_web_search_htmx.py`).
- 일반 브라우저 새로고침(Direct GET `/listings/search?...`) 시 `index.html` 200 OK 응답 및 전체 CSS 적용 여부 검증.
