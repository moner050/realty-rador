# 작업 계획서: 개인 자격 대출 기준 및 차용증 작성 인원수 기반 아파트 필터링 개선

## 1. 개요
결혼 예정자 혜택을 제거하고, 순수 **개인 자격(일반 무주택/생애최초)**으로 구매할 수 있는 대출 상품(디딤돌 5억 이하, 버팀목 3억 이하)으로 기준을 조정합니다.
또한 **차용증 사용 가능 여부** 및 **작성 가능 인원수(1인당 2억 1,700만원)**를 설정에서 입력받아 총 자본금을 계산하고 구매 가능한 아파트를 필터링하도록 수정합니다.

## 2. 상세 내역
1. `ApplicantProfile`: `is_engaged` 제거, `use_promissory_note`, `promissory_note_person_count`, `promissory_note_amount` 추가.
2. `LoanRuleEvaluator`: 개인 자격(일반 미혼/일반 가구 5억 이하, 버팀목 3억 이하) 중심 대출 한도 산출.
3. `ListingSearchService`: `total_capital = net_assets + (use_promissory_note ? person_count * 2.17억 : 0)` 기반의 구매 가능 매물 필터링.
4. `settings/index.html`: 차용증 사용 가능 여부 체크박스 및 작성 가능 인원수 입력란 제공.
