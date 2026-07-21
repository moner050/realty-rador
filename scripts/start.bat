@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ===================================================
echo  Realty Radar Multi-Process System Starting...
echo ===================================================

rem Set PYTHONPATH to include src directory
set PYTHONPATH=src

rem Check .env file
if not exist .env (
    echo [.env] File not found. Please create .env based on .env.example
    exit /b 1
)

echo 1. Starting Worker Process...
start "Realty Radar Worker" cmd /k "set PYTHONPATH=src && python -m realty_radar.worker"

echo 2. Starting Scheduler Process...
start "Realty Radar Scheduler" cmd /k "set PYTHONPATH=src && python -m realty_radar.scheduler"

echo 3. Starting FastAPI Web Server (http://127.0.0.1:8000)...
python -m uvicorn realty_radar.web.main:app --host 127.0.0.1 --port 8000 --reload
