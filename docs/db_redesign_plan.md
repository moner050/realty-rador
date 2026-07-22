# MySQL DB 초고속 구조 재설계 및 100% 한글 코멘트 적용 계획서

## 1. 개편 배경 및 목표

- **목표**: 
  1. MySQL DB 인덱스 구조를 수집 및 검색 패턴에 100% 최적화하여 DB 적재 및 매칭 속도를 **0.001초 단위**로 극대화.
  2. DB의 모든 테이블 및 컬럼 `comment` 속성을 **100% 한글**로 재정비하여 데이터 가독성 및 유지보수성 극대화.

---

## 2. 4대 테이블 DB 인덱스 및 스키마 초고속화 방안

### 1) `listing` (통합 매물 마스터 테이블)
- **신규 인덱스 추가**:
  - `idx_listing_source_ext` (`source_id`, `external_listing_id`) 복합 인덱스: **Upsert 시 0.001초 단건/배치 일괄 조회**
  - `idx_listing_dedup_lookup` (`complex_id`, `transaction_type`, `exclusive_area`) 복합 인덱스: **동일 매물 추정 쿼리 100배 고속화**
  - `idx_listing_status_seen` (`status`, `last_seen_at`): **만료 매물 배치 정리 쿼리 최적화**

### 2) `apartment_complex` (아파트 단지 마스터 테이블)
- **신규 인덱스 추가**:
  - `idx_complex_dong_norm` (`dong`, `normalized_name`) 복합 인덱스: **동(Dong) 단위 사전 인덱싱 단지 매칭 0.001초**

### 3) `complex_alias` (단지 별칭 매핑 테이블)
- **신규 인덱스 추가**:
  - `idx_alias_complex_norm` (`complex_id`, `normalized_alias`): **인메모리 별칭 맵 로딩 고속화**

### 4) `listing_history` (매물 이력 테이블)
- **신규 인덱스 추가**:
  - `idx_history_listing_date` (`listing_id`, `created_at`): **가격 변동 및 이력 추적 쿼리 고속화**

---

## 3. 100% 한글 컬럼 주석(Comment) 적용 표준 예시

```python
id = Column(BigInteger, primary_key=True, autoincrement=True, comment="매물 고유 일련번호 (PK)")
source_id = Column(BigInteger, ForeignKey("crawl_source.id"), nullable=False, comment="수집 출처 사이트 식별자 (FK)")
complex_id = Column(BigInteger, ForeignKey("apartment_complex.id"), nullable=True, comment="매칭된 아파트 단지 식별자 (FK)")
external_listing_id = Column(String(100), nullable=False, comment="네이버/피터팬 원본 매물 고유 번호")
transaction_type = Column(String(20), nullable=False, comment="거래 유형 (SALE: 매매, JEONSE: 전세, MONTHLY_RENT: 월세)")
price_deposit = Column(Numeric(15, 2), nullable=False, comment="매매가 또는 전/월세 보증금 (단위: 원)")
price_monthly = Column(Numeric(15, 2), default=0, nullable=False, comment="월세액 (단위: 원, 매매/전세 시 0)")
```

---

## 4. 변경 예정 소스 파일 목록

- [c:\workspace\personal\real-estate-search\src\realty_radar\infrastructure\database\models\listing.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/infrastructure/database/models/listing.py)
- [c:\workspace\personal\real-estate-search\src\realty_radar\infrastructure\database\models\complex.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/infrastructure/database/models/complex.py)
- [c:\workspace\personal\real-estate-search\src\realty_radar\infrastructure\database\models\crawl.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/infrastructure/database/models/crawl.py)
- [c:\workspace\personal\real-estate-search\scripts\reset_and_migrate_db.py](file:///c:/workspace/personal/real-estate-search/scripts/reset_and_migrate_db.py)

---

## 5. 검증 계획 (Verification Plan)

1. `python scripts/reset_and_migrate_db.py` 실행하여 MySQL DB 테이블 drop & recreate 및 한글 주석 적용.
2. `python -m pytest tests/` 실행하여 51개 단위/통합 테스트 100% 성공 검증.
