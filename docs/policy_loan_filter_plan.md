# 작업 계획 및 결과 보고서: 정책대출 적격 매물 전용 필터 추가

## 1. 개요
설정 화면에 입력된 사용자의 개인 조건(무주택, 연소득 등)에 맞춰 디딤돌 대출이나 버팀목 전세 대출을 실제로 받을 수 있는 적격 매물만 홈 화면 검색 결과에 필터링해 보여주는 고급 토글 기능을 추가합니다.

## 2. 상세 구현 내역

### ① 검색 필터 DTO 확장
- 위치: `src/realty_radar/domain/listing/filters.py`, `models.py`
- `ListingSearchFilter` / `ListingFilterParams` 에 `only_eligible_loans: bool = False` 속성 추가.

### ② 백엔드 쿼리 레벨 복합 필터링 적용
- 위치: `src/realty_radar/application/listing_search_service.py`
- `only_eligible_loans` 가 `True` 인 경우:
  - 무주택자가 아니면 빈 결과 즉시 반환.
  - 전용면적 85㎡ 이하 매물만 대상 지정.
  - 소득 한도에 따라 매매(디딤돌 - 일반 6000만, 신혼 8500만, 생초/다자녀 7000만 이하) 및 전월세(버팀목 - 일반 5000만, 신혼 7500만 이하) 중 적격한 상품군을 필터링.
  - 각 상품별 매매가(디딤돌 5억/6억 이하) 및 보증금(버팀목 3억/4억 이하) 한도를 SQL WHERE 조건절로 복합 매칭하여 페이징을 보존하며 고성능 검색 수행.

### ③ 프론트엔드 맞춤 조건 설정 UI 추가
- 위치: `src/realty_radar/web/templates/listings/index.html`
- "내 자격 조건으로 정책대출 가능한 매물만 보기" 체크박스(디자인 테마 적용) 추가.
- 체크 시 HTMX 필터 전송 연동 및 필터 초기화(`resetAllFilters`) 시 상태 초기화 대응.

## 3. 검증 결과
- **격리 검증 통합 테스트 통과**: [test_policy_loan_filter.py](file:///c:/workspace/personal/real-estate-search/tests/integration/test_policy_loan_filter.py) 통합 테스트를 작성하여 소득 및 주택 소유 여부에 따라 상품별 한도 이하 적격 매물만 철저하게 걸러지는지 검증.
- `pytest tests/unit tests/integration` 실행하여 총 43개 전체 테스트 100% 통과(`43 passed`).
