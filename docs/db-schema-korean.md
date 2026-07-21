# Realty Radar 한글 데이터베이스 스키마 명세서

이 문서는 Realty Radar 시스템에서 사용하는 클라우드 MySQL 데이터베이스의 7개 테이블과 각 컬럼별 한글 주석(Comment) 명세입니다.

---

## 1. `apartment_complex` (아파트 단지 마스터 테이블)
아파트 단지 공식 정보 및 위치/세대수/준공년도 마스터 데이터입니다.

| 컬럼명 (Column) | 데이터 타입 | 제약 조건 | 한글 설명 (Comment) |
|---|---|---|---|
| `id` | BIGINT | PK, Auto Inc | 아파트 단지 일련번호 (PK) |
| `complex_code` | VARCHAR(50) | Unique, Nullable | 공공데이터/포털 고유 단지 코드 |
| `official_name` | VARCHAR(100) | Not Null | 아파트 공식 단지명 (예: 여의도 시범아파트) |
| `normalized_name` | VARCHAR(100) | Not Null, Index | 검색 정규화 단지명 (특수문자/괄호 제거) |
| `sido` | VARCHAR(50) | Nullable | 시/도 (예: 서울특별시, 경기도) |
| `sigungu` | VARCHAR(50) | Nullable | 시/군/구 (예: 영등포구, 분당구) |
| `dong` | VARCHAR(50) | Nullable | 법정동/행정동 (예: 여의도동, 백현동) |
| `road_address` | VARCHAR(200) | Nullable | 도로명/지번 상세 주소 |
| `total_households` | INT | Nullable | 총 세대수 |
| `total_buildings` | INT | Nullable | 총 동수 |
| `construction_year` | INT | Nullable | 준공 연도 (예: 1971) |
| `use_approval_date` | VARCHAR(20) | Nullable | 사용승인일자 (YYYY-MM-DD) |
| `builder_name` | VARCHAR(100) | Nullable | 건설사/시공사명 |
| `heat_type` | VARCHAR(50) | Nullable | 난방 방식 (예: 지역난방, 개별난방) |
| `latitude` | DECIMAL(10, 7) | Nullable | 위도 좌표 (Latitude) |
| `longitude` | DECIMAL(10, 7) | Nullable | 경도 좌표 (Longitude) |
| `created_at` | DATETIME | Not Null | 단지 등록 일시 |
| `updated_at` | DATETIME | Not Null | 단지 수정 일시 |

---

## 2. `complex_alias` (단지명 매칭 & 별칭 관리 테이블)
수집된 매물의 다양한 원본 단지명과 아파트 단지 마스터 간의 매칭 이력을 저장합니다.

| 컬럼명 (Column) | 데이터 타입 | 제약 조건 | 한글 설명 (Comment) |
|---|---|---|---|
| `id` | BIGINT | PK, Auto Inc | 단지 별칭 일련번호 (PK) |
| `complex_id` | BIGINT | FK (apartment_complex) | 연결된 아파트 단지 ID |
| `source_id` | BIGINT | FK (crawl_source) | 수집 출처 사이트 ID |
| `alias_name` | VARCHAR(100) | Not Null | 수집된 원본 매물 단지명 |
| `normalized_alias` | VARCHAR(100) | Not Null, Index | 정규화된 단지 별칭 |
| `match_method` | VARCHAR(30) | Not Null | 매칭 연산 방식 (ADDRESS_EXACT, NAME_EXACT, FUZZY, MANUAL) |
| `match_confidence` | DECIMAL(5, 2) | Nullable | 매칭 신뢰도 점수 (0.00 ~ 99.99) |
| `manually_verified` | BOOLEAN | Not Null, Default 0 | 관리자 수동 검증 완료 여부 |
| `created_at` | DATETIME | Not Null | 별칭 매핑 등록 일시 |

---

## 3. `listing` (통합 매물 실시간 수집 마스터 테이블)
여러 출처에서 실시간 수집된 매물의 실효 상태, 가격, 면적 및 융자 상태 마스터입니다.

| 컬럼명 (Column) | 데이터 타입 | 제약 조건 | 한글 설명 (Comment) |
|---|---|---|---|
| `id` | BIGINT | PK, Auto Inc | 매물 일련번호 (PK) |
| `source_id` | BIGINT | FK (crawl_source) | 수집 출처 사이트 ID |
| `complex_id` | BIGINT | FK (apartment_complex) | 매칭된 아파트 단지 ID |
| `external_listing_id` | VARCHAR(100) | Not Null | 출처 사이트 원본 매물 ID |
| `canonical_group_id` | VARCHAR(100) | Nullable | 다중 사이트 중복 매물 추정 대표 그룹 ID |
| `source_url` | TEXT | Not Null | 원본 매물 상세 접속 URL |
| `complex_name_raw` | VARCHAR(100) | Not Null | 수집된 원본 아파트 단지명 |
| `address_raw` | VARCHAR(200) | Nullable | 수집된 원본 매물 주소 |
| `transaction_type` | VARCHAR(20) | Not Null | 거래 유형 (SALE: 매매, JEONSE: 전세, MONTHLY_RENT: 월세) |
| `price_deposit` | DECIMAL(15, 2) | Not Null | 매매가 또는 전월세 보증금 (단위: 원) |
| `price_monthly` | DECIMAL(15, 2) | Not Null, Default 0 | 월세액 (단위: 원, 매매/전세는 0) |
| `supply_area` | DECIMAL(8, 2) | Nullable | 공급면적 (단위: ㎡) |
| `exclusive_area` | DECIMAL(8, 2) | Nullable | 전용면적 (단위: ㎡) |
| `floor_info` | VARCHAR(50) | Nullable | 층수 정보 (예: 고/15층, 7/12층) |
| `mortgage_status` | VARCHAR(30) | Not Null | 융자 상태 (EXPLICIT_NONE, EXPLICIT_EXISTS, UNKNOWN) |
| `description_raw` | TEXT | Nullable | 수집된 원본 매물 상세 설명 문구 |
| `status` | VARCHAR(30) | Not Null | 매물 상태 (ACTIVE, STALE, REMOVED, SOLD_OR_CONTRACTED) |
| `first_seen_at` | DATETIME | Not Null | 최초 크롤링 발견 일시 |
| `last_seen_at` | DATETIME | Not Null | 최근 크롤링 확인 일시 |
| `stale_count` | INT | Not Null, Default 0 | 연속 미발견 누적 횟수 |
| `created_at` | DATETIME | Not Null | 매물 등록 일시 |
| `updated_at` | DATETIME | Not Null | 매물 수정 일시 |

---

## 4. `listing_history` (매물 변경 이력 및 추적 기록 테이블)
매물 가격 변동, 거래완료/상태 변경 및 동일 매물 추정 이력을 보관합니다.

| 컬럼명 (Column) | 데이터 타입 | 제약 조건 | 한글 설명 (Comment) |
|---|---|---|---|
| `id` | BIGINT | PK, Auto Inc | 이력 일련번호 (PK) |
| `listing_id` | BIGINT | FK (listing) | 연결된 매물 ID |
| `change_type` | VARCHAR(50) | Not Null | 변경 유형 (PRICE_CHANGE, STATUS_CHANGE, DEDUP_MATCH) |
| `prev_price_deposit` | DECIMAL(15, 2) | Nullable | 변경 전 보증금/매매가 |
| `new_price_deposit` | DECIMAL(15, 2) | Nullable | 변경 후 보증금/매매가 |
| `prev_status` | VARCHAR(30) | Nullable | 변경 전 매물 상태 |
| `new_status` | VARCHAR(30) | Nullable | 변경 후 매물 상태 |
| `note` | TEXT | Nullable | 이력 상세 비고/추정 정보 |
| `created_at` | DATETIME | Not Null | 이력 발생 일시 |

---

## 5. `crawl_source` (크롤링 대상 출처 사이트 관리 테이블)
크롤링 대상 외부 사이트 정보 및 요청 제한 속도를 관리합니다.

| 컬럼명 (Column) | 데이터 타입 | 제약 조건 | 한글 설명 (Comment) |
|---|---|---|---|
| `id` | BIGINT | PK, Auto Inc | 출처 일련번호 (PK) |
| `source_code` | VARCHAR(50) | Unique, Not Null | 출처 고유 코드 (SITE_A, SITE_B 등) |
| `source_name` | VARCHAR(100) | Not Null | 출처 사이트 이름 (예: 네이버부동산) |
| `base_url` | VARCHAR(255) | Not Null | 출처 사이트 기본 접속 URL |
| `rate_limit_ms` | INT | Not Null | 수집 요청 제한 간격 (밀리초 단위) |
| `is_active` | BOOLEAN | Not Null, Default 1 | 수집 활성화 여부 |
| `created_at` | DATETIME | Not Null | 등록 일시 |
| `updated_at` | DATETIME | Not Null | 수정 일시 |

---

## 6. `crawl_schedule` (크롤링 자동 스케줄 관리 테이블)
정기 수집 크론 주기를 관리합니다.

| 컬럼명 (Column) | 데이터 타입 | 제약 조건 | 한글 설명 (Comment) |
|---|---|---|---|
| `id` | BIGINT | PK, Auto Inc | 스케줄 일련번호 (PK) |
| `source_id` | BIGINT | FK (crawl_source) | 연결된 출처 사이트 ID |
| `target_region` | VARCHAR(100) | Not Null | 수집 대상 지역/키워드 |
| `cron_expression` | VARCHAR(50) | Not Null | 크론 주기 표현식 |
| `is_enabled` | BOOLEAN | Not Null, Default 1 | 스케줄 활성화 여부 |
| `last_run_at` | DATETIME | Nullable | 최근 실행 일시 |
| `next_run_at` | DATETIME | Nullable | 다음 실행 예정 일시 |
| `created_at` | DATETIME | Not Null | 스케줄 등록 일시 |
| `updated_at` | DATETIME | Not Null | 스케줄 수정 일시 |

---

## 7. `crawl_job` (크롤링 비동기 작업 큐 테이블)
Worker 프로세스가 Polling하여 처리하는 크롤링 단위 작업 큐입니다.

| 컬럼명 (Column) | 데이터 타입 | 제약 조건 | 한글 설명 (Comment) |
|---|---|---|---|
| `id` | BIGINT | PK, Auto Inc | 작업 일련번호 (PK) |
| `source_id` | BIGINT | FK (crawl_source) | 연결된 출처 사이트 ID |
| `schedule_id` | BIGINT | FK (crawl_schedule) | 연결된 스케줄 ID |
| `job_type` | VARCHAR(30) | Not Null | 작업 유형 (SEARCH, DETAIL 등) |
| `target_region` | VARCHAR(100) | Nullable | 수집 대상 지역명 |
| `target_url` | TEXT | Nullable | 수집 대상 상세 URL |
| `status` | VARCHAR(30) | Not Null | 작업 상태 (PENDING, RUNNING 등) |
| `priority` | INT | Not Null, Default 10 | 우선순위 |
| `retry_count` | INT | Not Null, Default 0 | 재시도 누적 횟수 |
| `max_retries` | INT | Not Null, Default 3 | 최대 재시도 가능 횟수 |
| `worker_id` | VARCHAR(100) | Nullable | 선점한 Worker 식별자 |
| `error_type` | VARCHAR(100) | Nullable | 오류 발생 예외 클래스명 |
| `error_message` | TEXT | Nullable | 오류 발생 상세 메시지 |
| `started_at` | DATETIME | Nullable | 작업 처리 시작 일시 |
| `finished_at` | DATETIME | Nullable | 작업 완료/실패 일시 |
| `created_at` | DATETIME | Not Null | 작업 생성 일시 |
| `updated_at` | DATETIME | Not Null | 작업 수정 일시 |
