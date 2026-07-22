# 작업 계획서: 정책대출 적격 뱃지 표기 및 금액 실시간 콤마 포맷팅

## 1. 개요
1. 개인 자격 및 조건 설정(`/settings`)에 따라 매물 검색 목록의 각 아파트 매물 카드에 이용 가능한 **정책대출 뱃지("디딤돌 대출 가능", "버팀목 대출 가능")**를 표시합니다.
2. 금액 표기 시 가독성을 위한 천 단위 콤마(`,`)를 적용하고, 사용자가 입력 필드에 금액을 작성할 때 **실시간으로 콤마가 자동 채워지도록** UI를 개선합니다.

## 2. 상세 구현 계획

### 2.1 매물 카드 정책대출 적격 평가 연동
- 위치: `src/realty_radar/web/routes/home.py`, `list_partial.html`
- `home.py`: 매물 검색 시 `session_user_profile`을 이용해 `LoanEvaluationService.evaluate_listing_loans()` 호출 및 `item.eligible_loans` 리스트 설정.
- `list_partial.html`: 매물 카드 상단에 정책대출 혜택 뱃지 노출.

### 2.2 실시간 금액 콤마(`,`) 자동 포맷팅 (JavaScript)
- 위치: `src/realty_radar/web/templates/settings/index.html`, `listings/index.html`
- 금액 입력 필드(`input.currency-input`)에 `input` 이벤트 핸들러 장착:
  - 타이핑 시 숫자 이외의 문자 제거 후 천 단위 콤마(`,`) 추가.
  - 폼 전송 시 콤마를 정제하여 백엔드로 안전하게 전달.

### 2.3 Jinja2 금액 필터 개선
- 위치: `src/realty_radar/web/jinja_filters.py`
- `comma_number` 필터 구현 (예: `650000000 | comma_number` -> `650,000,000`).

## 3. 검증 계획
- `pytest tests/unit/test_jinja_filters.py tests/integration/test_loan_service.py` 실행.
- 웹 브라우저에서 `/settings` 및 `/` 금액 입력 시 콤마 자동 입력 및 대출 뱃지 표시 확인.

## 4. 수행 결과 보고
- **매물 카드 정책대출 적격 뱃지 연동**: `home.py`에서 매물 검색 결과 반환 시 `session_user_profile` 기반의 `LoanEvaluationService` 적격 조회를 실행하여 매물 상단 카드 뱃지("디딤돌 대출 가능", "버팀목 대출 가능" 등)를 성공적으로 표시했습니다.
- **금액 가독성 향상 (천 단위 콤마 표기)**: Jinja2 필터 `comma_number`를 추가하고 `list_partial.html` 매물 카드 금액 표시 부분에 적용하여 `650,000,000 원` 형태로 가독성을 획기적으로 개선했습니다.
- **실시간 천 단위 콤마(`,`) 자동 채움 기능**: `/settings` 설정 페이지의 연소득, 순자산 입력 박스 및 필터 조건 입력란에 자바스크립트 실시간 포맷터(`input.money-input`)를 적용하여 사용자가 숫자를 입력할 때 즉시 천 단위 콤마가 자동 생성되도록 구현했습니다.
- **테스트 통과**: 39개 전체 유닛 및 통합 테스트를 수행하여 100% 성공(`39 passed`)을 확인했습니다.
