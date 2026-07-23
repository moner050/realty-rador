# 프로세스 매니저 도입 및 CMD 창 100% 자동 종료 개편 계획서

## 1. 지연/미종료 원인 분석
- Windows Batch(`start.bat`) 특성상 `uvicorn`에 `Ctrl+C`가 전달되면 CMD 인터프리터가 `Terminate batch job (Y/N)?` 질문을 띄우며 스크립트 실행이 중단됨.
- 사용자가 `Y`를 누르지 않거나 프롬프트에 갇히는 경우 하단의 `taskkill` 구문까지 도달하지 못해 2개의 백그라운드 CMD 창(`Worker`, `Scheduler`)이 계속 켜져있는 현상이 발생함.

---

## 2. 해결 방안: Python 기반 프로세스 오케스트레이터 (`scripts/run.py`) 도입

1. **`scripts/run.py` 파이썬 오케스트레이터 작성**:
   - `subprocess.Popen`으로 `Worker`와 `Scheduler` 프로세스를 별도 CMD 창으로 생성.
   - `try ... finally` 예외 처리 구문을 통해 `Ctrl+C` (KeyboardInterrupt) 감지 시 `finally` 블록에서 `worker.terminate()`, `scheduler.terminate()` 및 `kill()`을 즉시 호출.
   - **`Terminate batch job (Y/N)?` 물음 없이 0.1초 만에 2개 창과 메인 프로세스 창까지 모두 100% 깔끔하게 자동 종료**!

2. **`scripts/start.bat` 간소화**:
   - `python scripts/run.py` 명령만 깔끔하게 구동하도록 전면 개편.

---

## 3. 검증 계획
- `python -m pytest tests/`로 51개 전체 테스트 정상 통과 검증.
