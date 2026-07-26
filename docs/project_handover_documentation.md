# Realty Radar v2 인수인계

2026-07-26 기준, Realty Radar는 네이버부동산(SITE_A)만 수집하는 MySQL 8.4 기반 매물 검색 서비스다. 기존 데이터는 이관하지 않으며, 검색 경로의 읽기 성능과 수집의 일관성을 우선한다.

## 현재 구조

```text
web / scheduler ──> crawl_job ──> worker
                                  ├─ Playwright bootstrap (인증만)
                                  ├─ httpx AsyncClient (API 수집)
                                  └─ bounded queue ──> temporary staging writer ──> MySQL

web search ──> listing_current (JOIN 없는 hot table)
```

- `PlaywrightBrowserManager`는 worker 수명 동안 Chromium 프로세스만 재사용한다.
- 각 잡은 새 browser context에서 `new.land.naver.com` 한 곳만 열어 Authorization과 쿠키를 메모리에서 획득한다.
- 실제 region, complex, article API 호출은 장기 `httpx.AsyncClient` connection pool이 담당한다. 인증 정보·raw JSON·원본 URL은 로그, DB, 파일에 저장하지 않는다.
- `NaverHttpClient`는 초기 동시성 8(4~32), connection/keepalive 32, connect/read/pool timeout 5/15/15초를 사용한다. 50회 연속 성공 시 +1, 429 시 절반으로 감소하며 `Retry-After`를 적용한다. 401은 refresh 1회, 반복 403은 `RETRY_WAIT` circuit breaker, 5xx/timeout은 URL별 최대 3회 backoff 재시도다.
- pagination은 전역 queue로 확장한다. 중복 페이지 또는 100페이지 상한은 scope를 partial/failed로 기록하며 stale 판정을 막는다.

## 데이터베이스 v2

기본 DSN은 `realty_radar_v2`를 가리킨다. canonical Alembic migration은 `2026_07_26_0001_site_a_v2` 하나이며, `Base.metadata.create_all`과 reset 스크립트는 사용하지 않는다.

| 테이블 | 용도 | 핵심 키와 인덱스 |
| --- | --- | --- |
| `complex_current` | 단지 탐색/공공데이터 보강 | `complex_id`; sigungu+이름, sigungu+준공/세대수, ngram FULLTEXT |
| `listing_current` | 검색 화면 전용 hot table | `article_id`; lifecycle/지역/거래/가격, 최신, 면적, 세대수, 단지 복합 인덱스 |
| `listing_history` | 실제 변경만 보관하는 cold append-only table | `(job_id, article_id, event_type)` idempotency, article timeline |
| `crawl_job` | lease 기반 수집 잡 queue | dedupe, claim, reaper, recent 인덱스 |
| `crawl_scope` | 동 단위 수집 완전성 | `(job_id, region_code)` |

`region_code`에서 `sido_code`, `sigungu_code`를 generated stored column으로 만든다. `listing_current`은 완전 비정규화되어 목록 검색에 JOIN이 없다. 단지 검색만 `complex_current`의 ngram FULLTEXT로 complex ID를 찾아 hot table을 조회한다.

### 저장과 lifecycle

네트워크 producer와 단일 DB writer 사이에는 bounded queue가 있다. writer 연결은 `incoming_listing` temporary table을 만들고, 500건 또는 1초마다 다음을 하나의 transaction으로 처리한다.

1. 수치 ID와 필수 필드를 검증하고 batch 내 `article_id`를 중복 제거한다.
2. 단지 정보를 multi-row upsert한다.
3. incoming temporary table에 bulk insert한다.
4. 변경된 `state_hash`에 대해서만 history를 `INSERT IGNORE`한다.
5. current를 `INSERT … SELECT … ON DUPLICATE KEY UPDATE`로 갱신한다.
6. commit 뒤에만 job counter를 증가시킨다.

`crawl_scope`가 complete인 동만 미관측 매물을 ACTIVE→STALE→REMOVED로 진행한다. 실패하거나 truncated된 동은 lifecycle을 바꾸지 않는다.

## 검색 계약

- 목록은 `items`, `next_cursor`, `has_more`를 반환한다. OFFSET과 매 요청 `COUNT(*)`는 사용하지 않는다.
- cursor는 `(sort_value, article_id)`와 filter fingerprint를 서명하므로 다른 필터에 재사용할 수 없다.
- 가격, 최신, 면적, 세대수, 단지 묶음은 keyset pagination을 사용한다.
- 층, 방향, 융자는 문자열 LIKE가 아닌 숫자 코드의 정확 비교다. 대출 적격성은 DB 후보를 먼저 줄인 뒤 정책 evaluator 하나가 판단한다.

## 운영 절차

1. worker와 scheduler를 중지하고 대상 MySQL 인스턴스 및 DB 이름을 확인한다.
2. `python scripts/create_v2_database.py --database realty_radar_v2 --confirm-create realty_radar_v2`로 DB를 생성하고 Alembic head를 적용한다.
3. `MYSQL_V2_TEST_URL`을 설정한 뒤 `python -m pytest -m mysql -q`로 MySQL 기능을 검사한다.
4. 한 동 smoke crawl 후 `crawl_scope`와 current/history 카운터를 점검한다. live HTTP 검증은 `RUN_LIVE_SITE_A_HTTPX=1 python -m pytest -m live -q`로만 실행한다.
5. 수도권 fresh crawl에서 모든 동 coverage가 complete인지 확인한 후 web/worker DSN을 v2로 전환한다.
6. 기존 DB는 rollback 기간 동안 유지한다. 퇴역 시 `python scripts/retire_v1_tables.py --database <old-db> --confirm-drop <old-db>`를 실행한다. 이 스크립트는 먼저 날짜 포함 `mysqldump`를 생성하고 명시된 legacy table만 DROP한다.

## 검증 기준

로컬 기본 suite는 `python -m pytest -q`다. MySQL/live marker는 환경 변수가 없는 경우 skip되는 것이 정상이다. 배포 전에는 generated column, ngram FULLTEXT, temporary staging, bulk upsert, `SKIP LOCKED`, replay idempotency와 cursor의 누락/중복을 확인한다.

성능 수치는 canary 전까지 실환경 개선값을 추정하지 않고 `N/A`로 보고한다. 목표는 100만 current/1천만 history warm buffer에서 일반 목록 p95 100ms 이하, 단지 묶음 200ms 이하, 단일 매물 history 50ms 이하이다.
