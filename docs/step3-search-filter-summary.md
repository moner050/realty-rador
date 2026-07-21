# 3단계 매물 필터링 및 검색 서비스 구축 요약

## 1. 개요
본 문서는 `docs/feature-plan.md` 아키텍처 설계를 바탕으로 **3단계 매물 필터링 및 검색 서비스**를 구축한 기록 문서입니다.

## 2. 주요 구축 모듈
1. **검색 필터 DTO (`src/realty_radar/domain/listing/filters.py`)**:
   - `ListingSearchFilter`: 거래 유형(매매/전세/월세), 매매가/보증금/월세 범위, 전용 면적 범위, 융자 상태(`EXPLICIT_NONE`, `EXPLICIT_EXISTS`, `UNKNOWN`), 키워드 검색, 정렬 조건(`recent`, `price_asc`, `price_desc`, `area_desc`), 페이징 파라미터

2. **매물 검색 애플리케이션 서비스 (`src/realty_radar/application/listing_search_service.py`)**:
   - `ListingSearchService`: DB 인덱스를 활용하는 동적 조건 쿼리 구현
   - 검색 통계 집계: 전체 검색 수, 24시간 내 등록된 신규 매물 수(`new_count`), 가격 변동 이력이 있는 매물 수(`price_reduced_count`)

3. **HTMX 기반 인터렉티브 UI (`src/realty_radar/web`)**:
   - `list_partial.html`: 필터 변경 시 매물 카드 리스트만 비동기로 전달받는 Jinja2 조각 템플릿
   - `index.html`: `hx-get="/listings/search"`, `hx-target="#listings-container"`, `hx-trigger="change delay:300ms, submit"` 연결
   - `routes/home.py`: GET `/` (초기 화면) 및 GET `/listings/search` (HTMX partial 렌더링) 라우터

## 3. 검증 결과
- `python -m pytest` 실행 결과 13개 전체 단위 및 통합 테스트 100% 통과 (13/13 passed)
