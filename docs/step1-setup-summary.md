# 1단계 프로젝트 기반 구축 완료 요약

## 1. 개요
본 문서는 `docs/feature-plan.md` 아키텍처 설계를 바탕으로 **1단계 프로젝트 기반 구축** 작업을 진행한 마크다운 저장 파일입니다.

## 2. 변경 내용
- **프로젝트 구성**: `pyproject.toml`, `.env`, `.env.example`, `.gitignore`, `README.md` 작성
- **데이터베이스 연동**:
  - 클라우드 MySQL 8.4 연동 환경 설정
  - SQLAlchemy 2.0 ORM 모델 7종 (`CrawlSource`, `CrawlSchedule`, `CrawlJob`, `ApartmentComplex`, `ComplexAlias`, `Listing`, `ListingSnapshot`) 정의
  - Alembic 최초 스키마 마이그레이션 Script (`migrations/versions/2026_07_21_0001-001_initial.py`) 생성
- **웹 서버 & UI**:
  - FastAPI 기반 웹 애플리케이션 (`realty_radar.web.main:app`) 및 `/healthz` API 구현
  - Jinja2 + HTMX + Tailwind CSS 레이아웃 (`base.html`, `index.html`) 구현
- **실행 & 빌드**:
  - Windows 배치 스크립트 (`start.bat`, `stop.bat`)
  - Gradle 빌드/검증 태스크 연동 (`build.gradle`)

## 3. 추후 참고 사항
- 클라우드 MySQL DB 접근 시 `.env` 파일에 작성된 접속 환경변수를 활용함.
- 다음 단계(2단계)에서는 **첫 번째 사이트 Adapter (Playwright/HTTPX 수집기 및 Parser, Normalizer)** 개발을 추진함.
