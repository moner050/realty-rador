# 주거 스펙 방향 다중 선택 필터 복원 계획서 (direction_multi_select_filter_plan.md)

## 1. 개요
매물검색 상세 필터 모달의 `주거 스펙` 탭에 DB 매핑 기준 8종 방향(남향, 남동향, 동향, 북동향, 북향, 북서향, 서향, 남서향) 다중 선택 필터를 추가함.

## 2. 변경 파일
- `src/realty_radar/web/templates/listings/index.html`: `filter-tab-content-housing` 내 방향 8종 체크박스 칩 그리드 배치.
