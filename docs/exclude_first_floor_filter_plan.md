# 층수 필터 내 1층 제외 필터 옵션 추가 & 정밀 SQL 조건 구현 계획서

층수 필터 칩에 **[🚫 1층 제외 (2층 이상)]** 칩 버튼을 추가하고, 11층/21층/31층 등은 제외되지 않고 오직 1층 매물만 정밀하게 필터링하여 걸러내는 고성능 SQL 쿼리를 구현하는 계획서입니다.

---

## 1. 개편 내용

1. **[Frontend UI] 1층 제외 칩 추가 (`index.html`)**
   - 층수 다중 선택 칩 목록에 **[🚫 1층 제외]** 칩 버튼 탑재.
   - 클릭 시 토글 선택 가능하며 다른 층수 칩(예: 남향 + 1층제외)과 조합 선택 가능.

2. **[Domain & Web DTO] DTO 확장 (`filters.py`, `home.py`)**
   - `ListingSearchFilter` DTO에 `exclude_first_floor: bool = False` (또는 `floors` 내 `'1층제외'`) 지원.

3. **[Application Service] 1층 정밀 제외 SQL 쿼리 빌더 (`listing_search_service.py`)**
   - 1층 제외 시 11층/21층/31층 등은 정상 노출되도록 정밀 조건문(SQL `not_()`) 적용:
     - `1층`, `1/x층`, `저/x층` 중 1층 명시 매물 제외.
     - DB 인덱스를 활용하여 0.01초 내에 1층 제외 조회가 처리되도록 쿼리 조작.

4. **[Tests] 1층 제외 단위 테스트 보강 (`test_floor_filter.py`)**
   - 1층 제외 필터링 및 11층 정상 유지 단위 테스트 작성.

---

## 2. 파일별 수정 계획

### [1] `src/realty_radar/domain/listing/filters.py`
- `exclude_first_floor: bool = False` 필드 추가.

### [2] `src/realty_radar/web/routes/home.py`
- `exclude_first_floor: bool = Query(False)` 파라미터 수신 및 DTO 할당.

### [3] `src/realty_radar/application/listing_search_service.py`
- 1층 제외 정밀 SQL `not_()` 필터링 조건문 빌딩.

### [4] `src/realty_radar/web/templates/listings/index.html`
- **[🚫 1층 제외]** 토글 칩 버튼 및 hidden input (`filter-exclude-first-floor`) UI 적용.

### [5] `tests/unit/test_floor_filter.py`
- 1층 제외 단위 테스트 작성.

---

## 3. 검증 계획
- pytest 및 gradle 검증 구동.
- 1층 제외 매물 필터링 및 11층 정상 노출 동작 확인.
