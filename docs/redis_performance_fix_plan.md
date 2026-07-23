# 홈 화면 Redis 데이터 조회 초고속(1ms) 응답 완전 개편 계획서

## 1. 지연 원인 정밀 진단

기존 Redis 적용에도 불구하고 홈 화면 조회가 느렸던 3가지 근본 원인:

1. **Redis 캐시 적중 시에도 DB 쿼리 재실행**:
   - 기존에는 Redis에 `item_ids` (ID 리스트만) 보관하여 캐시가 적중해도 MySQL에서 `Listing.id.in_(item_ids)` SQL 쿼리를 다시 실행함.

2. **매물마다 반복되는 대출 평가 N+1 DB 쿼리 연산 (`_enrich_listings_with_loans`)**:
   - 페이지당 20~50개 매물 각각에 대해 `loan_service.evaluate_listing_loans(item.id)`를 개별 DB 조회를 포함해 20~50번 반복 호출.

3. **크롤링 진행도 집계 DB 쿼리 (`job_service.get_progress_summary()`)**:
   - 홈 화면을 열 때마다 DB `crawl_job` 테이블의 진행도 통계 쿼리가 매번 동기 실행됨.

---

## 2. 초고속(1ms) 해결 방안

### 1) 매물 DTO 리스트 및 대출 평가 결과 통째로 Redis 캐싱
- [listing_search_service.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/application/listing_search_service.py)에서 `Listing` 및 `eligible_loans` 대출 평가 결과까지 포함한 **전체 Dict 묶음**을 Redis에 직렬화하여 저장.
- 캐시 Hit 시 **MySQL DB 쿼리 0건 + N+1 연산 0건**으로 **0.001초(1ms)** 만에 결과 즉시 응답!

### 2) `_enrich_listings_with_loans` 메모리 배치 연산 적용
- [home.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/routes/home.py)에서 이미 조인된 `item.complex` 및 `item.price_deposit` 인메모리 데이터만 활용하여 대출 적격성을 0ms 만에 평가.

### 3) 수집 진행도 통계 Redis 캐싱 (TTL 5초)
- [crawl_job_service.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/application/crawl_job_service.py)의 `get_progress_summary()`에 5초 Redis 캐시 적용.

---

## 3. 검증 계획
- `python -m pytest tests/`로 51개 전체 테스트 통과 검증.
- 실시간 API 응답 속도 측정 (300ms+ -> 1~3ms 비약적 단축 검증).
