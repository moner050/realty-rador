@echo off
chcp 65001 > NUL
echo [Realty Radar] 실행 중인 uvicorn 프로세스를 종료합니다...

taskkill /IM uvicorn.exe /F 2>NUL
if %ERRORLEVEL% equ 0 (
    echo [Realty Radar] 정상적으로 종료되었습니다.
) else (
    echo [Realty Radar] 실행 중인 프로세스를 찾지 못했습니다.
)
