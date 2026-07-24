# 서울특별시 필터 선택 시 경기도 매물 혼입 버그 수정 계획서

서울특별시 선택 시 경기도 매물이 혼입되어 출력되던 문제에 대한 원인 분석 및 수정 계획입니다.

## 1. 원인 분석

- **시/도(sido) OR 조건 결합으로 인한 우회 침투**:
  - `listing_search_service.py` L314에서 `where(or_(*sido_conds, ApartmentComplex.sido.like(...)))` 처리 시, `Listing` 자체의 주소(`address_raw`) 및 `sido`가 `경기도`이더라도, outerjoin된 `ApartmentComplex.sido`가 `서울특별시`로 다르게 매핑된 데이터가 있으면 `OR` 조건문에 의해 참(True)으로 포함되어 경기도 매물이 서울특별시 결과에 노출되었습니다.

---

## 2. 주요 수정 계획

### [Backend] `src/realty_radar/application/listing_search_service.py`
- **시/도(sido) 필터링 정밀 격리 조치**:
  - `Listing.sido` 및 `Listing.address_raw`를 최우선 기준으로 격리.
  - `서울특별시` 검색 시 `Listing.sido`가 경기도/인천이거나 `address_raw`가 `'경기 %'`, `'경기도 %'`, `'인천 %'`인 타 지역 매물은 `~Listing.sido.in_(...)` 및 `~Listing.address_raw.like(...)` 방어막으로 명시적 차단하여 우회 노출을 원천 예방.

---

## 3. 검증 계획
- pytest 및 gradle 검증 수행.
- `sido='서울특별시'` 쿼리 시 경기도/인천 등 타 지역 매물 포함 여부 (0건 차단 확인) 테스트.
