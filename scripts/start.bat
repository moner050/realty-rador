@echo off
setlocal enabledelayedexpansion

rem 기존 8000번 포트 중복 프로세스 정리
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

rem Launch Python Process Orchestrator
python scripts/run.py

exit /b %ERRORLEVEL%
