# 세대수 및 준공년도 매핑 오류 수정 계획서

## 1. 개요 및 원인 분석

### 1) 매물-단지 매칭 시 공용 단지 정보 무분별 덮어쓰기 버그
- `ComplexMatchService._update_complex_region_and_info`에서 이미 존재하는 `ApartmentComplex` 단지 객체의 `total_households` 및 `construction_year`를 새로 매칭되는 매물 데이터로 무조건 덮어써 오염시킴.

### 2) UI 템플릿의 `Listing` 본래 데이터 미참조
- `list_partial.html`에서 매물 자체의 비정규화 정보 `item.total_households` 및 `item.construction_year` 대신 오염된 `item.complex.total_households` 및 `item.complex.construction_year`를 참조하여 렌더링함.

---

## 2. 해결 방안

### 1) UI 템플릿 (`list_partial.html`) 수정
- 매물 자체 데이터(`item.total_households`, `item.construction_year`)를 우선 사용하고, 없을 경우 `item.complex` 데이터를 차선책(fallback)으로 사용하도록 수정.

### 2) 단지 매칭 서비스 (`ComplexMatchService`) 수정
- `ApartmentComplex` 단지의 `total_households`와 `construction_year`가 이미 존재하는 경우 무분별하게 덮어쓰지 않도록 비어있을 때만 수복하도록 보호 (`if complex_obj.total_households is None:`).

### 3) 기존 오염 DB 데이터 정제 스크립트 작성 및 구동
- `Listing` 마스터 테이블의 `total_households`와 `construction_year` 정보를 정제 복원하는 마이그레이션 실행.

---

## 3. 검증 계획
1. pytest 유닛 및 통합 테스트 통과 확인.
2. 봉천동 삼성 매물 세대수(25세대), 준공연도(1974년) 정상 출력 검증.
