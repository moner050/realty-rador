# 멀티 브라우저 컨텍스트 기반 병렬 분할 크롤링 아키텍처 분석 및 계획서

## 1. 개요 및 분석 배경
- **현상**: 현재 크롤러(`SiteAAdapter`)는 단일 브라우저 세션(`self._session_page`)에서 구 → 동 → 단지를 **순차적(Single Thread / Serial execution)**으로 수집하고 있습니다.
- **병목 원인**: 서울시 전체 25개 구(수백 개 동, 수천 개 단지)를 1.5초 딜레이로 순차 수집 시 **전체 수집 소요시간이 15분~30분 이상 발생**합니다.
- **목적**: 소스 코드를 바로 수정하지 않고, **지역 분할 멀티 워커(Async Parallel Workers / Browser Context Pool)** 방식의 도입 타당성, 최적 아키텍처, 위험 요소(차단/메모리/DB) 및 단계별 구현 계획을 정립합니다.

---

## 2. 기술 방식 비교 분석 (Multi-Threading vs Async Multi-BrowserContext)

| 비교 항목 | 방식 A: Multi-Threading / Processing (프로세스/스레드 생성) | 방식 B: Async Multi-BrowserContext Worker Pool (권장) |
| :--- | :--- | :--- |
| **개념** | Playwright 브라우저 프로세스를 N개 개별 창으로 가동 | 1개의 Chromium 실행 후, 독립 세션(`BrowserContext`) N개 분할 가동 |
| **메모리/CPU 사용량** | **매우 높음** (Chromium N개 띄움, RAM 수 GB 소모) | **매우 낮음** (Chromium 1개 공유, 세션/쿠키만 N개 격리) |
| **동시 처리 속도** | 빠름 | **매우 빠름** (`asyncio.gather` / `asyncio.Queue` 기반) |
| **안정성/예외 관리** | 프로세스 간 DB 세션 공유 복잡 | 단일 비동기 이벤트 루프 내에서 세마포어로 완벽 제어 가능 |
| **차단 대응 (Rate Limit)** | IP/WAF 차단 위험 높음 | 글로벌 세마포어(Global RateLimiter)로 초당 요청 동시 제어 용이 |

---

## 3. 권장 병렬 크롤링 아키텍처 설계

1. **Region Task Producer (지역 분할 분배기)**:
   - 요청된 지역(예: 서울 전체)의 하위 구/시(Sigungu) 또는 동(Dong) 목록을 미리 가져와 `asyncio.Queue` 작업 큐에 채웁니다.
2. **Parallel Worker Pool (N개 병렬 워커)**:
   - 설정된 동시성 제한 수(예: `max_workers = 5`) 만큼 병렬 워커 태스크를 띄웁니다.
   - 각 워커는 자기만의 독립된 `BrowserContext` 및 `Page`를 가지고 큐에서 동/구 작업을 꺼내 독립적으로 크롤링합니다.
3. **글로벌 Rate Limiter & IP 차단 방지**:
   - `asyncio.Semaphore` 기반의 글로벌 동시성 제어 장치를 달아, 네이버 API 차단 방지(초당 최대 5회 제한).
4. **실시간 DB 스트리밍 연동**:
   - 기존 `on_batch_callback`을 각 워커가 공통으로 호출하여 **5개 구/동에서 동시에 수집되는 데이터가 실시간으로 DB에 적재**.

---

## 4. 기대 효과 (Performance Benchmark)

- **수집 속도**: 서울 전체(25개 구) 수집 기준 **기존 ~20분 내외 → 개편 후 ~2분~3분으로 약 7~10배 속도 향상**
- **자원 효율성**: `BrowserContext` 기반이므로 5개 병렬 수집 시에도 메모리 증가량 약 150MB 수준으로 경량화
- **안정성**: 특정 동/구 수집 중 에러가 발생해도 다른 워커의 수집은 멈추지 않고 계속 진행됨 (격리성 보장)
