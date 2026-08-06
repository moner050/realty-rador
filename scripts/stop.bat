@echo off
chcp 65001 >nul
echo [Realty Radar] Stopping uvicorn process...

taskkill /IM uvicorn.exe /F 2>nul
if %ERRORLEVEL% equ 0 (
    echo [Realty Radar] Stopped successfully.
) else (
    echo [Realty Radar] No process found.
)
