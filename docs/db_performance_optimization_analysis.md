# RDB 데이터 조회 및 필터링 성능 최적화 분석 보고서

현재 157,000건 이상의 매물 데이터셋을 기준으로 RDB 기반 조회 및 필터링 속도를 단축하고 시스템 응답성을 극대화하기 위한 구조적 성능 최적화 분석 보고서입니다.

---

## 1. 현재 구조의 주요 성능 병목 요인 (Bottlenecks)

1. **`LIKE '%키워드%'` 부분 문자열 검색으로 인한 Full Table Scan**
   - `address_raw.like('%강남구%')`, `complex_name_raw.ilike('%래미안%')` 형태의 와일드카드 검색은 B-Tree 인덱스를 사용할 수 없어 15만 건 데이터 전체를 전수 스캔(Full Table Scan)하게 됩니다.

2. **`group_by_complex` 모드에서의 전역 데이터 인메모리 파싱**
   - 아파트 단지별 묶어보기 모드 시, DB에서 필터링된 전체 매물(수천~수만 건)을 파이썬 메모리로 한 번에 로드한 후 Dict 및 Lambda 정렬을 수행하여 CPU 및 메모리 오버헤드가 발생합니다.

3. **Multi-Column 복합 인덱스(Composite Index) 및 커버링 인덱스 부재**
   - `status`, `is_short_term`, `sido`, `sigungu`, `transaction_type`, `price_deposit` 등 동시에 자주 필터링되는 조건 조합에 대한 커버링 인덱스가 최적화되어 있지 않습니다.

4. **단지 정보(ApartmentComplex)와의 JOIN 오버헤드**
   - 매물 검색 시 세대수/준공연도 정렬 또는 지역 조회를 위해 `Listing`과 `ApartmentComplex` 간의 `LEFT OUTER JOIN`이 매번 실행됩니다.

---

## 2. 속도 향상을 위한 핵심 최적화 방안 5가지

### 🚀 1 단계: DB 복합 인덱스(Composite Index) 및 Covering Index 최적화 (즉시 적용 가능)
- **적용 방안**: 자주 사용되는 필터 파라미터 조합에 대해 Multi-Column Index 구축.
  - `idx_listing_active_search`: `(status, is_short_term, sido, sigungu, transaction_type, price_deposit)`
  - `idx_listing_sort_recent`: `(status, is_short_term, first_seen_at DESC)`
- **기대 효과**: DB 쿼리 실행 시간 80% 이상 감소 (Index Scan으로 전환).

### ⚡ 2 단계: Redis 기반 검색 결과 2계층 캐싱 (Two-Tier Caching)
- **적용 방안**:
  - **Filter Hash Key**: 검색 필터 DTO의 SHA256 해시값을 Key로 지정 (예: `cache:search:<hash_key>`).
  - **TTL 적용**: 수집 주기에 맞춘 short-TTL (예: 5분~10분) 적용 또는 데이터 수집(Crawl Upsert) 완료 시 관련 캐시 스마트 무효화(Invalidation).
- **기대 효과**: 동일/유사 조건 검색 시 DB 접근 없이 **1ms~3ms 이내 Super-fast 응답**.

### 🏛️ 3 단계: RDB 반정규화 (Denormalization) 및 JOIN 완전 제거
- **적용 방안**:
  - `Listing` 테이블에 `ApartmentComplex`의 `total_households`, `construction_year`, `sido`, `sigungu` 필드를 수집/Upsert 시점에 100% 반정규화하여 사전 포함.
- **기대 효과**: `Listing` 단일 테이블 조회만으로 필터링 및 정렬을 완수하여 `JOIN` 쿼리 100% 제거.

### 🔍 4 단계: MySQL Full-Text Search (N-gram Parser) 또는 전문 검색엔진 도입
- **적용 방안**:
  - **RDB 레벨**: MySQL `FULLTEXT INDEX` + `ngram` 파서 적용 (`MATCH(complex_name_raw, address_raw) AGAINST(...)`).
  - **외부 검색엔진 레벨**: `Elasticsearch` / `Meilisearch` 도입하여 15만 건 텍스트 인덱싱.
- **기대 효과**: 부분 단어 검색(`'래미안'`, `'반포'`) 속도가 100ms 이상에서 5ms 이내로 단축.

### 📊 5 단계: `group_by_complex` SQL 레벨 집계 및 SQL Window Function 전환
- **적용 방안**:
  - 파이썬 인메모리 그룹핑 대신 SQL `GROUP BY complex_id, complex_name_raw` 및 `ROW_NUMBER() OVER (PARTITION BY ...)` 위임.
- **기대 효과**: 서버 메모리 사용량 90% 절감 및 DB 페이징 속도 급증.

---

## 3. 실행 로드맵 및 단계별 계획
- **단기 (1단계)**: DB 최적 복합 인덱스 및 반정규화 정리.
- **중기 (2단계)**: Redis Caching Layer 결합.
- **장기 (3단계)**: MySQL Full-Text Index 또는 Meilisearch 검색 엔진 도입.
