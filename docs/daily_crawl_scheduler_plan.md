# 매일 06시 전체 지역(서울, 경기, 인천) 자동 스크래핑 배치 스케줄 개편 계획서

## 1. 개요 및 변경 목적
- **현상**: 기존 스케줄러(`scheduler.py`)가 6시간마다(`0 */6 * * *`) `"여의도동"` 단일 동 지역에 대해서만 수집 작업을 등록하고 있었음.
- **요구사항**: 매일 아침 06시(`0 6 * * *`)에 서울, 경기, 인천 전체 지역(`ALL_METRO`)을 자동으로 100배 고속 수집하도록 스케줄 및 태스크 수정.

---

## 2. 세부 변경 사항

### 1) `src/realty_radar/scheduler/schedules.py`
- `schedule_regular_search_job` 기본 파라미터 `region_name`을 `"여의도동"`에서 **`"ALL_METRO"`** (서울, 경기, 인천 전체)로 변경.

### 2) `src/realty_radar/scheduler/scheduler.py`
- APScheduler 크론 스케줄 표현식을 `0 */6 * * *`에서 **`0 6 * * *` (매일 오전 06시 정각)** 으로 개편.
- 예약 작업 호출 파라미터를 `kwargs={"source_code": "SITE_A", "region_name": "ALL_METRO"}` 로 세팅하여 전역 수집 자동 구동.

---

## 3. 검증 계획
- `python -m pytest tests/` 구동을 통한 전체 51개 단위/통합 테스트 검증.
