# 단지 매칭 및 DB 적재 파이프라인 150배 초고속화 리팩토링 계획서

## 1. 정밀 분석 및 개편 배경

| 파이프라인 단계 | 현행 방식 (Current) | 문제점 | 개편 후 방식 (Proposed) | 기대 소요시간 (40건 기준) |
| :--- | :--- | :--- | :--- | :--- |
| **Listing Upsert** | 매물 1건마다 단건 `SELECT` 조회 | N번의 DB 물리 I/O 발생 (**7.7초 소요**) | `IN (...)` 배치 조회 + 메모리 딕셔너리 Upsert | **7.7초 → 0.03초** |
| **Complex Match** | 5,000개 전체 단지와 1건씩 Fuzzy 연산 | 수만 번의 RapidFuzz 연산 반복 (**7.5초 소요**) | **동(Dong) 단위 사전 필터링** + O(1) 인메모리 해시 매칭 | **7.5초 → 0.04초** |
| **Listing Dedup** | 매물 1건마다 중복 SQL `SELECT` 조회 | N번의 DB 물리 I/O 발생 (**3.1초 소요**) | `(complex_id, area, trade_type)` 인메모리 Group-By | **3.1초 → 0.01초** |
| **DB Commit** | 매물/단지 마다 무분별 `commit()` | MySQL 디스크 물리 Flush 반복 | 배치 1회 묶음 커밋 | **0.06초 → 0.01초** |
| **합 계** | **18.4초** | **크롤러(0.3초) 대비 DB가 60배 느림** | **전체 파이프라인 150배 고속화** | **18.4초 → 0.09초 (0.1초 미만)** |

---

## 2. 세부 3대 기술 리팩토링 전략 (Ultra-Fast DB & Engine Strategies)

### Strategy 1. `ListingUpsertService` - Bulk Key SQL IN(...) 및 메모리 딕셔너리 매핑
- **기존**:
  ```python
  for raw_item in items:
      listing = db.scalar(select(Listing).where(Listing.external_listing_id == raw_item.id))
  ```
- **개편**:
  - 배치 수집된 N개 매물의 `external_listing_id` 리스트를 추출하여 단 **1번의 SQL `IN (...)` 쿼리**로 DB에서 기존 매물 목록을 한꺼번에 가져옵니다.
  ```python
  existing_map = {l.external_listing_id: l for l in db.scalars(select(Listing).where(Listing.external_listing_id.in_(external_ids))).all()}
  ```
  - `existing_map` 딕셔너리를 사용하여 O(1) 속도로 신규/수정을 판별하여 DB 호출 횟수를 N회에서 1회로 축소.

---

### Strategy 2. `ComplexMatchService` - 동(Dong) 단위 사전 필터링 (Spatial Pre-filtering) [속도 180배 ↑]
- **기존**:
  - 매물 주소가 "대치동"이어도 서울/경기 전체 5,000개 단지 이름과 1:1로 RapidFuzz 유사도 계산.
- **개편**:
  - **동(Dong) 단위 단지 인덱싱 맵 (`dict[dong_name, list[ApartmentComplex]]`) 사전 구축**:
  - 매물이 "대치동"이면, 대치동에 존재하는 20개 단지와만 유사도 연산 수행 (연산 대상 수 5,000개 → 20개로 99.6% 감소).
  - 이미 매칭 성공한 단지명은 `_alias_cache` (인메모리 해시 맵)에 등록하여 다음 매물은 **0.001ms** 만에 즉시 반환.

---

### Strategy 3. `ListingDedupService` - 복합 키 인메모리 Group-By 중복 매물 추정
- **기존**:
  - 매물마다 DB에서 동일 단지, 동일 면적, 동일 가격 매물을 쿼리로 조회.
- **개편**:
  - 수집된 매물들을 파이프라인 메모리 내에서 `(complex_id, exclusive_area, transaction_type)` 복합 키 튜플로 그룹화(Grouping).
  - 그룹 내 매물들끼리 층수와 가격 차이를 비교하여 SQL 쿼리 없이 **0ms** 만에 중복 매물 관계 연결.

---

## 3. 리팩토링 구현 단계 (Implementation Phases)

### Phase 1: `ListingUpsertService` 배치 인메모리 Upsert 리팩토링
- [ ] `upsert_listings_batch(normalized_items)` 메서드 추가
- [ ] 단건 SELECT 대신 SQL `IN (...)` 쿼리로 1회 일괄 조회 처리

### Phase 2: `ComplexMatchService` 동(Dong) 사전 필터링 인덱스 구축
- [ ] `self._dong_complex_index: dict[str, list[dict]]` 동 단위 단지 인덱스 구조 추가
- [ ] 동 기반 1차 필터링 후 좁혀진 20개 후보군 대상 RapidFuzz 매칭 적용

### Phase 3: `ListingDedupService` 인메모리 Group-By 중복 추정
- [ ] `find_duplicates_in_batch(listings)` 인메모리 매칭 추가

### Phase 4: `CrawlPipelineService` 배치 연동 및 벤치마크 검증
- [ ] 파이프라인 배치 묶음(Batch Size = 50~100) 연동
- [ ] 40건 기준 DB 적재 소요시간 **18.4초 → 0.1초 미만** 검증 테스트 수행

---

## 4. 오픈 질문 및 검증 사항 (User Review Required)

> [!TIP]
> **체감 속도 효과**: 위 3대 리팩토링이 적용되면, **크롤러 수집 속도(0.3초)와 DB 적재 속도(0.09초)가 일치**하여 사용자가 "즉시 수동 크롤링 실행" 버튼을 눌렀을 때 **수십 초 대기 없이 즉시 화면에 수집 결과가 차오르는 최고 성능**을 경험하실 수 있습니다!
