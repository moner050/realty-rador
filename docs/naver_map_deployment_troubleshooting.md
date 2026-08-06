# Ubuntu 서버 네이버 지도 미표시 트러블슈팅 정밀 가이드 (naver_map_deployment_troubleshooting.md)

설정과 등록을 모두 마쳤음에도 불구하고 Ubuntu 서버 배포 환경에서 네이버 지도가 나타나지 않는 경우, 다음 3가지 핵심 원인을 순서대로 점검하세요.

---

## 🔍 Step 1. 백엔드 환경 변수 전달 여부 확인 (페이지 소스 검사)

### 점검 방법:
1. Ubuntu 서버에서 구동 중인 웹 사이트에 접속합니다.
2. 키보드의 **`Ctrl + U`** (페이지 소스 보기)를 누릅니다.
3. 소스 코드 상단 `<head>` 영역에서 아래 문장이 존재하는지 검색(`Ctrl + F`)합니다:
   ```html
   <script src="https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=..." defer></script>
   ```

### 🚨 진단 결과:
- **Case A: 소스 코드에 `maps.js` script 태그 자체가 보이지 않음**
  - **원인**: `.env` 파일에 작성하였더라도 `systemd` 서비스 데몬이 환경 변수를 읽지 못해 백엔드에서 `naver_map_client_id`가 `None`으로 처리된 상태입니다.
  - **해결책**: `/etc/systemd/system/realty-radar.service` 파일에 `EnvironmentFile` 경로를 명시합니다.
    ```ini
    [Service]
    EnvironmentFile=/home/ubuntu/real-estate-search/.env
    ```
    이후 아래 명령어로 데몬을 재시작합니다:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart realty-radar
    ```

---

## 🔍 Step 2. 브라우저 Referer 헤더 차단 여부 확인 (Referrer-Policy)

### 원인 설명:
네이버 지도 API(`oapi.map.naver.com`)는 클라이언트 브라우저가 보낸 HTTP **`Referer` 헤더**를 통해 서비스 등록된 URL인지 대조합니다.
만약 Nginx 역방향 프록시 설정이나 보안 헤더로 인해 `Referrer-Policy: no-referrer`가 설정되어 있으면, 브라우저가 Referer 정보를 지우고 요청을 보내게 되어 네이버 인증 서버가 **403 Forbidden (등록되지 않은 서비스 환경)** 에러를 응답합니다.

### 점검 방법:
1. 브라우저에서 **`F12 (개발자 도구)`** -> **`Console (콘솔)`** 및 **`Network (네트워크)`** 탭을 엽니다.
2. `maps.js` 요청 상태 코드가 **`403 Forbidden`** 인지 확인합니다.
3. 요청 헤더(Request Headers)에 `Referer:` 항목이 포함되어 있는지 확인합니다.

### 🚨 해결책:
- `index.html` 상단에 `<meta name="referrer" content="strict-origin-when-cross-origin">` 설정이 적용되었는지 확인.
- Nginx 설정(`/etc/nginx/nginx.conf` 또는 `/etc/nginx/sites-available/realty-radar`)에서 `Referrer-Policy`를 `no-referrer`로 강제하는 헤더가 있다면 제거 또는 `strict-origin-when-cross-origin`으로 변경 후 `sudo systemctl restart nginx` 실행.

---

## 🔍 Step 3. NCP Client ID 항목 정확도 점검

### 점검 내용:
1. `NAVER_MAP_CLIENT_ID`에 입력한 값에 **공백**이나 **따옴표**가 잘못 포함되지 않았는지 확인.
2. 발급받은 키가 **ncpKeyId**가 맞는지 확인 (NCP 콘솔 -> AI·NAVER API -> Application -> Client ID 복사).
