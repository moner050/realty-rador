# README 및 Ubuntu 배포 가이드 문서 업데이트 계획 (readme_and_ubuntu_update_plan.md)

## 1. 개요 및 목적
- Ubuntu/Linux 환경 실행 스크립트(`scripts/start.sh`)를 가상환경(`.venv` 및 `venv`) 자동 인식 및 실행 구조로 최신화.
- `docs/ubuntu_deployment_guide.md` 배포 가이드를 최신 v2 DB (`realty_radar_v2`) 및 패키지 설정에 맞춰 보완.
- `README.md` 프로젝트 메인 문서를 현재 최신 소스 및 Windows/Ubuntu 환경별 초기 설정 가이드를 포함하도록 종합 업데이트.

## 2. 작업 세부 계획
1. `scripts/start.sh` 보완:
   - 가상환경 경로(`.venv/bin/python` 또는 `venv/bin/python`) 자동 감지.
   - `PYTHONPATH=src` 적용 후 오케스트레이터(`scripts/run.py`) 구동.
2. `docs/ubuntu_deployment_guide.md` 업데이트:
   - MySQL 8.4 및 DB명(`realty_radar_v2`) 일치화.
   - 패키지 설치 명령어(`pip install -e .[dev]`) 보완.
   - Systemd 서비스 설정(`realty-radar.service`)의 파이썬 인터프리터 경로 최신화.
3. `README.md` 업데이트:
   - 프로젝트 개요 및 주요 기능/아키텍처.
   - Windows 환경 설치/실행 가이드 (`.venv` 생성, pip 업그레이드, `start.bat` / `start_crawler.bat` / `stop.bat`).
   - Ubuntu 환경 설치/배포 가이드 (`docs/ubuntu_deployment_guide.md` 연동).
   - DB 생성, Alembic 마이그레이션 및 검증 안내.
