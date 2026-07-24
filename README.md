# Realty Radar (개인용 부동산 매물 크롤링·필터링·대출평가·시세분석 시스템)

개인 사용자를 위한 고성능 부동산 매물 자동 크롤링, 수집 데이터 정규화, 단지 매칭, 사이트 간 동일 매물 판정, 정부 정책대출 자격 평가 및 실거래가 시세 분석 시스템입니다.

---

## 🚀 주요 기능

- **다중 사이트 매물 자동 수집 (Crawler Adapter)**: Playwright 기반 브라우저 세션 및 지능형 RateLimiter를 통한 안전한 다중 부동산 사이트 매물 자동 수집
- **한국 부동산 특화 정규화 (Normalizer)**: 금액(억/만 원 정수 변환), 면적(공급/전용 분리), 층수, 융자 상태 키워드 분석
- **아파트 단지 결합 및 자동 매칭 엔진 (Complex Matcher)**: `RapidFuzz` 및 주소/세대수/준공연도 기반 가중치 매칭 점수 산출 및 단지 별칭(`complex_alias`) 자동 생성
- **사이트 간 동일 매물 추정 (Listing Dedup)**: 다른 부동산 사이트에 중복 등록된 동일 매물을 가중치 알고리즘으로 자동 판정 및 그룹화
- **정부 정책대출 예상 적격 평가 (Loan Evaluator)**: 내집마련 디딤돌 대출, 버팀목 전세자금 대출 자격 및 개인 소득/무주택 조건 연동 2단계 자동 평가
- **공공 데이터 연동 및 실거래 시세 비교 (Price Comparison)**: 국토교통부 아파트 실거래가 동기화 및 실거래가 대비 급매(is_bargain, 5% 이상 저렴) 분석
- **비동기 멀티 프로세스 작업 큐 (Worker & Scheduler)**: MySQL `FOR UPDATE SKIP LOCKED` 기반 PENDING 작업 동시성 선점 처리 및 APScheduler 자동 주기 예약

---

## 🛠️ 개발 및 실행 환경

- **Language**: Python 3.10+
- **Framework**: FastAPI + Jinja2 + HTMX + Tailwind CSS
- **Database**: MySQL (SQLAlchemy 2.0 ORM & Alembic 마이그레이션)
- **Crawler**: Playwright, Selectolax, RapidFuzz
- **Scheduler & Queue**: APScheduler, Multi-process Worker Runner

---

## ⚙️ OS별 초기 세팅 & 설정 & 실행 가이드 (Step-by-Step)

---

### 🪟 [1] Windows (윈도우 환경)

#### Step 1. 가상환경 생성 및 활성화
```cmd
# 1) 가상환경 생성 (Python 3.10+)
python -m venv venv

# 2) 가상환경 활성화 (CMD / PowerShell)
.\venv\Scripts\activate
```

#### Step 2. 환경 변수 파일 (`.env`) 복사 및 설정
```cmd
# 1) .env.example 복사
copy .env.example .env
```
> `.env` 파일을 열어 MySQL DB 접속 정보 및 관리자 계정 정보를 설정합니다:
```ini
APP_ENV=local
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin1234
SECRET_KEY=realty-radar-secret-key-2026

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=realty_app
MYSQL_PASSWORD=realty_secret_pass
MYSQL_DATABASE=realty_radar
```

#### Step 3. 패키지 설치 및 Playwright 브라우저 설치
```cmd
# 1) pip 최신화 및 패키지 설치 (Editable 모드)
python -m pip install --upgrade pip
python -m pip install -e .

# 2) Playwright 브라우저 다운로드
playwright install
```

#### Step 4. 데이터베이스 마이그레이션 (테이블 생성)
```cmd
python -m alembic upgrade head
```

#### Step 5. 원클릭 시스템 구동
```cmd
.\scripts\start.bat
```
> **종초/종료**: `scripts\stop.bat` 실행 또는 콘솔에서 `Ctrl + C` 입력.

---

### 🐧 [2] Ubuntu / Linux (우분투 / 리눅스 환경)

#### Step 1. 사전 필수 패키지 설치
```bash
# 시스템 라이브러리 및 파이썬 venv 설치
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

#### Step 2. 가상환경 생성 및 활성화
```bash
# 1) 가상환경 생성
python3 -m venv venv

# 2) 가상환경 활성화
source venv/bin/activate
```

#### Step 3. 환경 변수 파일 (`.env`) 복사 및 설정
```bash
# 1) .env.example 복사
cp .env.example .env

# 2) .env 편집 (DB 접속 정보 및 비밀번호 설정)
nano .env
```

#### Step 4. 패키지 설치 및 Playwright OS 디펜던시 설치 (필수)
```bash
# 1) pip 최신화 및 패키지 설치
python3 -m pip install --upgrade pip
python3 -m pip install -e .

# 2) Ubuntu 전용 Playwright OS 시스템 라이브러리 패키지 일괄 설치 (필수)
playwright install --with-deps
```

#### Step 5. 데이터베이스 마이그레이션 (테이블 생성)
```bash
python3 -m alembic upgrade head
```

#### Step 6. 원클릭 시스템 구동
```bash
# 1) 실행 권한 부여 (최초 1회)
chmod +x scripts/start.sh

# 2) 시스템 구동
./scripts/start.sh
# 또는 python3 scripts/run.py
```
> **종료**: 콘솔에서 `Ctrl + C` 입력.

---

### 🌐 웹 접속 및 관리자 포트 안내

> - **메인 웹 인터페이스**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
> - **관리자 로그인**: [http://127.0.0.1:8000/login](http://127.0.0.1:8000/login) (기본 계정: `admin` / `admin1234`)
> - **통합 매물 검색**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
> - **수집 현황 모니터링 (로그인 필수)**: [http://127.0.0.1:8000/jobs](http://127.0.0.1:8000/jobs)
> - **개인 조건 설정 (로그인 필수)**: [http://127.0.0.1:8000/settings](http://127.0.0.1:8000/settings)

---

### 4. 개별 프로세스 세분화 실행 방법

개별 터미널 창에서 독립적으로 각 모듈을 구동할 수도 있습니다.

#### ① Web 서버만 실행:
```bash
python -m uvicorn realty_radar.web.main:app --host 127.0.0.1 --port 8000 --reload
```

#### ② 크롤링 Worker 프로세스만 실행 (작업 큐 Polling):
```bash
python -m realty_radar.worker
```

#### ③ 예약 Scheduler 프로세스만 실행:
```bash
python -m realty_radar.scheduler
```

---

### 5. DB 데이터 재초기화 (리셋) 방법

수집된 데이터베이스 전체 테이블을 안전하게 삭제(Drop) 후 최신 스키마로 재초기화(Migrate)하려면 다음 명령어를 실행합니다.

```bash
python scripts/reset_and_migrate_db.py
```

> **주의**: 이 스크립트를 실행하면 기존 수집된 매물 데이터(`listing`), 단지 정보(`apartment_complex`), 크롤링 작업 이력(`crawl_job`)이 모두 드롭되고 깨끗한 상태로 재초기화됩니다.

---

### 6. CLI 수동 명령 사용 방법

#### ① 크롤링 대상 사이트 로그인 세션 저장:
```bash
python -m realty_radar.cli.login --source SITE_A
```

#### ② 즉시 수동 수집 실행:
```bash
python -m realty_radar.cli.crawl --source SITE_A --region 여의도동
```

---

## 🧪 테스트 실행 (Pytest)

전체 단위 및 통합 테스트를 실행하여 시스템 검증을 수행합니다.

```bash
python -m pytest
```
