# Realty Radar v2

SITE_A만 수집하는 MySQL 8.4 매물 검색 서비스입니다. 브라우저는 SITE_A 인증 bootstrap에만 쓰고, 실제 지역·단지·매물 API 요청은 하나의 인증된 `httpx.AsyncClient` connection pool로 처리합니다.

## 데이터 구조

Alembic `001_site_a_v2`가 유일한 canonical migration입니다. 도메인 테이블은 다음 다섯 개뿐입니다.

- `complex_current`: 단지 키워드 FULLTEXT와 공공데이터 보강용
- `listing_current`: 검색 화면이 JOIN 없이 읽는 hot table
- `listing_history`: 실제 변경만 보관하는 append-only cold table
- `crawl_job`: `SKIP LOCKED` lease 기반 SITE_A 작업 큐
- `crawl_scope`: 동 단위 수집 완결성 기록

검색은 정확한 전체 건수와 OFFSET을 제공하지 않습니다. 응답은 `items`, `next_cursor`, `has_more`이며 cursor는 필터 fingerprint에 서명됩니다.

## 새 DB 생성

운영 DB를 자동으로 지우지 않습니다. 빈 v2 DB에만 다음을 실행합니다.

```powershell
python scripts/create_v2_database.py --database realty_radar_v2 --confirm-create realty_radar_v2
```

## Naver Maps

Set `NAVER_MAP_CLIENT_ID` to the NCP Map ID (`ncpKeyId`) issued for Dynamic Map. It is sent only to the browser so map tiles can load. Keep `NAVER_MAP_CLIENT_SECRET` server-side: it is used only by the Geocoding API and is never rendered in listing HTML.

After enabling Dynamic Map and Geocoding in NCP, register each development/production web-service URL. Apply the schema change and then backfill verified complex coordinates:

```powershell
python -m alembic upgrade head
python scripts/backfill_complex_geocodes.py --batch-size 100
```

Listings without a verified coordinate remain visible in search results but are excluded from the map. No client-side or synthetic coordinates are generated.

## Purchase affordability

Purchase affordability uses available cash, existing monthly debt payment, the maximum monthly housing cost, and a closing-cost reserve rate (default 2%). It is a planning estimate based on the current policy-loan rules and a 30-year equal-payment schedule; it does not replace bank approval or statutory acquisition-tax and brokerage-fee calculations.

`MYSQL_DATABASE`의 기본값도 `realty_radar_v2`입니다. 기존 DB 폐기는 전체 coverage와 24시간 rollback 기간이 끝난 뒤에만 `scripts/retire_v1_tables.py`를 명시적으로 실행합니다. 이 스크립트는 먼저 날짜가 포함된 `mysqldump` 백업을 만듭니다.

## 검증

```powershell
python -m pytest -q
python -m alembic upgrade head --sql
```

실제 SITE_A HTTP 검증은 자격 증명·본문을 저장하지 않는 `live` marker와 환경 변수로만 실행합니다.

```powershell
$env:RUN_LIVE_SITE_A_HTTPX='1'
python -m pytest -m live -q
```

Canary 전에는 httpx 전환과 새 스키마의 실환경 성능 개선 수치를 `N/A`로 취급합니다.
