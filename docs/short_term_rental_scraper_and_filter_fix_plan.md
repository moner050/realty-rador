# 네이버부동산 단기임대 수집 파서 & 필터 정밀 개편 계획서

## 1. 개요 및 원인
네이버부동산 API 응답 데이터에는 `tradeTypeName: "단기임대"` 및 보증금/월세(`dealOrWarrantPrc` / `rentPrc`) 정보가 정상 포함되어 있으나, 기존 수집 파서 및 정규화기(`SiteANormalizer`)에서 `"단기임대"` 거래유형 감지가 누락되어 **매매(SALE) 2억 2,000만 원**과 같이 단기임대 월세 매물이 매매로 오파싱되는 문제가 있었습니다.

---

## 2. 개편 세부 변경사항

### 1) 수집 파서 및 정규화기 개편 (`SiteAParser`, `SiteANormalizer`)
- `SiteAParser`: `tradeTypeName`이 `"단기임대"`이거나 `rentPrc`가 존재하는 경우 `price_raw`에 `단기임대 2억 2,000/270` 형식으로 단기임대 식별 정보를 명확히 기록.
- `SiteANormalizer`:
  - `normalize_price` 메서드에서 `"단기임대"` 또는 `"월세"` 거래 유형을 100% 감지하여 `TransactionType.MONTHLY_RENT`로 분류.
  - 보증금(`price_deposit`)과 월세(`price_monthly_rent`)를 분리하여 정확히 정규화.

### 2) 검색 필터 서비스 강화 (`ListingSearchService`)
- 단기임대 제외 옵션 (`exclude_short_term=True`) 적용 시:
  - `price_raw`, `description_raw`, `address_raw`, `complex_name_raw` 내 `"단기임대"` 문자열 포함 매물 100% 원천 배제.
  - 거래유형이 `SALE` (매매) 검색인 경우 월세(`price_monthly_rent`)가 존재하는 매물 배제.

---

## 3. 검증 계획
1. 검증 스크립트로 `송파파인타운4단지 401동 단기임대 2억 2,000/270` 등 단기임대 매물이 매매 검색 결과에서 100% 원천 제거되었는지 확인.
2. `pytest tests/` 51개 전체 테스트 수행.
