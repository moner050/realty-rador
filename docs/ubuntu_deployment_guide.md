# Realty Radar - Ubuntu 클라우드 서버 배포 및 외부 공개 가이드

이 문서는 Realty Radar 서버를 Ubuntu 클라우드 인스턴스(AWS EC2, GCP Compute Engine, Oracle Cloud 등)에 배포하고 외부에 안전하게 공개하기 위한 단계별 설정 가이드입니다.

---

## 📋 1. 작업 개요 및 핵심 요구사항

| 구분 | 주요 설정 및 내용 |
| :--- | :--- |
| **방화벽 설정** | 인바운드 보안 그룹 (80, 443, 22) 및 UFW 설정 |
| **의존성 설치** | Python 3.10+, MySQL, Playwright 리눅스 의존성 라이브러리 |
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
python3 -m venv venv
source venv/bin/activate

# 4) 패키지 설치 및 Playwright 리눅스 의존성 설치
pip install --upgrade pip
pip install -e .
playwright install --with-deps
```

---

### Step 3. 환경 변수 (`.env`) 설정

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

# MySQL 설정 (로컬 MySQL 사용 시)
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=realty_app
MYSQL_PASSWORD=your_secure_password
MYSQL_DATABASE=realty_radar

# 공공 데이터 API 키 등 기타 설정
PUBLIC_DATA_API_KEY=your_api_key
```

#### MySQL DB 및 유저 생성:
```bash
sudo mysql -u root -p
```
```sql
CREATE DATABASE realty_radar CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'realty_app'@'localhost' IDENTIFIED BY 'your_secure_password';
GRANT ALL PRIVILEGES ON realty_radar.* TO 'realty_app'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

#### DB 마이그레이션 실행:
```bash
python3 -m alembic upgrade head
```

---

### Step 4. Systemd 서비스를 이용한 프로세스 데몬화

터미널을 닫아도 백그라운드에서 상시 실행되도록 `systemd` 서비스 등록을 진행합니다.

#### 서비스 파일 생성 (`/etc/systemd/system/realty-radar.service`):
```bash
sudo nano /etc/systemd/system/realty-radar.service
```

다음 내용을 입력합니다 (사용자명 `/home/ubuntu` 경로 확인):

```ini
[Unit]
Description=Realty Radar Multi-Process Service
After=network.target mysql.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/real-estate-search
ExecStart=/home/ubuntu/real-estate-search/venv/bin/python scripts/run.py
Restart=always
RestartSec=5
Environment=PYTHONPATH=/home/ubuntu/real-estate-search/src

[Install]
WantedBy=multi-user.target
```

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
4. **크롤링 및 스케줄러 동시 실행 확인**:
   `/jobs` 모니터링 페이지 및 DB 테이블 상태 검증.

---

## 🛡️ 4. 무차별 보안 스캔(Automated Vulnerability Scan) 로그 원인 및 대응 방안

### 1) 발생 원인
서버가 외부에 노출(공인 IP 오픈)되면 전 세계의 **자동화 보안 스캐너 봇(Shodan, Censys, 봇넷 등)**이 백업 파일(`.env`, `dump.sql`), 인증 키(`.ssh/id_rsa`), 관리자 페이지(`actuator`, `config`) 등의 취약점 유무를 파악하기 위해 무차별 탐색(Scanning) 요청을 보냅니다.
- 로그의 모든 요청이 **`404 Not Found`**로 응답되고 있다면, 애플리케이션에서 해당 민감 파일이 노출되지 않고 **정상 차단**되고 있는 상태입니다.

### 2) 권장 보안 대책
1. **Nginx에서 IP 직접 접근 및 알 수 없는 Host 요청 차단**:
   도메인 없이 IP로 들어오는 봇 스캔을 Nginx `default_server`에서 `444` (응답 없이 연결 종료) 처리.
2. **Fail2ban 도입**:
   짧은 시간 내 연속으로 404/403 에러를 유발하는 IP를 자동으로 IPTables 레벨에서 24시간 동안 차단.
3. **민감 경로 Nginx 차단 규칙 추가**:
   `.env`, `.git`, `.svn` 등 숨김 파일 및 `.sql`, `.bak` 요청을 Nginx 단에서 즉시 404/403 응답 처리하여 백엔드(Python)로 전달되지 않게 방어.

