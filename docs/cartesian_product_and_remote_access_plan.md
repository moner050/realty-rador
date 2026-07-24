# SQLAlchemy SAWarning 경고 수정 및 원격 IP 접속 문제 분석 계획서

## 1. 외부/클라우드 IP (74.7.242.63) 접속 불가 원인 분석 및 해결 방안

### 원인 분석
- **로컬 실행 서버 설정 문제**: Uvicorn 실행 시 `--host 127.0.0.1`로 구동하면 로컬 루프백 인터페이스만 바인딩되므로 external IP(74.7.242.63 등)나 타 장치에서 연결할 수 없습니다.
- **원격 클라우드 서버 서비스 상태 문제**: 74.7.242.63이 우분투 클라우드 서버인 경우, uvicorn/systemd 프로세스가 정지되어 있거나 방화벽(UFW 또는 클라우드 인바운드 보안 그룹 80/8000 포트)이 차단되어 있을 가능성이 큽니다.

### 해결 방안
- 외부 접속을 허용하려면 `--host 0.0.0.0` 바인딩을 사용해야 합니다.
- 원격 서버인 경우 UFW 및 보안 그룹 포트(80, 8000)를 개방하고 uvicorn 데몬 상태를 점검합니다.

---

## 2. SQLAlchemy Cartesian Product 경고 (SAWarning) 원인 분석 및 수정

### 원인 분석
- `listing_search_service.py` L523의 `count_stmt = select(func.count(Listing.id)).select_from(stmt.order_by(None))` 문장에서 `stmt`를 `.subquery()`로 명시하지 않아 `anon_1`과 `listing` 테이블 간 Cartesian Product 경고가 발생합니다.

### 수정 계획
- `src/realty_radar/application/listing_search_service.py` 파일의 L523 `count_stmt` 조회를 `select(func.count()).select_from(stmt.order_by(None).subquery())` 형태로 변경하여 서브쿼리 조회가 안전하게 수행되도록 수정합니다.

---

## 검증 계획
- Gradle/Pytest 기반 단위 및 통합 테스트 수행.
