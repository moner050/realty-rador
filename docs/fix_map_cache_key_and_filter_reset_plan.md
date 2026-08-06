# 지도 캐시 키 필터 파라미터 미반영 및 초기화 갱신 완벽 조치 계획서 (fix_map_cache_key_and_filter_reset_plan.md)

## 1. 개요
MapViewportCache 키에 필터 파라미터가 빠져 무필터 캐시가 리턴되던 결정적 원인을 수정하고, 탭 초기화 폼 갱신을 보강함.

## 2. 변경 파일
- `src/realty_radar/application/listing_map_service.py`: cache_key 필터 해시 통합.
- `src/realty_radar/web/templates/listings/index.html`: data-clear-filter-tab 폼 제출 연동.
- `src/realty_radar/web/static/listing-filter-panel.js`: 현재 탭 초기화 및 해제 동작 강화.
