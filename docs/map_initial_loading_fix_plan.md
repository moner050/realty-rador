# 지도 첫 접속 시 데이터 자동 로딩 개선 계획서 (map_initial_loading_fix_plan.md)

## 1. 문제 분석
홈페이지에 처음 접속했을 때 지도에 단지 마커 및 클러스터가 표시되지 않고(`0개 단지`), 지도를 확충하거나 이동해야 데이터를 조회하던 문제를 해결함.

## 2. 세부 원인
`src/realty_radar/web/static/listing-map.js` 모듈에서 지도 객체가 생성된 후(`mount`) 첫 번째 `idle` 이벤트가 수신될 때 `viewportDirty` 상태값이 `false`여서 초기 데이터 조회가 스킵되었음.

## 3. 조치 사항
- `listing-map.js` 내 `instance.viewportDirty = true;`로 초기화하여 첫 `idle` 이벤트 수신 즉시 자동으로 뷰포트 마커 데이터를 로딩함.
- 초기 지도 줌 레벨(`INITIAL_ZOOM`)을 `11`로 조정하여 첫 화면 접속 시부터 시군구 클러스터 및 주요 단지 마커가 또렷하게 나타나도록 최적화.
