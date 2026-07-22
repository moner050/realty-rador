# 컴퓨터 리소스 극대화 기반 초고속 크롤링(Ultra-Fast Crawling) 전략 마크다운

## 1. 현재 병목 원인 진단

| 구 분 | 현재 방식 (Playwright Browser Context) | 원인 및 한계점 |
| :--- | :--- | :--- |
| **페이지 네비게이션** | 단지마다 `page.goto(...)` 호출 | 단지 1개당 DOM 렌더링 + JS 초기화에 **2~3초 소요** (전체 90% 병목) |
| **요청 동시성** | `max_workers = 4` (구 단위 순차 수집) | 구(Sigungu)는 순차 수집하고 구 내부 동(Dong)만 4개 병렬 |
| **리소스 활용률** | CPU/RAM 사용률 10% 미만 | PC의 남는 CPU 코어 및 메모리 자원을 거의 쓰지 않음 |

---

## 2. 컴퓨터 리소스 극대화 기반 4대 초고속화 방안 (Hyperspeed Strategies)

### Strategy 1. Playwright DOM 네비게이션 완전히 제거 -> Pure Async HTTP Client (`httpx`) 직호출 [속도 40배 ↑]
- **개념**: 
  - Playwright는 최초 1회만 켜서 네이버 보안 쿠키/헤더만 채취한 뒤 브라우저를 즉시 종료합니다.
  - 이후 모든 단지/동/매물 조회를 **Playwright 페이지 띄우기 없이 `httpx.AsyncClient` (HTTP/2 지원)** 기반의 pure async HTTP 통신으로 직접 수행합니다.
- **기대 효과**:
  - 단지 1개 수집 소요시간: **2.5초 → 0.05초 (50ms)**
  - 서울/경기 전역 수집 시간: **20분 → 30초~1분 미만으로 파격 축소**

---

### Strategy 2. Multi-Level Worker Pool (구 & 동 2단계 동시성 폭발 수집) [속도 5배 ↑]
- **개념**:
  - 기존: 구(Sigungu)는 1개씩 순차 진행 → 구 내부 동만 4개 병렬
  - **개편**: **5개 구(Sigungu)를 동시에 띄우고, 각 구 내부에서 8개 동을 동시에 처리** (총 40개 비동기 파이프라인 동시 가동)
- **리소스 투입량**:
  - CPU 코어 8개 이상, RAM 4GB~8GB 전면 투입

---

### Strategy 3. 경량화 Mobile API (`m.land.naver.com`) 및 Connection Pooling 융합
- **개념**:
  - PC 웹 용 무거운 API대신 데이터 응답 속도가 3배 이상 빠른 Mobile 경량 API (`/api/articles/complex/{complexNo}`) 활용.
  - HTTP Connection Pool (Keep-Alive TCP 커넥션 재활용)로 SSL/TLS 핸드셰이크 지연시간 0ms 구현.

---

### Strategy 4. 하드웨어 스펙 맞춤형 튜닝 파라미터

| 파라미터 | 권장 설정 값 | 설명 |
| :--- | :--- | :--- |
| `max_sigungu_workers` | **5 ~ 8** | 동시 수집할 구/시 수 (서울 5개 구 동시 진행) |
| `max_dong_workers` | **8 ~ 16** | 구 내부에서 동시 수집할 동 수 |
| `httpx_max_connections` | **100 ~ 200** | 비동기 HTTP 커넥션 풀 크기 |
| `rate_limit_interval_ms` | **100ms ~ 200ms** | WAF 차단 안 당하는 최적 초고속 API 요청 간격 |

---

## 3. 요약 및 적용 예상 결과

- **수집 소요시간**: 서울/경기 전역 (65개 구/시, 수만 개 단지) **기존 ~20분 → 개편 시 1분 미만 (약 30~50초)**
- **컴퓨터 자원 활용**: CPU 멀티코어 80% 활용, RAM 2~4GB 투입으로 하드웨어 성능 한계까지 발휘.
