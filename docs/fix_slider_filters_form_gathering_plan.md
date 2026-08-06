# 슬라이더 필터 파라미터 수집 및 연동 계획서 (fix_slider_filters_form_gathering_plan.md)

## 1. 개요
detailed-filter-modal 내 슬라이더(가격, 전용면적, 준공년도, 세대수 등) 인풋들이 requestUrl() 및 폼 데이터 수집에서 누락되던 문제를 수집기 통합으로 완벽 수정함.

## 2. 변경 파일
- `src/realty_radar/web/static/listing-map.js`: 모달 내부 인풋 통합 수집기 적용.
- `src/realty_radar/web/templates/listings/index.html`: 슬라이더 및 인풋 form="listing-search-form" 보강.
