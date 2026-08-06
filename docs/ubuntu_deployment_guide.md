# Realty Radar - Ubuntu 클라우드 서버 배포 및 외부 공개 가이드

이 문서는 Realty Radar 서버를 Ubuntu 클라우드 인스턴스(AWS EC2, GCP Compute Engine, Oracle Cloud 등)에 배포하고 외부에 안전하게 공개하기 위한 단계별 설정 가이드입니다.

---

## 📋 1. 작업 개요 및 핵심 요구사항

| 구분 | 주요 설정 및 내용 |
| :--- | :--- |
| **방화벽 설정** | 인바운드 보안 그룹 (80, 443, 22) 및 UFW 설정 |
| **의존성 설치** | Python 3.10+, MySQL 8.4, Playwright 리눅스 의존성 라이브러리 |
| **웹 서버 설정** | Nginx 역방향 프록시 (127.0.0.1:8000 ↔ 80/443 외부 포트) |
| **보안 (SSL)** | Let's Encrypt (Certbot)을 통한 HTTPS 무료 보안 서명 적용 |
| **프로세스 관리** | `systemd` 데몬을 통한 서버 재부팅 시 자동 실행 및 시스템 상시 유지 |

---

## 🚀 2. 단계별 배포 순서

### Step 1. 클라우드 방화벽 (보안 그룹) 및 UFW 설정

#### 1) 인프라 보안 그룹 (Security Group / Inbound Rules)
사용 중인 클라우드 콘솔(AWS, GCP, Oracle Cloud 등)의 보안 그룹 설정에서 아래 포트를 허용합니다.
- **SSH**: `22` (포트)
- **HTTP**: `80` (포트)
- **HTTPS**: `443` (포트)

#### 2) Ubuntu UFW 방화벽 설정
```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

---

### Step 2. 서버 패키지 및 파이썬 가상환경 구축

```bash
# 1) 시스템 업데이트 및 필수 패키지 설치
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx mysql-server

# 2) 저장소 클론 (또는 소스 코드 업로드)
cd /home/ubuntu
git clone <YOUR_REPOSITORY_URL> real-estate-search
cd real-estate-search

# 3) 파이썬 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 4) pip 업그레이드 및 개발/운영 패키지 설치
python3 -m pip install --upgrade pip
pip install -e .[dev]
playwright install --with-deps
```

---

### Step 3. 환경 변수 (`.env`) 설정 및 데이터베이스 초기화

`.env` 파일을 생성하고 MySQL DB 정보 및 시크릿 키, 바인딩 설정을 작성합니다.

```bash
cp .env.example .env
nano .env
```

```ini
APP_ENV=production
APP_HOST=127.0.0.1
APP_PORT=8000

SECRET_KEY=realty-radar-prod-secret-key-change-this

# MySQL 설정 (로컬 MySQL 8.4 사용 시 기본 DB: realty_radar_v2)
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=realty_app
MYSQL_PASSWORD=your_secure_password
MYSQL_DATABASE=realty_radar_v2

# 네이버 지도 API ID (클라이언트용)
NAVER_MAP_CLIENT_ID=your_ncp_client_id
NAVER_MAP_CLIENT_SECRET=your_ncp_client_secret
```

#### MySQL DB 및 유저 생성:
```bash
sudo mysql -u root -p
```
```sql
CREATE DATABASE realty_radar_v2 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'realty_app'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON realty_radar_v2.* TO 'realty_app'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

#### DB 자동 생성 및 마이그레이션 실행:
```bash
# 1) v2 데이터베이스 스키마 생성
python3 scripts/create_v2_database.py --database realty_radar_v2 --confirm-create realty_radar_v2

# 2) Alembic 마이그레이션 실행
python3 -m alembic upgrade head

# 3) 단지 지오코딩 보강 (선택 사항)
python3 scripts/backfill_complex_geocodes.py --batch-size 100
```

---

### Step 4. Systemd 서비스를 이용한 프로세스 데몬화

터미널을 닫아도 백그라운드에서 상시 실행되도록 `systemd` 서비스 등록을 진행합니다.

#### 서비스 파일 생성 (`/etc/systemd/system/realty-radar.service`):
```bash
sudo nano /etc/systemd/system/realty-radar.service
```

다음 내용을 입력합니다 (`/home/ubuntu` 경로 확인):

```ini
[Unit]
Description=Realty Radar Web Server Service
After=network.target mysql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/real-estate-search
ExecStart=/home/ubuntu/real-estate-search/.venv/bin/python scripts/run_web_only.py
Restart=always
RestartSec=5
Environment=PYTHONPATH=/home/ubuntu/real-estate-search/src

[Install]
WantedBy=multi-user.target
```

> **⚠️ 하이브리드 운영 참고**: 네이버 부동산 차단을 방지하기 위해 크롤러(Worker/Scheduler)는 **로컬 Windows PC**에서 실행하고, 클라우드 Ubuntu 서버에서는 웹 서버만 구동합니다.
> - **Ubuntu (클라우드)**: `run_web_only.py` (웹 서버만 상시 구동) 또는 `./scripts/start.sh`
> - **Windows (로컬 PC)**: `.\scripts\start_crawler.bat` (크롤러만 구동하여 클라우드 DB로 직접 저장)

#### 서비스 등록 및 구동:
```bash
sudo systemctl daemon-reload
sudo systemctl enable realty-radar
sudo systemctl start realty-radar

# 상태 확인
sudo systemctl status realty-radar
```

---

### Step 5. Nginx 역방향 프록시 (Reverse Proxy) 및 SSL 적용

Nginx를 앞단에 두어 `80/443` 외부 요청을 내부 `127.0.0.1:8000`으로 안전하게 전달합니다.

#### 1) Nginx 설정 파일 생성:
```bash
sudo nano /etc/nginx/sites-available/realty-radar
```

```nginx
server {
    listen 80;
    server_name your-domain.com; # 도메인이 없는 경우 서버 공인 IP 입력

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### 2) 심볼릭 링크 생성 및 Nginx 재시작:
```bash
sudo ln -s /etc/nginx/sites-available/realty-radar /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

#### 3) HTTPS Certbot SSL 적용 (도메인 연결 시):
```bash
sudo certbot --nginx -d your-domain.com
```

---

## 🔍 3. 정상 동작 검증 및 점검 체크리스트

1. **서비스 상태 확인**:
   ```bash
   sudo systemctl status realty-radar
   ```
2. **로그 확인**:
   ```bash
   sudo journalctl -u realty-radar -f
   ```
3. **외부 웹 접속 검증**:
   브라우저에서 `http://<서버_공인_IP>` 또는 `https://your-domain.com` 접속 확인.
4. **수동 실행 검증**:
   ```bash
   chmod +x scripts/start.sh
   ./scripts/start.sh
   ```

---

## 🛡️ 4. 무차별 보안 스캔 대응 방안

1. **Nginx에서 IP 직접 접근 및 알 수 없는 Host 요청 차단**:
   도메인 없이 IP로 들어오는 봇 스캔을 Nginx `default_server`에서 `444` (응답 없이 연결 종료) 처리.
2. **Fail2ban 도입**:
   짧은 시간 내 연속으로 404/403 에러를 유발하는 IP를 IPTables 레벨에서 자동 차단.
3. **민감 경로 차단**:
   `.env`, `.git`, `.sql` 요청을 Nginx 단에서 즉시 차단.
