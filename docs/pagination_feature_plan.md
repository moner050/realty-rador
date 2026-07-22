# 작업 계획서: 홈 화면 매물 목록 페이지네이션 기능 구현

## 1. 개요
현재 홈 화면 매물 목록 하단에 페이지 이동 버튼 및 페이지 정보가 노출되지 않아 매물 조회가 1페이지에 고정되는 문제를 해결합니다.

## 2. 세부 구현 계획

### 2.1 검색 결과 모델 개선 (`SearchResult`)
- 위치: `src/realty_radar/domain/listing/models.py`
- `SearchResult`에 `page`, `page_size`, `total_pages`, `has_prev`, `has_next` 속성 추가.

### 2.2 검색 서비스 연동 (`ListingSearchService`)
- 위치: `src/realty_radar/application/listing_search_service.py`
- `SearchResult` 반환 시 `page=params.page`, `page_size=params.page_size` 값 전달.

### 2.3 UI 템플릿 개선 (`list_partial.html` & `index.html`)
- 위치: `src/realty_radar/web/templates/listings/list_partial.html`, `index.html`
- 하단 페이지네이션 컴포넌트 추가:
  - 이전/다음 버튼
  - 1 2 3 ... 페이지 번호 직관적 선택 버튼
  - HTMX `hx-include="#search-filter-form"`을 통해 필터 조건 유지 상태로 비동기 갱신.

## 3. 검증 계획
- `pytest tests/unit/test_models.py tests/integration/test_web_search_htmx.py` 검증.
- 매물 페이지네이션 이동 및 UI 동작 테스트.

## 4. 수행 결과 보고
- **검색 결과 DTO 모델 개선**: `SearchResult` 클래스에 `page`, `page_size`, `total_pages`, `has_prev`, `has_next` 속성을 구현하였습니다.
- **검색 서비스 연동**: `ListingSearchService.search_listings()` 결과 반환 시 `page`와 `page_size` 값을 바인딩하여 정확한 총 페이지 수가 산출되도록 보완했습니다.
- **페이지네이션 UI 컨트롤 구현**: `list_partial.html` 하단에 이전/다음 버튼 및 페이지 번호(1, 2, 3...) 직접 이동 버튼을 배치하고 HTMX `hx-include="#search-filter-form"`을 연동하여 선택된 필터 조건이 유지된 채 비동기로 페이지 목록이 갱신되도록 하였습니다.
- **테스트 검증**: 39개 전체 유닛 및 통합 테스트를 수행하여 오류 없이 성공(`39 passed`)함을 확인하였습니다.
