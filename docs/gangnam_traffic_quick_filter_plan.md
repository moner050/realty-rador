# 강남역 통근시간 보정 및 퀵 필터 3종 추가 구현 계획서

## 1. 개요
`docs/gangnam_traffic.md`에서 재검증된 수도권 시·군·구별 강남역 대중교통 통근 소요시간을 `GANGNAM_COMMUTE_MINUTES_MAP`에 정확히 반영하고, 웹 UI 검색 폼의 퀵 필터 탭에 **"강남 30분 이내"**, **"강남 1시간 이내"**, **"강남 1시간 30분 이내"** 3가지 원클릭 퀵 필터 버튼을 추가합니다.

## 2. 작업 계획
1. `src/realty_radar/domain/listing/commute_map.py` 업데이트
   - `docs/gangnam_traffic.md` 재검증 기준에 맞춰 강남 30분 이내, 60분 이내, 90분 이내 시군구 소요시간 보정
2. `src/realty_radar/web/templates/listings/index.html` 업데이트
   - 퀵 필터 탭에 30분 이내, 1시간 이내, 1시간 30분 이내 3개 버튼 추가
3. `tests/test_commute_and_region_filter.py` 테스트 코드 업데이트 및 `gradle test` 검증
