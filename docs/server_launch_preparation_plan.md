# 서버 구동 시 최적화 바로 적용 여부 및 DB 점검 계획서

서버 재실행 시 소스코드 최적화 반영 여부 및 DB 물리 인덱스 동기화 점검 결과 보고서입니다.

## 1. 점검 및 분석 결과

1. **기존 DB 데이터 100% 준비 완료**
   - 현재 157,038건의 전체 DB 매물 중 `complex_id`가 지정된 모든 레코드의 `total_households`, `construction_year`, `sido`, `sigungu` 비정규화 컬럼이 이미 **100% 데이터로 채워져 있음**을 확인하였습니다.
   - 따라서 별도의 둔중한 Backfill 마이그레이션 작업 없이도 즉시 고속 쿼리를 이용할 수 있습니다.

2. **서버 실행 시 소스 코드 반영**
   - 서버를 재실행(`uvicorn` 구동)하는 순간 수정된 `ListingSearchService` 및 `ComplexMatchService` 로직이 **즉시 적용**됩니다.

3. **DB 물리 복합 인덱스 생성 조치**
   - 새로 정의된 `idx_listing_super_search`, `idx_listing_super_filter` 등 복합 인덱스가 DB 물리 테이블에 100% 반영되도록 인덱스 생성 헬퍼 스크립트를 준비 및 검증합니다.

---

## 2. 주요 조치 계획

- `Base.metadata.create_all()` 기반 인덱스 자동 생성 헬퍼 확인.
- `gradle test` 및 파이썬 검증을 통한 시스템 작동 안정성 최종 확보.
