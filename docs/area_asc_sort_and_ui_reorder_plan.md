# 면적 좁은순 정렬 추가 및 정렬 UI 순서 변경 구현 계획서

신규 정렬 옵션인 '면적 좁은순(`area_asc`)'을 추가하고, 정렬 UI 셀렉트 박스에서 '최신 발견순' 옵션을 맨 아래로 배치하는 구현 계획서입니다.

---

## 1. 주요 변경 요구사항

1. **'면적 좁은순' (`area_asc`) 정렬 옵션 신규 추가**
   - `SortBy` enum 상수에 `AREA_ASC = "area_asc"` 등록.
   - `ListingSearchService`에서 SQL 및 그룹 정렬 로직에 `Listing.exclusive_area.asc()` 처리 반영.

2. **정렬 UI 셀렉트 박스 순서 재배치 (`list_partial.html`)**
   - '최신 발견순' 옵션을 드롭다운의 **맨 아래(7번째)** 로 이동.
   - 구성 순서:
     1. 가격 낮은순 (`price_asc`) - 기본값
     2. 가격 높은순 (`price_desc`)
     3. 면적 넓은순 (`area_desc`)
     4. 면적 좁은순 (`area_asc`) **[신규]**
     5. 세대 많은순 (`households_desc`)
     6. 세대 적은순 (`households_asc`)
     7. 최신 발견순 (`recent`) **[맨 아래]**

---

## 2. 파일별 수정 계획

### [1] `src/realty_radar/constants.py`
- `SortBy` enum 클래스에 `AREA_ASC = "area_asc"` 추가.

### [2] `src/realty_radar/application/listing_search_service.py`
- `sort_by_val == "area_asc"` 처리 추가:
  - SQL: `stmt.order_by(Listing.exclusive_area.is_(None).asc(), Listing.exclusive_area.asc())`
  - Group Sort: `all_grouped_items.sort(key=lambda g: min([_get_area(l) ...]))`

### [3] `src/realty_radar/web/templates/listings/list_partial.html`
- 정렬 셀렉트 박스 `<option>` 목록 순서 변경 및 `area_asc` 추가.

---

## 3. 검증 계획
- pytest 및 gradle 검증 수행.
- `area_asc` 정렬 적용 시 면적이 작은 매물부터 오름차순 출력 여부 및 UI 순서 변경 검증.
