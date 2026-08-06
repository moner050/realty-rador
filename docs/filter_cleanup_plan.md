# 실구매 가능 매물 필터 제거 작업 계획서 (filter_cleanup_plan.md)

## 1. 목적
자금 조건 그룹의 **"가능대출 매물만"**과 **"실구매 가능 매물만"** 필터 간의 사용자 인식 모호성을 해소하기 위해 **"실구매 가능 매물만" (`only_purchase_affordable`)** 필터를 삭제하고 **"가능대출 매물만"**으로 통합 정리함.

## 2. 세부 변경 파일
1. `src/realty_radar/web/templates/listings/index.html`: UI 체크박스 삭제.
2. `src/realty_radar/web/templates/listings/_search_result_summary.html`: 필터 요약 칩 제거.
3. `src/realty_radar/domain/listing/filters.py`: `ListingSearchFilter` 데이터 클래스 수정.
4. `src/realty_radar/web/routes/home.py`: 쿼리 파라미터 및 렌더링 로직 수정.
5. `src/realty_radar/application/listing_search_service.py`: 검색 필터링 로직 수정.
6. `tests/`: 관련 테스트 코드 수정.
