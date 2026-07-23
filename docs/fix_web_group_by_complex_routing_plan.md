# 웹 필터 라우팅 파라미터 미수신으로 인한 그룹핑 미작동 원인 분석 및 수정 계획서

## 1. 원인 분석

### 1) 라우터 파서(`parse_search_filter`)의 `group_by_complex` 쿼리 파라미터 누락
- 프론트엔드 체크박스(`filter-group-by-complex`)에서 `group_by_complex=true`를 웹 서버로 전송하지만, 웹 라우터 파서인 `parse_search_filter`(`src/realty_radar/web/routes/home.py`)에 해당 쿼리 매개변수 선언이 누락되어 서버가 매개변수를 완전히 무시함.

### 2) DTO(`ListingSearchFilter`)의 `group_by_complex` 필드 누락
- `ListingSearchFilter` (`src/realty_radar/domain/listing/filters.py`)에 `group_by_complex` 필드가 선언되어 있지 않아 `search_listings()` 서비스로 전달되지 않고 항시 `False`로 동작함.

---

## 2. 해결 방안

### 1) `ListingSearchFilter` DTO 속성 추가
- [filters.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/domain/listing/filters.py): `group_by_complex: bool = False` 속성 추가.

### 2) 웹 라우터 파서 매개변수 바인딩
- [home.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/routes/home.py): `parse_search_filter` 함수에 `group_by_complex: bool = Query(False)` 추가 및 `ListingSearchFilter` 전달.

---

## 3. 검증 계획
1. `TestClient` 웹 통합 디버그 스크립트를 실행하여 `/listings/search?group_by_complex=true` 요청 시 응답 HTML에 `아파트 묶음` 카드가 정상 출력되는지 검증.
2. pytest 전체 자동화 테스트 54개 통과 확인.
