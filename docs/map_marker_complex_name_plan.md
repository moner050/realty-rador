# 지도 마커 오버레이 단지명 및 가격 표시 계획서 (map_marker_complex_name_plan.md)

## 1. 개요
지도를 확대했을 때 노출되는 단지 마커에 기존 가격 단일 표시 방식 대신, 윗줄에 아파트 단지명(`complex_name`)과 아랫줄에 가격 및 매물 수를 2단 구조로 시각화하여 가독성을 극대화함.

## 2. 세부 변경 사항
- `src/realty_radar/web/static/listing-map.js` 내 `makeMarkerOverlay`:
  - 1행: `item.complex_name` (단지 이름)
  - 2행: `formatPrice(item.min_price)` + `(item.listing_count건)`
