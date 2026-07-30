# 역 도보 0분 데이터 원인 분석 및 정제/수정 계획

## 1. 원인 분석 결과 (Root Cause Analysis)

### 조사 질문에 대한 답변
- **질문**: 현재 DB 수집 로직 문제인가, 네이버 부동산 원본 데이터 표기 문제인가?
- **답변**: **두 요인이 결합된 현상**입니다.
  1. **네이버 부동산 API 표기 방식**: 네이버 부동산 상세 API(`articleDetail`)는 주변에 지하철역이 아예 없는 매물(예: 인천 강화도, 용인 기흥 상하동 등)이나 역 정보 미입력 매물에 대해 필드 생략이 아니라 **`"walkingTimeToNearSubway": 0` (숫자 0)**으로 반환합니다.
  2. **DB 수집 파서 로직**: `mortgage_enrichment_service.py`의 `parse_article_detail` 및 `_unsigned_int` 함수가 숫자 `0`을 유효한 값으로 판단하여 DB `nearest_subway_walk_minutes` 컬럼에 `0` (역 도보 0분 = 초역세권)으로 그대로 저장하였습니다.
  3. **검색 필터 동작**: 역 도보 상한 15분 이하 필터링(`nearest_subway_walk_minutes <= 15`) 적용 시, `0`으로 잘못 저장된 약 10,700여 건의 '역 없는 매물'이 초역세권 매물로 오인되어 대량 검색되는 현상이 발생했습니다.

---

## 2. 해결 방안 (Resolution Plan)

### A. 파서 로직 정규화 (`src/realty_radar/application/mortgage_enrichment_service.py`)
- `nearest_subway_walk_minutes` 파싱 시 값이 `0` 이하일 경우 "역 정보 없음(None/Null)"으로 처리되도록 수정 (`0`은 유효한 도보 분 수에서 제외).

### B. 기존 DB 데이터 클리닝 (Migration Script)
- 이미 DB(`listing_current`)에 `nearest_subway_walk_minutes = 0`으로 저장된 10,701건의 데이터를 `NULL`로 일괄 업데이트.

### C. 검색 필터 이중 보호 (`src/realty_radar/application/listing_search_service.py`)
- `max_subway_walk_minutes` 쿼리 조건 생성 시 `nearest_subway_walk_minutes > 0` 조건도 함께 지정하여 0분 데이터 오노출을 이중 방어.

---

## 3. 검증 계획
1. 파서 단위 테스트 추가 (`tests/unit/test_mortgage_enrichment.py`).
2. 마이그레이션 실행 후 DB 0분 데이터 0건 확인.
3. 전체 pytest 스위트 실행 (`python -m pytest`).
