# MySQL 정렬 문법 오류 수정 및 새로고침 CSS 깜빡임 방지 계획서

세대순 정렬 시 MySQL 문법 오류(500 에러) 수정 및 새로고침 시 발생하던 CSS 레이아웃 깨짐(FOUC) 방지 계획입니다.

## 1. 원인 분석

1. **MySQL `NULLS LAST/FIRST` 구문 미지원 오류 (500 에러)**
   - `listing_search_service.py` L392~394에서 `nullslast()`, `nullsfirst()` 구문을 사용했으나, MySQL/MariaDB(PyMySQL) dialect에서는 `NULLS LAST` 구문 문법을 지원하지 않아 Syntax Error 1064 및 500 서버 오류가 발생했습니다.

2. **새로고침 시 CSS 레이아웃 깜빡임/깨짐 (FOUC)**
   - `base.html`에서 Tailwind Play CDN 스크립트를 사용하고 있어, 페이지 새로고침 시 CDN 스크립트가 로딩/파싱되어 스타일을 주입하기 전 찰나의 순간 동안 무스타일 HTML 화면이 노출되었습니다.

---

## 2. 주요 수정 계획

### [Backend] `src/realty_radar/application/listing_search_service.py`
- MySQL 호환 범용 정렬 처리:
  - `HOUSEHOLDS_DESC`: `func.coalesce(Listing.total_households, ApartmentComplex.total_households).desc()`
  - `HOUSEHOLDS_ASC`: `func.coalesce(Listing.total_households, ApartmentComplex.total_households).is_(None).asc()` 1차 조건 추가 후 `.asc()` 적용.

### [Frontend] `src/realty_radar/web/templates/base.html`
- `<head>` 내 사전에 기본 배경색, 폰트 테마, FOUC 방지 스타일(`html, body { background-color: #0f172a; color: #f1f5f9; min-height: 100vh; }`)을 포함시켜 CDN 로딩 지연 중에도 CSS 깨짐이나 레이아웃 순간 변형을 예방.

---

## 3. 검증 계획
- pytest 및 gradle 검증 수행.
- MySQL 및 SQLite 환경에서 `sort_by=households_desc`, `sort_by=households_asc` 정렬 쿼리 수행 500 오류 예방 검증.
