# Redis .env 환경변수 설정 및 RESP2 구버전 호환 오류 수정 계획서

## 1. 개요 및 요구사항
- **원인 분석**: 
  1. 최신 `redis-py` 라이브러리가 기본 RESP3 프로토콜의 `HELLO` 명령을 실행하는데, 사용자의 로컬/서버 Redis 버전이 구버전(Redis 5 이하 등)일 경우 `unknown command 'HELLO'` 접속 오류가 발생하며 폴백됨.
  2. Redis 접속 정보(Host, Port, Password, DB)가 코드 내 고정(Hardcoded)되어 있어 환경별 설정 분리가 불가했음.

- **해결 방안**:
  1. `.env` 및 `config.py`에 `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB` 설정 항목 추가.
  2. `redis_client.py` 접속 시 `protocol=2` (RESP2 프로토콜) 옵션을 명시하여 `HELLO` 에러를 원천 차단하고 구버전/신버전 Redis 전 버전에 100% 호환 접속되도록 보정.

---

## 2. 세부 변경 파일 계획

### 1) `.env.example` & `.env`
- Redis 환경 변수 템플릿 추가:
  ```env
  REDIS_HOST=127.0.0.1
  REDIS_PORT=6379
  REDIS_PASSWORD=
  REDIS_DB=0
  ```

### 2) `src/realty_radar/config.py`
- `Settings` 데이터클래스 또는 환경 변수 읽기 유틸리티에 `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB` 속성 추가.

### 3) `src/realty_radar/infrastructure/cache/redis_client.py`
- `config.py`에서 `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB`를 동적으로 받아 접속.
- `redis.Redis(..., protocol=2)`를 지정하여 `unknown command 'HELLO'` 예외 완전 해결.

---

## 3. 검증 계획
- `python -m pytest tests/` 실행을 통한 51개 전체 단위/통합 테스트 검증.
