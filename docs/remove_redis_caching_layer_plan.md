# 불필요한 Redis 검색 캐싱 레이어 전면 제거 및 구조 단순화 계획서

## 1. 개요
DB 스키마 및 B-Tree 슈퍼 인덱스 개편을 통해 DB Direct Query 속도가 **4.6ms(0.004초)**로 압도적인 성능을 달성함에 따라, 기존의 불필요하고 복잡했던 **Redis 검색 청크 캐싱 및 서버 부팅 웜업 로직을 전면 제거**하여 고성능 단일 DB 구조로 시스템을 대폭 단순화합니다.

---

## 2. 주요 변경 사항

### 1) `ListingSearchService` Redis 캐싱 제거
- `search_listings()` 메서드 내 Redis `listings_chunk:*` 캐시 Key 조회 및 직렬화/데세리얼라이즈 불필요 연산 완전 차단.
- DB Direct 쿼리로 단 4ms 만에 결과를 바로 반환하도록 단순화.

### 2) 웹 서버 `main.py` 웜업 로직 제거
- `lifespan` 내 불필요한 백그라운드 캐시 웜업 루틴(`_run_background_cache_warmup`) 제거.
- 서버 시작 오버헤드 0ms 달성.

---

## 3. 검증 계획
1. pytest 51개 유닛/통합 테스트 구동 및 100% 통과 확인.
2. DB Direct Query 성능 측정 (0.01초 미만 유지 확인).
