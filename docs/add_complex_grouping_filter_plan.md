# 동일 아파트 묶어서 보기 필터 및 접이식(Accordion) UI 구현 계획서

## 1. 개요 및 요구사항
- 검색 필터 화면에 **"동일 아파트 묶어서 보기"** 필터를 추가합니다.
- 필터 조건(가격, 면적, 세대수, 대출 조건 등)에 맞게 걸러진 매물들만을 대상으로 단지별로 그룹화합니다.
- 단지 그룹 카드에 최저가~최고가 범위(예: `5억 5,000만원 ~ 6억원`) 및 매물 수량을 표기합니다.
- 그룹 카드를 클릭하면 속한 매물 목록이 아코디언 방식으로 **접혔다 펴지는(Toggle)** UI를 제공합니다.

---

## 2. 세부 구현 계획

### 1) 백엔드 DTO 및 서비스 개편
- **[domain/listing/models.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/domain/listing/models.py)**:
  - `ListingFilterParams`에 `group_by_complex: bool = False` 추가.
  - 단지 그룹 정보를 담는 `ComplexGroupItem` 및 `SearchResult` DTO 보강.
- **[application/listing_search_service.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/application/listing_search_service.py)**:
  - `group_by_complex`가 `True`인 경우, 필터링된 결과 매물을 `complex_id` 또는 `complex_name_raw` 기준으로 파이썬 인메모리 단지 그룹핑을 수행.
  - 최저가/최고가 범위 계산 및 한글 금액 범위 문자열(`5억 5,000만 원 ~ 6억 원`) 구성.

### 2) 프론트엔드 UI & 템플릿 구현
- **[web/templates/listings/index.html](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/templates/listings/index.html)**:
  - 필터 옵션 영역에 `동일 아파트 묶어서 보기` 토글 스위치/체크박스 추가.
- **[web/templates/listings/list_partial.html](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/templates/listings/list_partial.html)**:
  - 단지 그룹 모드(`is_grouped`)일 때 고급 아코디언 카드 렌더링.
  - 클릭 시 펼쳐지는 부드러운 토글 애니메이션 적용.

---

## 3. 검증 계획
1. `pytest` 전체 테스트 통과 확인.
2. 필터 적용 시 6억 이하 등의 조건에 맞는 매물들로만 정확히 아파트별 그룹핑되는지 확인.
