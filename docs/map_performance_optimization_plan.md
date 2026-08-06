# 지도 로딩 속도 최적화 및 Redis 캐시 도입 아키텍처 문서 (map_performance_optimization_plan.md)

## 1. 현상 분석
현재 Realty Radar의 지도 서비스는 지도를 드래그하거나 줌 레벨을 조절할 때마다 백엔드로 `/map/data` 및 `/map/cards` API 요청을 보냅니다. 백엔드에서는 매번 MySQL 데이터베이스에서 경계 조건(`map_west, map_south, map_east, map_north`) 쿼리를 실행하여 단지를 그룹핑하고 수집 마커를 집계합니다.

### 주요 병목 요인:
1. **DB 집계 쿼리 연산 부하**: 매 요청 시 MySQL에서 `GROUP BY complex_id`, `MIN(price)`, `MAX(price)`, `COUNT(*)` 집계 연산 수행.
2. **지연 시간 (Debounce Time)**: 프론트엔드 `listing-map.js`에 설정된 1.5초(1500ms) 대기시간.

---

## 2. Redis 도입 시 기대 효과 및 캐시 설계

### 🚀 Redis 도입 효과
- **응답 속도 개선**: DB Disk I/O (30ms ~ 200ms) -> Redis Memory Lookup (1ms ~ 5ms)로 **약 10~20배 향상**.
- **DB 부하 대폭 감소**: 동일 뷰포트나 인접 구역 반복 조회 시 DB 쿼리가 0건으로 감소.

### 🛠️ Redis 캐시 구조 설계

1. **단지 기본 정보 및 좌표 캐시 (Complex Geo Cache)**
   - **Key**: `realty:complex:{complex_id}`
   - **Value (Hash)**: `{ "name": "...", "lat": 37.55, "lng": 126.90, "address": "..." }`
   - **TTL**: 24시간

2. **뷰포트/셀 기반 클러스터 캐시 (Viewport Cluster Cache)**
   - **Key**: `realty:map:viewport:{filter_hash}:{zoom}:{west}_{south}_{east}_{north}`
   - **Value (JSON)**: `ListingMapViewport` 객체 직렬화 데이터
   - **TTL**: 5분

3. **Redis Geospatial Index (GEOSEARCH) 활용**
   - `GEOADD realty:map:geo <longitude> <latitude> <complex_id>`
   - `GEOSEARCH` 명령으로 Bounding Box 탐색을 DB 조인 없이 Redis 레벨에서 초고속 처리.

---

## 3. 프론트엔드 최적화 병행

1. **디바운스 타임 조정**: `listing-map.js`의 `VIEWPORT_SEARCH_DEBOUNCE_MS`를 `1500ms`에서 `300ms ~ 500ms`로 단축.
2. **클라이언트 메모리 캐싱**: 브라우저 JS 단에 최근 조회한 뷰포트 결과를 저장하여 뒤로가기나 동일 위치 재조회 시 즉시 렌더링.
