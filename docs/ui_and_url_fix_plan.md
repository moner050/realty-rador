# 원본보기 URL 수정, 수집 모니터링 이동 및 고급 필터 접기/펼치기 UI 구현 계획서

## 1. 개편 배경 및 요구사항

1. **네이버 부동산 원본보기 404 URL 오류 수정**:
   - `new.land.naver.com/articles/...` 404 접속 오류를 표준 URL 도메인인 `fin.land.naver.com/articles/...`로 변경 및 보정.
2. **수동 크롤링 실행 버튼 및 수집 진행도 위젯 이동**:
   - 홈 화면(`listings/index.html`)에서 제거 후 수집 현황 페이지(`jobs/index.html`)로 통합 이관.
3. **고급 필터 접기/펼치기(Accordion) 및 요약 뱃지 표기**:
   - 검색창 하단 조절 필터들을 "고급 필터" 패널로 접어두고, 접힌 상태에서는 실시간 적용 중인 필터 요약 텍스트를 소형 폰트로 출력.

---

## 2. 세부 구현 방안

### 1) 원본보기 URL 표준화 ([parser.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/crawler/adapters/site_a/parser.py), [adapter.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/crawler/adapters/site_a/adapter.py), [list_partial.html](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/templates/listings/list_partial.html))
- `SiteAParser.parse_new_article_json` 내 URL 생성 수정:
  `source_url = f"https://fin.land.naver.com/articles/{article_no}"`
- `list_partial.html` 템플릿 URL 보정:
  `href="{{ item.source_url | replace('new.land.naver.com/articles', 'fin.land.naver.com/articles') }}"`

### 2) 크롤링 컨트롤 위젯 이동 ([listings/index.html](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/templates/listings/index.html), [jobs/index.html](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/templates/jobs/index.html))
- 홈 화면에서 `{% include "jobs/progress_partial.html" %}` 및 수동 크롤링 실행 폼 제거.
- 수집 현황 페이지(`jobs/index.html`) 상단 헤더에 수동 크롤링 실행 버튼 및 진행도 위젯 통합 배치.

### 3) 고급 필터 접기/펼치기 패널 및 실시간 요약 텍스트 ([listings/index.html](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/templates/listings/index.html))
- **Accordion 토글 헤더 생성**:
  - 버튼 클릭 시 `advanced-filter-panel` 영역 `hidden` 클래스 토글.
  - 접힌 상태 우측에 `id="filter-summary-badge"` 요약 텍스트 요소 배치.
- **실시간 요약 텍스트 JS 업데이트 (`updateFilterSummaryText()`)**:
  - 가격, 면적, 연식, 세대수, 융자상태, 정책대출 체크 여부를 감지하여 `적용 필터: 15억 이하 • 전용 59㎡(24평) 이상 • 2010년 이후 • 500세대 이상` 형태로 소형 텍스트(`text-xs text-indigo-300 font-medium`)로 실시간 표시.

---

## 3. 검증 계획

1. `python -m pytest tests/`로 51개 테스트 검증.
2. 수집 현황 페이지로 이동된 크롤링 버튼 동작 확인 및 원본보기 URL `fin.land.naver.com` 정상 연결 검증.
