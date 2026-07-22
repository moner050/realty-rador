# 작업 계획서: 결혼 예정자 및 차용증 활용 자금 반영 정책대출 필터 개선

## 1. 개요
혼인신고 전 결혼 예정자 세대 및 부모/친족 차용증 작성 자금(증여세 2억 1,700만원 면제 한도)을 설정에 추가하여, 실제 내 자본금과 정책대출 한도로 매수/임차 가능한 아파트만 홈 화면에서 정밀 검색하도록 필터를 개선합니다.

## 2. 상세 개발 항목

### ① 설정 UI 문구 및 필드 추가
- `src/realty_radar/web/templates/settings/index.html`
  - "부부합산 연소득 (원)" -> **"개인 또는 부부합산 연소득 (원)"** 변경.
  - "결혼 예정 여부 (`is_engaged`)" 체크박스 추가.
  - 차용증 활용 한도 안내 팁 카드(2억 1,700만원 증여세 면제 한도 설명) 및 차용금 입력 필드(`promissory_note_amount`) 추가.

### ② 도메인 프로필 및 대출 평가 엔진 확장
- `src/realty_radar/domain/loan/entities.py`: `is_engaged`, `promissory_note_amount`, `total_capital` 속성 추가.
- `src/realty_radar/domain/loan/evaluator.py`: `is_newlywed or is_engaged` 일 때 디딤돌/버팀목 신혼 우대 조건(매매가 6억, 대출 3억, 소득 8500만 이하 등) 동등 적용.

### ③ 검색 필터 서비스 자본금 합산 필터링 연동
- `src/realty_radar/application/listing_search_service.py`:
  - `only_eligible_loans` 적용 시, `min(법정 한도, applicant.total_capital + max_loan_limit)`으로 매매가/보증금 상한을 산출하여 실제 구매 가능한 아파트 매물만 SQL 레벨에서 엄격 필터링.

## 3. 검증 계획
- `pytest tests/unit tests/integration` 실행으로 unit 및 integration 테스트 100% 통과 확인.
