@echo off
setlocal enabledelayedexpansion

rem Python 기반 프로세스 오케스트레이터 호출 (Terminate batch job 질문 없이 자동 종료 지원)
python scripts/run.py

exit /b %ERRORLEVEL%
