# 전체 적용 필터 완벽 접기/펴기 및 툴바 제거 계획서 (applied_filters_full_collapse_plan.md)

## 1. 개요
`검색 결과 (20개씩 보기)` 툴바 칩을 완전 제거하고, `_search_result_summary.html`의 모든 필터 뱃지와 `적용 지역:` 칩 영역을 단일 Alpine 토글 컨테이너로 감싸 접었을 때 하위 필터 뱃지가 완전히 싹 감춰지도록 보완함.

## 2. 변경 파일
- `src/realty_radar/web/templates/listings/_search_result_summary.html`: `id="search-status"` 툴바 삭제.
- `src/realty_radar/web/templates/listings/index.html`: `_search_result_summary.html` 위치를 `x-show="showAppliedFilters"` 토글 컨테이너 안으로 통째 이동.
