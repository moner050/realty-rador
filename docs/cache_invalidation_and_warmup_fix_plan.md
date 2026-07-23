# 0건 잔존 캐시 자동 무효화 및 매물 52만 건 노출 완수 계획서

## 1. 매물 미노출 근본 원인 분석
- **원인**: 이전 실행 시 저장되었던 `listings_full_search:*` 캐시 키에 `total_count: 0, items: []` 형태의 **잘못된 0건 캐시 데이터가 Redis에 300초간 남아있어서**, DB 쿼리를 스킵하고 0건으로 계속 응답함.

---

## 2. 해결 방안

### 1) Redis 0건 잘못된 캐시 자동 무효화 (`listing_search_service.py`)
- 캐시 적중 시 `cached_data`의 `total_count == 0` 이거나 `items`가 비어있으면 캐시를 무효화하고 DB 쿼리를 구동하여 올바른 최신 매물을 즉시 갱신 적재.

### 2) 서버 시작 시 (Startup Lifespan) 이전 검색 캐시 초기화 (`main.py`)
- `redis_cache.delete_pattern("listings_full_search:*")` 호출로 잔존 0건 캐시를 자동 제거.
- MySQL에 저장된 52만 건 최신 매물을 읽어와 Redis로 사전 웜업(Warm-up) 적재.

---

## 3. 검증 계획
- `python -m pytest tests/` 구동으로 51개 전체 테스트 정상 통과 검증.
