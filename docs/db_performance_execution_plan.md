# DB 성능 최적화 (1단계, 3단계, 5단계) 구현 계획서

2단계(Redis 캐싱) 및 4단계(전문검색)를 제외하고 1단계, 3단계, 5단계 최적화를 데이터베이스 모델, 수집 서비스, 및 검색 서비스에 정밀 적용하는 구현 계획서입니다.

---

## 1. 개요 및 구현 목표

1. **복합 인덱스(Composite Index) 추가 (1단계)**
   - `Listing` 모델에 동적 조회 및 정렬용 Multi-Column Index 추가 (`idx_listing_active_search`, `idx_listing_recent_sort`, `idx_listing_households_sort` 등).
2. **반정규화 및 JOIN 100% 제거 (3단계)**
   - `Listing` 모델 내 `total_households`, `construction_year`, `sido`, `sigungu` 반정규화 필드를 100% 활용하여 `ApartmentComplex`와의 불필요한 `LEFT OUTER JOIN` 제거.
   - `ListingUpsertService`에서 단지 연동 시 반정규화 필드가 누락 없이 동기화되도록 보완.
3. **SQL 레벨 단지 그룹핑 및 페이징 전환 (5단계)**
   - `group_by_complex=True` 모드 시 파이썬 전역 메모리 로드 방식을 SQL 레벨 그룹핑(`GROUP BY` & Aggregation) 기반 단지 페이징 구조로 완전 전환하여 속도 단축 및 메모리 절감.

---

## 2. 파일별 수정 계획

### [1] `src/realty_radar/infrastructure/database/models/listing.py`
- SQLAlchemy `__table_args__`에 복합 인덱스(`Index`) 등록.

### [2] `src/realty_radar/application/listing_upsert_service.py`
- 단지 매핑 시 `Listing` 반정규화 필드(`total_households`, `construction_year`, `sido`, `sigungu`) 자동 동기화 보장.

### [3] `src/realty_radar/application/listing_search_service.py`
- 시/도, 시/군/구, 세대수, 준공연도 조건 및 정렬 시 `ApartmentComplex` JOIN 제거 -> 단일 `Listing` 테이블 쿼리로 슬림화.
- `group_by_complex=True` 시 SQL 레벨 그룹 집계 및 페이징 구조 적용.

---

## 3. 검증 계획
- pytest 및 gradle 검증 수행.
- 복합 인덱스 생성 및 쿼리 실행 속도, JOIN 제거 쿼리 통과 확인, `group_by_complex` 결과 검증.
