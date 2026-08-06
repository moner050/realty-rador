# 필터 모달 높이 수축 방지 및 방향 필터 적용 계획서 (fix_modal_height_and_direction_filter_plan.md)

## 1. 개요
모달 바디 레이아웃 고정으로 탭/방향 선택 시 높이 찌그러짐 현상을 방지하고, 방향 선택(direction_codes) 및 옵션 파라미터를 메인 검색 폼 및 지도로 정확히 전달함.

## 2. 변경 파일
- `src/realty_radar/web/templates/listings/index.html`: 모달 높이 고정 및 인풋 form 바인딩 보강.
- `src/realty_radar/web/static/listing-map.js`: 다중 파라미터 URL 병합 보강.
