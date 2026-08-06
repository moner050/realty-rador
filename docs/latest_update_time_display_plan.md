# 최신 데이터 갱신 시각 표시 계획서 (latest_update_time_display_plan.md)

## 1. 개요
데이터의 수집/갱신 시점을 사용자가 바로 알아볼 수 있도록 사이트 상단 타이틀 영역에 최신 갱신 기준 일시를 표기하는 기능 추가.

## 2. 변경 파일
1. `src/realty_radar/web/routes/home.py`: DB 최신 갱신 일시 조회 헬퍼 `_latest_data_update_time(db)` 추가 및 템플릿 전달.
2. `src/realty_radar/web/templates/listings/index.html`: 상단 헤더 타이틀 영역에 `🕒 2026.08.06 14:55 기준` 배지 표기.
