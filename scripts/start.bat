@echo off
setlocal enabledelayedexpansion

rem Launch Python Process Orchestrator
python scripts/run.py

exit /b %ERRORLEVEL%
