# MySQL Lock Wait Timeout Exceeded (1205) 오류 분석 및 방지 계획서

## 1. 에러 원인 분석
- **발생 위치**: `POST /api/crawl-jobs/metro` ➔ `CrawlJobService(db).enqueue_metro_batch()` ➔ `db.commit()` (`crawl_job` 75개 레코드 INSERT 처리 시)
- **원인**:
  1. 웹 데이터베이스 세션(`get_db()`)에 `innodb_lock_wait_timeout = 3`초가 지정되어 있어, 락 경합 시 3초 이상 지연되면 `1205 Lock wait timeout exceeded` 에러를 유발합니다.
  2. 동시 실행 중인 스케줄러, Worker 프로세스 또는 타 트랜잭션이 `crawl_job` 테이블에 락(Claim, Lease, Status Update)을 쥐고 있는 상태에서, 웹 세션이 75개 레코드를 단일 트랜잭션으로 일괄 INSERT 하려다 3초 타임아웃을 초과하였습니다.

## 2. 해결 및 방지 대책

### 1) 웹 DB 세션 타임아웃 타당화 (`src/realty_radar/infrastructure/database/session.py`)
- `innodb_lock_wait_timeout`을 기존 3초에서 안정적인 **15초**로 상향 조정하여 순간적인 락 경합 발생 시에도 500 에러 없이 정상 처리되도록 개선.

### 2) 배치 등록 안정성 강화 (`src/realty_radar/application/crawl_job_service.py`)
- `enqueue_metro_batch`에서 이미 큐잉된 동일 batch가 있거나 락 지연 시 안전하게 복구할 수 있도록 예외 핸들링 및 세션 처리 강화.

## 3. 검증 계획
- pytest 단위 및 통합 테스트 실행하여 스케줄러, 배치 등록 및 DB 세션 정상 동작 검증
