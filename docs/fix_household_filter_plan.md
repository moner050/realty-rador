# 세대수 필터 정제 세대수(COALESCE) 기준 전환 계획서

## 1. 개요 및 원인
기존 필터 방식(`or_(Listing.total_households >= min, ApartmentComplex.total_households >= min)`)은 매물 자체의 정제된 세대수 대신 오매칭된 단지 세대수가 조건에 걸려 필터링 왜곡이 발생하는 원인이 되었습니다.

---

## 2. 해결 방안

### 1) `ListingSearchService` 필터 조건식 개선
- `func.coalesce(Listing.total_households, ApartmentComplex.total_households)`를 사용하여 매물 자체의 **정제된 세대수**를 1순위 기준으로 적용.
- 준공년도 필터 역시 `func.coalesce(Listing.construction_year, ApartmentComplex.construction_year)`를 사용하여 1순위 정제된 준공년도로 필터링 적용.

---

## 3. 검증 계획
1. pytest 51개 전체 테스트 구동 및 통과 확인.
2. 정제된 세대수 기준 필터링 쿼리가 정상 작동하는지 확인.
