@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

rem Clean existing port 8000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

rem Detect virtualenv Python
set "PYTHON_CMD=python"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else if exist ".venv\bin\python.exe" (
    set "PYTHON_CMD=.venv\bin\python.exe"
)

rem Launch Python process
%PYTHON_CMD% scripts/run.py

exit /b %ERRORLEVEL%
