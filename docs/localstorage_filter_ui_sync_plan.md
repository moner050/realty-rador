# 필터링 상태 로컬스토리지 및 UI 요소 완벽 동기화 구현 계획서

이전 필터링 조건 적용 시 UI 상(슬라이더, 라벨 텍스트, 뱃지)에 반영되지 않던 문제를 해결하고, 로컬스토리지 복원 시 화면 표기가 100% 일치하도록 보완하는 계획입니다.

## 1. 원인 분석

1. **로컬스토리지 복원 시 `range` 슬라이더 및 라벨 미동기화**
   - `loadFiltersFromLocalStorage()`가 실행될 때 `filter-max-price`, `filter-min-area` 등 hidden input의 값은 채워졌으나, 사용자가 눈으로 보는 range 슬라이더(`filter-*-range`) 및 뱃지 라벨(`label-*`)이 업데이트되지 않아 화면상에는 필터가 적용되지 않은 것처럼 보렸습니다.

2. **초기 로딩 시 슬라이더 & 라벨 동기화 호출 부재**
   - Jinja2 템플릿 렌더링 후 JS `DOMContentLoaded` 시점에 hidden input의 실제 값과 range 슬라이더 및 라벨 텍스트 간의 상호 동기화 함수가 명시적으로 실행되지 않았습니다.

---

## 2. 주요 수정 계획

### [Frontend] `src/realty_radar/web/templates/listings/index.html`
- **`loadFiltersFromLocalStorage()` 보완**:
  - `max_price`, `min_exclusive_area`, `min_construction_year`, `min_households` 복원 시 폼 hidden input뿐만 아니라 `range` 슬라이더의 `value`를 세팅하고 라벨 갱신 함수(`updatePriceLabel`, `updateAreaLabel`, `updateYearLabel`, `updateHouseholdsLabel`)를 즉시 호출.
  - `transaction_type` 복원 시 `setTransactionType(val)`을 호출하여 버튼 UI 하이라이트 동기화.
- **`DOMContentLoaded` 동기화 로직 전면 개선**:
  - 로컬스토리지 복원 후 hidden input에 저장된 최신 필터 값을 기반으로 range 슬라이더, 뱃지 라벨, 그리고 고급 필터 요약 바(`filter-summary-text`)가 일관성 있게 표기되도록 수정.

---

## 3. 검증 계획
- pytest 및 gradle 검증 수행.
- 로컬스토리지 저장 값 변경 및 페이지 새로고침 시 슬라이더 위치, 라벨 텍스트, 요약 텍스트의 동기화 여부 확인.
