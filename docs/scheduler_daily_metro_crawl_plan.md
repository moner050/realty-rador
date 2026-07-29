# 매일 06시 수도권 전체 정기 스크래핑 스케줄러 개선 계획서

## 1. 개요 및 현재 문제점 분석
- **현재 스케줄러 상태**: `TaskScheduler`가 실행 시 APScheduler를 통해 `CronTrigger("0 6 * * *")` 스케줄을 등록하고 있으나, 기존 `schedules.py`의 `schedule_regular_search_job` 함수가 단 1개의 시도 scope(`1100000000`)만 `create_job`으로 등록하도록 구현되어 있었습니다.
- **개선 필요 사항**: 안내 및 주석에 기재된 대로 "매일 06시 수도권 전체(서울·경기·인천 전체 시/군/구) 정기 수집"이 정상 작동하도록 `CrawlJobService.enqueue_metro_batch()`를 호출하여 실제 전체 수도권 시군구 배치 job이 등록되도록 수정합니다.

## 2. 세부 수정 계획

### 1) `src/realty_radar/scheduler/schedules.py`
- 기존 단일 scope `create_job` 대신 수도권 전체 시/군/구 정기 수집 배치를 등록하는 `enqueue_metro_batch()` 호출로 개선.

### 2) `src/realty_radar/scheduler/scheduler.py`
- 크론 트리거 실행 및 예외 처리 로깅 보강.
- 매일 오전 06:00 (Cron: `0 6 * * *`) 스케줄링 설정 유지 및 로깅 명확화.

## 3. 검증 계획
- `pytest tests/unit/test_scheduler.py` 또는 관련 스케줄러 실행 단위 테스트 작성 및 통과 검증
