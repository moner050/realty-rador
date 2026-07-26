# SITE_A v2 cutover

1. worker와 scheduler를 멈추고 대상 DB 이름을 확인한다.
2. `python scripts/create_v2_database.py --database realty_radar_v2 --confirm-create realty_radar_v2`로 빈 DB에 Alembic head를 적용한다.
3. 한 동 smoke crawl과 MySQL integration test를 수행한다.
4. 수도권 fresh crawl에서 모든 동 `crawl_scope`가 complete인지 확인한다. 실패·truncated 동에는 stale 판정이 일어나면 안 된다.
5. web read DSN과 worker DSN을 v2로 전환한다.
6. 24시간 동안 rollback 가능한 이전 DB를 유지한다.
7. 필요 시 `scripts/retire_v1_tables.py --database <old-db> --confirm-drop <old-db>`를 실행한다. 이 도구는 먼저 날짜가 포함된 dump를 만들고, 명시된 이전 테이블만 DROP한다.

수집 자격 증명은 Playwright context와 `httpx.AsyncClient` 메모리에만 존재한다. 로그, DB, 파일에는 기록하지 않는다.
