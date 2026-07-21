# 6단계 예약 실행 및 작업 큐 프로세스 구축 요약

## 1. 개요
본 문서는 `docs/feature-plan.md` 아키텍처 설계를 바탕으로 **6단계 예약 실행 및 작업 큐 프로세스**를 구축한 기록 문서입니다.

## 2. 주요 구축 모듈
1. **작업 큐 애플리케이션 서비스 (`src/realty_radar/application/crawl_job_service.py`)**:
   - `create_job`: 수동/정기 크롤링 작업 생성 (PENDING)
   - `fetch_next_job`: `FOR UPDATE SKIP LOCKED` 기반으로 대기/재시도 작업을 동시성 안전하게 선점하여 RUNNING으로 전환
   - `mark_job_success` & `mark_job_failure`: 작업 결과 저장 및 지수 백오프(5분 -> 30분 -> 120분) 재시도 관리

2. **Worker 프로세스 (`src/realty_radar/worker`)**:
   - `job_handler.py`: SEARCH/DETAIL 작업 유형별 크롤링 파이프라인 수행
   - `runner.py`: 무한 루프 Polling 및 지능형 딜레이 처리 (`python -m realty_radar.worker`)

3. **Scheduler 프로세스 (`src/realty_radar/scheduler`)**:
   - `scheduler.py`: APScheduler 크론 백그라운드 스케줄러 (`python -m realty_radar.scheduler`)

4. **수집 현황 Web UI (`src/realty_radar/web`)**:
   - `routes/crawl_jobs.py`: GET `/jobs` 및 POST `/api/crawl-jobs`
   - `templates/jobs/index.html`: PENDING, RUNNING, SUCCESS, FAILED 지표 및 작업 대기열 모니터링 테이블 UI

## 3. 검증 결과
- `python -m pytest` 실행 결과 20개 전체 단위 및 통합 테스트 100% 통과 (20/20 passed)
