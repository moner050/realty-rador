# OS별 Redis 설치 및 설정 계획서 (redis_setup_guide_plan.md)

## 1. 개요
웹 프론트 서버의 지도 로딩 속도 최적화를 위해 Redis 캐시 서버를 Windows 및 Ubuntu 환경에 구축하는 방법과 설정 절차를 정리함.

## 2. 문서 업데이트 계획
1. `README.md`:
   - OS별 (Windows / Ubuntu Linux) Redis 설치 및 가동 명령어 수록.
   - 프로젝트 `.env` 파일의 Redis 관련 환경 변수 설명.
2. `docs/ubuntu_deployment_guide.md`:
   - Ubuntu 서버 배포 가이드 Step 2 패키지 설치 항목에 `redis-server` 및 `systemctl enable redis-server` 반영.
