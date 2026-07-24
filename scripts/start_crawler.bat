@echo off
setlocal enabledelayedexpansion

rem ============================================
rem  로컬 크롤러 전용 실행 스크립트
rem  - Worker + Scheduler만 실행 (웹서버 제외)
rem  - 클라우드 DB에 직접 연결하여 데이터 수집
rem ============================================

echo ===================================================
echo  Realty Radar - 로컬 크롤러 전용 모드
echo  (웹서버 없이 Worker + Scheduler만 실행)
echo ===================================================

set PYTHONPATH=src

rem 1. Worker 프로세스 실행
echo [1/2] Worker 프로세스 시작...
start "Realty Radar Worker" cmd /k "set PYTHONPATH=src && python -m realty_radar.worker"

rem 2. Scheduler 프로세스 실행
echo [2/2] Scheduler 프로세스 시작...
start "Realty Radar Scheduler" cmd /k "set PYTHONPATH=src && python -m realty_radar.scheduler"

echo.
echo [완료] 크롤러가 백그라운드에서 실행 중입니다.
echo  - Worker: 수집 작업 처리
echo  - Scheduler: 매일 06시 자동 수집 예약
echo.
echo  종료하려면 열린 CMD 창을 닫으세요.
pause

exit /b 0
