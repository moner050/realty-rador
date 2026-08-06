# Realty Radar v2

SITE_A 매물을 수집하고 검색하는 MySQL 8.4 기반 부동산 매물 필터링 및 오케스트레이션 시스템입니다. 브라우저는 SITE_A 인증 bootstrap에만 사용하며, 실제 지역·단지·매물 API 요청은 하나의 인증된 `httpx.AsyncClient` connection pool로 신속하게 처리합니다.

---

## 🏗️ 아키텍처 및 데이터 구조

Alembic `001_site_a_v2`가 유일한 canonical migration입니다. 주요 도메인 테이블은 다음과 같습니다.

- `complex_current`: 단지 키워드 FULLTEXT 검색 및 공공데이터 보강용 데이터
- `listing_current`: 검색 화면이 JOIN 없이 읽는 Hot 테이블
- `listing_history`: 변경 이력만 보관하는 Append-only Cold 테이블
- `crawl_job`: `SKIP LOCKED` lease 기반 SITE_A 작업 큐
- `crawl_scope`: 동 단위 수집 완결성 기록

---

## ⚡ Redis 캐시 서버 설정 가이드 (지도 속도 최적화)

지도 뷰포트 검색 결과를 초고속(1~5ms)으로 처리하기 위해 프론트(웹) 서버에 Redis 구축을 권장합니다.

### 1. Windows 환경 Redis 설정

#### 1) Redis 설치 (택 1)
- **방법 A: Windows 포팅 설치 파일 (권장)**
  - [tporadowski/redis GitHub Releases](https://github.com/tporadowski/redis/releases)에서 `Redis-x64-5.0.14.1.msi` 또는 `.zip`을 다운로드하여 설치합니다.
- **방법 B: Memurai (Windows 전용 Redis)**
  - Windows 서비스 환경 전용인 Memurai(Developer Edition)를 공식 웹사이트에서 다운로드하여 설치합니다.

#### 2) 서비스 등록 및 가동
```powershell
# Windows 서비스로 등록 및 시작 (설치 폴더 이동 후)
redis-server --service-install
redis-server --service-start

# 동작 확인 (PONG 응답 확인)
redis-cli ping
```

---

### 2. Ubuntu / Linux 환경 Redis 설정

#### 1) 저장소 업데이트 및 패키지 설치
```bash
sudo apt update
sudo apt install -y redis-server
```

#### 2) Redis 바인딩 및 systemd 서비스 설정
```bash
sudo nano /etc/redis/redis.conf
```
- `supervised no` 구문을 `supervised systemd`로 변경합니다.

#### 3) 서비스 등록 및 자동 구동
```bash
sudo systemctl enable redis-server
sudo systemctl restart redis-server

# 상태 확인
sudo systemctl status redis-server
```

---

### 3. 프로젝트 `.env` 환경 변수 설정

`.env` 파일에 Redis 접속 정보를 설정합니다 (미설정 시 자동으로 DB 모드로 작동함).

```ini
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
```

---

## 🛠️ 환경별 초기 설정 및 실행 가이드

### 1. Windows 환경 초기 설정 및 실행

#### 1) 가상환경 생성 및 pip 업그레이드
```powershell
# 가상환경 생성 (.venv)
python -m venv .venv

# 가상환경 pip 업그레이드 및 패키지 설치
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -e .[dev]

# Playwright 브라우저 라이브러리 설치
.\.venv\Scripts\playwright.exe install
```

#### 2) 스크립트를 통한 서버 구동 및 종료
- **통합 시스템 실행 (웹서버 + 크롤러 Worker + Scheduler)**:
  ```powershell
  .\scripts\start.bat
  ```
- **크롤러 전용 모드 실행 (웹서버 제외, Worker + Scheduler만 실행)**:
  ```powershell
  .\scripts\start_crawler.bat
  ```
- **실행 중인 서버 프로세스 정지**:
  ```powershell
  .\scripts\stop.bat
  ```

---

### 2. Ubuntu / Linux 환경 초기 설정 및 배포

Ubuntu 클라우드 서버 배포에 대한 상세 단계별 가이드는 [docs/ubuntu_deployment_guide.md](file:///c:/workspace/personal/real-estate-search/docs/ubuntu_deployment_guide.md) 문서를 참고하세요.

#### 1) 파이썬 가상환경 생성 및 패키지 설치
```bash
# 가상환경 생성 (.venv)
python3 -m venv .venv
source .venv/bin/activate

# pip 업그레이드 및 의존성 설치
python3 -m pip install --upgrade pip
pip install -e .[dev]
playwright install --with-deps
```

#### 2) Ubuntu 전용 자동 실행 스크립트
```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

---

## 🗄️ 데이터베이스 생성 및 마이그레이션

기본 DB명은 `realty_radar_v2`입니다. 신규 데이터베이스 구축 시 다음 명령어를 실행합니다.

```powershell
# 1. 새 v2 데이터베이스 생성
python scripts/create_v2_database.py --database realty_radar_v2 --confirm-create realty_radar_v2

# 2. Alembic 마이그레이션 적용
python -m alembic upgrade head

# 3. 단지 좌표 지오코딩 보강 (선택)
python scripts/backfill_complex_geocodes.py --batch-size 100
```

---

## 🗺️ 네이버 지도 (Naver Maps) API 설정

1. `NAVER_MAP_CLIENT_ID`: NCP Dynamic Map 발급 Client ID (`ncpKeyId`). 브라우저 지도 타일 로드용으로 전달됩니다.
2. `NAVER_MAP_CLIENT_SECRET`: 서버 측 지오코딩(Geocoding API) 전용 비밀키입니다 (HTML에 노출되지 않음).

---

## 🧪 검증 및 테스트

### Gradle 기반 검증
```powershell
# pytest 및 ruff 검증 실행
./gradlew check
```

### Pytest 수동 실행
```powershell
# 단위 및 통합 테스트 실행
python -m pytest -q

# 마이그레이션 SQL 검증
python -m alembic upgrade head --sql

# 실제 SITE_A HTTP 연동 검증 (자격 증명 설정 필요)
$env:RUN_LIVE_SITE_A_HTTPX='1'
python -m pytest -m live -q
```
