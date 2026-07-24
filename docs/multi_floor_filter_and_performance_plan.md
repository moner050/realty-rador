# 층수 다중 선택 필터 & 고성능 SQL 필터링 구현 계획서

매물 층수 선택 필터를 다중 동시 선택(예: 저층 + 중층, 고층 + 탑층) 가능하도록 개편하고, DB 인덱스를 활용하여 0.01초 내에 필터링되도록 고성능 쿼리를 빌딩하는 계획서입니다.

---

## 1. 주요 구현 내용

1. **[Database Index] 층수 전용 인덱스 보강 (`listing.py`)**
   - `Listing` 모델에 `Index("idx_listing_floor_info", "floor_info")` 추가로 0.01초 초고속 조회 보장.

2. **[Domain & Web DTO] 다중 층수 파라미터 파싱 (`filters.py`, `home.py`)**
   - `ListingSearchFilter` DTO에 `floor: str | None`, `floors: list[str] | None` 필드 추가.
   - `parsed_floors` 프로퍼티 추가 (예: `['저층', '중층']`).

3. **[Application Service] 고성능 SQL 인덱스 활용 쿼리 빌더 (`listing_search_service.py`)**
   - 저층(1~3층/저), 중층(4~10층/중), 고층(11층 이상/고), 탑층(최상층/탑), 반지하(지하/B1) 카테고리별 `or_(*floor_conditions)` 인덱스 조건문 빌딩.

4. **[Frontend] 토글 기반 다중 선택 층수 칩 UI (`index.html`)**
   - [전체] [🏢 저층 (1~3층)] [🏢 중층 (4~10층)] [🏢 고층 (11층 이상)] [👑 탑층/최상층] [🔻 반지하/지하] 토글 칩 UI.
   - `toggleFloorFilter(val)` 함수로 클릭 시 토글 선택 및 `filter-floor` hidden input에 콤마 구분자("저층,고층")로 저장 및 뱃지 표출.

5. **[Tests] 층수 필터링 단위 테스트 (`tests/unit/test_floor_filter.py`)**
   - 층수 다중 선택 파싱 및 DTO 왕복 테스트 작성.

---

## 2. 파일별 수정 계획

### [1] `src/realty_radar/infrastructure/database/models/listing.py`
- `Index("idx_listing_floor_info", "floor_info")` 추가.

### [2] `src/realty_radar/domain/listing/filters.py`
- `floor`, `floors` 필드 및 `parsed_floors` 프로퍼티 구현.

### [3] `src/realty_radar/web/routes/home.py`
- `floor`, `floors` 파라미터 수신 및 DTO 매핑.

### [4] `src/realty_radar/application/listing_search_service.py`
- 다중 층수 필터링 SQL 조건 빌더 추가.

### [5] `src/realty_radar/web/templates/listings/index.html`
- 층수 다중 선택 토글 HTML & JavaScript 칩 UI 구현.

### [6] `tests/unit/test_floor_filter.py`
- 층수 필터링 단위 테스트 케이스 신규 작성.

---

## 3. 검증 계획
- `pytest` 및 `gradle` 검증 수행.
- 층수 다중 선택 필터링 100% 구동 및 초고속 검색 확인.
