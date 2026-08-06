# 실행 스크립트 및 환경 수정 작업 기록 (execution_fix_plan.md)

## 작업 목표
- 배치 스크립트(`start.bat`, `start_crawler.bat`, `stop.bat`) 실행 시 발생하는 구문 및 인코딩 오류 해결.
- `ModuleNotFoundError: No module named 'uvicorn'` 및 파이썬 가상환경 미사용 문제 해결.
- Gradle 기반 빌드/검증 환경 점검.

## 원인 분석
1. **CMD 인코딩 문제**: UTF-8 BOM 및 멀티바이트 문자셋 해석 문제로 인해 `setlocal enabledelayedexpansion`이 `edexpansion`으로 잘려서 인식됨.
2. **파이썬 실행 경로 문제**: 배치 파일에서 `.venv` 가상환경 대신 글로벌 Python이 호출되어 설치된 라이브러리(`uvicorn` 등)를 인식하지 못함.

## 작업 상세 내용
1. `scripts/start.bat`: `chcp 65001 >nul` 설정 추가 및 `.venv` 파이썬 자동 탐색 로직 적용.
2. `scripts/start_crawler.bat`: `.venv` 가상환경 파이썬 사용 및 `chcp 65001` 적용.
3. `scripts/stop.bat`: 프로세스 포트 정리 로직 안정화 및 인코딩 고치기.
4. 가상환경 의존성 동기화 (`.venv` 패키지 설치 확인).
5. Gradle을 사용한 검증 수행.
