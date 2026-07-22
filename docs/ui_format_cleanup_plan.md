# 작업 계획서: 매물 카드 가격 표기 단순화 및 출처 명칭 수정

## 1. 개요
사용자 요구사항에 맞춰 매물 카드의 한글 금액 우측에 출력되던 천 단위 콤마 숫자 표기(괄호 부분)를 제거하여 단순화하고, 출처 명칭 표기를 "네이버부동산"으로 깔끔하게 정돈합니다.

## 2. 상세 수정 계획

### ① 가격 표기 단순화
- 위치: `src/realty_radar/web/templates/listings/list_partial.html`
- 내용: `{{ price_val | korean_price }} ({{ price_val | comma_number }}원)` 중 `({{ price_val | comma_number }}원)` 부분 및 월세 콤마 표기 괄호 부분을 전면 제거합니다.

### ② 출처 명칭 표기 정돈
- 위치: `src/realty_radar/web/templates/listings/list_partial.html`
- 내용: `{{ item.source.source_name or item.source.source_code | korean_source }}`를 `{{ item.source.source_code | korean_source }}`로 수정하여 DB 명칭과 무관하게 언제나 "네이버부동산"으로 포맷 출력되도록 보완합니다.
- 위치: `scripts/reset_and_migrate_db.py`
- 내용: `source_name="네이버부동산 (Site A)"` 설정 부분을 `source_name="네이버부동산"`으로 정비하여 초기 시드 데이터 수준에서도 일괄 통일합니다.

## 3. 검증 계획
- `pytest tests/unit tests/integration` 실행하여 테스트 100% 통과 검증.
- 매물 검색 화면 리스트 상에서 금액 표기 괄호 숫자 및 "(Site A)" 텍스트가 정상 제거되었는지 육안 및 템플릿 검증.

## 4. 수행 결과 보고
- **가격 표기 단순화 완료**: [list_partial.html](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/templates/listings/list_partial.html) 매물 카드 우측의 `({{ price_val | comma_number }}원)` 등 중복되던 천 단위 콤마 숫자 표기(괄호 부분)를 깔끔하게 제거하여 `8억 5,000만 원` 형태로 심플하게 통일했습니다.
- **출처 명칭 "네이버부동산" 통일**: [list_partial.html](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/templates/listings/list_partial.html) 출처 필드에 `korean_source`를 타도록 일원화하고, [reset_and_migrate_db.py](file:///c:/workspace/personal/real-estate-search/scripts/reset_and_migrate_db.py) 시드 설정에서 "(Site A)" 명칭 부분을 제거하여 화면 상에 오직 "네이버부동산"으로만 깔끔히 노출되도록 조치했습니다.
- **테스트 성공**: 40개 모든 테스트를 구동하여 성공적으로 통과(`40 passed`)했습니다.
