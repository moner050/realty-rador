# 2단계 첫 번째 사이트 Adapter 및 수집 파이프라인 구축 요약

## 1. 개요
본 문서는 `docs/feature-plan.md` 아키텍처 설계를 바탕으로 **2단계 첫 번째 사이트 Adapter 및 수집 파이프라인**을 구축한 상세 기록 문서입니다.

## 2. 주요 구축 모듈
1. **크롤러 공통 인터페이스 & 브라우저 세션 관리**:
   - `ListingSourceAdapter` Protocol 인터페이스 (`validate_session`, `search`, `fetch_detail`, `check_availability`)
   - `PlaywrightBrowserManager`: 브라우저 컨텍스트 관리 및 세션 파일(`data/auth/{source_code}.json`) 저장/로드
   - `RateLimiter`: 사이트별 최소 수집 간격 준수

2. **첫 번째 사이트 Adapter (Site A)**:
   - `SiteAParser`: `selectolax` 기반 DOM 카드 및 상세 페이지 파싱
   - `SiteANormalizer`: "6억 5,000만 원" -> `650,000,000` 원화 정수 변환, 면적, 층수("중/25층"), 융자 상태 키워드 분석(`EXPLICIT_NONE`, `EXPLICIT_EXISTS`, `UNKNOWN`)
   - `SiteAAdapter`: 검색 및 수집 흐름 조율

3. **비즈니스 서비스 파이프라인**:
   - `ListingUpsertService`: `listing` 데이터 Upsert 및 가격/융자 변동 발생 시 `listing_snapshot`에 이력 기록
   - `CrawlPipelineService`: `fetch` -> `parse` -> `normalize` -> `persist` 통합 파이프라인

4. **CLI 도구**:
   - `cli/login.py`: 브라우저 수동 로그인 및 쿠키 세션 저장
   - `cli/crawl.py`: 수동 수집 및 DB 연동 실행

## 3. 검증 결과
- `python -m pytest` 실행 결과 8개 단위 및 통합 테스트 100% 통과 (8/8 passed)
