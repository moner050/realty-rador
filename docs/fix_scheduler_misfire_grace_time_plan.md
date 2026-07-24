# 스케줄러 Misfire 지연 경고 수정 및 Grace Time 보정 계획서

## 1. 개요 및 로그 원인 분석

### 1) 로그 원인
- `Run time of job ... was missed by 0:00:02.031198` 메시지는 APScheduler 스케줄러 구동 시 시스템 초기화 로드 또는 컴퓨터 슬립/부팅 시차로 인해 지정된 06시 정각보다 **약 2초(2.03초) 늦게 job이 트리거되었을 때 발생한 경고(Warning)**입니다.
- APScheduler의 기본 허용 지연 시간(`misfire_grace_time`)이 1초로 짧게 설정되어 있어 2초 지연 시 해당 예정 작업이 취소(스킵)되었음을 알리는 로그입니다.

---

## 2. 해결 방안

### 1) `misfire_grace_time` 및 `coalesce` 옵션 적용
- [scheduler.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/scheduler/scheduler.py):
  - `misfire_grace_time=3600` (1시간): 컴퓨터 부팅 시간차나 2초 남짓의 시스템 지연이 발생하더라도 작업을 취소하지 않고 즉시 정상 실행하도록 허용 유예 시간을 부여함.
  - `coalesce=True`: 누적된 밀린 작업이 있더라도 중복 실행되지 않고 1회만 깔끔하게 구동되도록 지능적 병합 옵션 추가.

---

## 3. 검증 계획
1. `scheduler.py` 수정 후 스케줄러 모듈 구동 테스트.
2. pytest 전체 테스트 검증 통과 확인.
