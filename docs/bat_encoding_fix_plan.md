# start.bat 인코딩 구문 파싱 오류 수정 계획서

## 1. 원인 분석
- Windows CMD 및 PowerShell에서 batch (`.bat`) 파일을 실행할 때 UTF-8 멀티바이트 한글 주석(`rem`) 및 `echo` 구문이 CP949 해석기에서 깨지면서 명령어(`''`, `'WINDOWTITLE'` 등)로 잘못 파싱되는 에러 발생.

---

## 2. 해결 방안
- [scripts/start.bat](file:///c:/workspace/personal/real-estate-search/scripts/start.bat) 파일 내의 배치 처리 구문 메시지를 CMD/PowerShell 100% 호환 표준 구문 구조로 개편.
- 특수문자 및 멀티바이트 인코딩 깨짐을 예방하여 구문 에러 없이 `start.bat`이 100% 완벽히 구동되고, 서버 종료 시 CMD 창들이 일괄 자동 닫히도록 완수.

---

## 3. 검증 계획
- `python -m pytest tests/` 구동을 통해 전체 테스트 정상 동작 검증.
