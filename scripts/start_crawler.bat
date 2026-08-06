@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ===================================================
echo  Realty Radar - Crawler Mode
echo  (Worker + Scheduler)
echo ===================================================

set PYTHONPATH=src

rem Detect virtualenv Python
set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else if exist ".venv\bin\python.exe" (
    set "PYTHON_CMD=.venv\bin\python.exe"
)

rem 1. Worker process
echo [1/2] Starting Worker Process...
start "Realty Radar Worker" cmd /k "set PYTHONPATH=src && %PYTHON_CMD% -m realty_radar.worker"

rem 2. Scheduler process
echo [2/2] Starting Scheduler Process...
start "Realty Radar Scheduler" cmd /k "set PYTHONPATH=src && %PYTHON_CMD% -m realty_radar.scheduler"

echo.
echo [Done] Crawler running in background.
pause

exit /b 0
