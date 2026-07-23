# 초고속 DB 스키마 재설계 및 비동기 크롤링 극대화 계획서

## 1. 개요
데이터베이스 스키마 및 크롤링 파이프라인을 전면 재설계하여 데이터 조회 속도를 **1ms 미만(Sub-millisecond)**으로 단축하고, 수집/크롤링 속도를 **10배 이상 비동기 병렬 처리**합니다.

---

## 2. 세부 개편 방안

### 1) DB 스키마 재설계 (JOIN 0건 완전 제거 & 인덱스 최적화)
- **주소 분리 컬럼 탑재 (`sido`, `sigungu`)**:
  - `address_raw` 문자열 `LIKE` 검색을 없애고, 수집 시점에 `sido` (예: `"서울특별시"`), `sigungu` (예: `"송파구"`)로 즉시 정제하여 인덱스 컬럼으로 저장.
  - 검색 시 `Listing.sido == '서울특별시'` 형태의 **B-Tree Equal(=) 인덱스 검색**으로 1ms 미만 처리.
- **아파트 단지 정보 비정규화 (Denormalization)**:
  - `ApartmentComplex` 테이블 조인 오버헤드를 없애기 위해 `construction_year` (준공연도)와 `total_households` (세대수)를 `Listing` 마스터 테이블에 직접 보관.
  - 매물 검색 쿼리에서 **`JOIN` 문을 100% 완전 제거**하여 단일 테이블 쿼리로 조회의 극한 속도 달성.
- **슈퍼 복합 인덱스 (Super Composite Index)**:
  - `idx_super_search`: `(status, is_short_term, sido, sigungu, transaction_type, price_deposit)`
  - `idx_super_complex`: `(status, is_short_term, construction_year, total_households)`

### 2) 데이터 수집/크롤링 파이프라인 비동기 병렬화 (`asyncio.gather`)
- 기존 순차 HTTP 요청을 `httpx.AsyncClient` 동시성 파이프라인(Concurrency=20~50)으로 전환하여 **수집 속도 10배 이상 향상**.
- 수집 데이터 DB 저장 시 배치 단위 `bulk_insert_mappings` 및 초고속 Upsert 구동.

---

## 3. 검증 계획
1. 마이그레이션 스크립트로 전체 DB 스키마 및 기존 14만~50만 건 데이터 재정제 적용.
2. 필터 변경 쿼리 속도 측정 (1ms 미만 확인).
3. pytest 51개 전체 유닛/통합 테스트 구동 및 100% 통과 확인.
