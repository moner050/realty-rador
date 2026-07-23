# 서버 종료 시 CMD 창 자동 일괄 닫힘 개편 계획서

## 1. 개요 및 요구사항
- **현상**:
  - `scripts/start.bat` 구동 시 `Worker` 및 `Scheduler` 백그라운드 창이 `cmd /k` 옵션으로 띄워져 있어, Web 서버 프로세스가 종료되어도 창들이 닫히지 않고 프롬프트 상태로 남아있었음.
- **목표**:
  - 웹 서버가 종료되거나 사용자가 종료할 때 `Worker`, `Scheduler` 프로세스 창 및 메인 CMD 창까지 모두 한꺼번에 깔끔하게 자동으로 닫히도록(`exit`) 스크립트 튜닝.

---

## 2. 세부 변경 계획 (`scripts/start.bat`)

1. **`cmd /c` 자식 프로세스 자동 창 닫힘 모드 지정**:
   - Worker 및 Scheduler 실행 시 `cmd /c` 옵션 적용.
2. **서버 종료 시 연관 CMD 창 일괄 강제 종료 및 메인 창 자동 exit**:
   - `uvicorn` 실행 종료 직후 `taskkill /FI "WINDOWTITLE eq Realty Radar*" /F >nul 2>&1` 실행.
   - `exit 0` 구문을 추가하여 메인 CMD 창까지 1초의 대기 없이 자동으로 완전히 닫히도록 구성.

---

## 3. 검증 계획
- `python -m pytest tests/`로 51개 전체 테스트 정상 실행 검증.
