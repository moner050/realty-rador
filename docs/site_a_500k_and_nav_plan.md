# 작업 계획서: SITE_A 단일화, 50만건 수집, UI 표기 제거 및 상단 네비게이션 연결

## 1. 개요
사용자의 요청에 따라 다음과 같은 요구사항을 반영합니다:
1. 수집 출처를 SITE_A(네이버부동산) 단일 출처로 통합하고, 수집 건수를 기존 1,000개에서 500,000개(50만 개)로 변경.
2. 홈페이지 및 전체 UI에서 'SITE_A'라는 기술적 소스 코드 표기를 제거하고 한글 서비스 명칭("네이버부동산")으로 정돈하거나 숨김.
3. 홈페이지 상단 네비게이션 바(매물 검색, 단지 관리, 수집 현황, 설정)의 클릭 반응이 없는 문제 해결(각 라우트 페이지 연결).

## 2. 세부 구현 내용

### 2.1 대량 수집 및 SITE_A 단일화
- `src/realty_radar/crawler/adapters/site_a/adapter.py`:
  - `count = 500000`으로 변경 및 메모리 절약을 위한 제너레이터/배치 지원 구조 개선.
- `src/realty_radar/application/crawl_pipeline_service.py`:
  - 50만 건 수집 시 대량 데이터의 안정적인 처리와 DB 타임아웃 방지를 위해 Chunk 배치 단위(예: 5,000건) DB Upsert 및 Commit 처리 추가.

### 2.2 SITE_A UI 표기 제거
- `src/realty_radar/web/templates/jobs/index.html`:
  - 셀렉트 박스의 `(SITE_A)` 표기 및 `SITE_B` 선택 옵션 제거.
- `src/realty_radar/web/jinja_filters.py` & `list_partial.html`:
  - 출처 필터 변환 시 `SITE_A` 문구 대신 서비스명("네이버부동산")만 표기.

### 2.3 상단 네비게이션 메인 메뉴 연결
- `src/realty_radar/web/templates/base.html`:
  - '매물 검색' -> `href="/"`
  - '단지 관리' -> `href="/complexes"`
  - '수집 현황' -> `href="/jobs"`
  - '설정' -> `href="/settings"`

## 3. 검증 계획
- 헤더 네비게이션 4개 메뉴의 정상 이동 확인.
- 크롤링 수집 실행 시 50만 건 및 무제한 스트리밍 수집 동작 및 UI 표기 상태 점검.

## 4. 수행 결과 보고
- **상단 네비게이션 링크 연결 완료**: `base.html` 헤더의 '매물 검색'(`href="/"`), '단지 관리'(`href="/complexes"`), '수집 현황'(`href="/jobs"`), '설정'(`href="/settings"`) 메뉴를 각 라우터 페이지 경로에 연결하여 정상 작동하도록 구현하였습니다.
- **UI 내 'SITE_A' 표기 제거**: `jobs/index.html`, `scheduler.py` 등 사용자 인터페이스에 직접 노출되던 기술 명칭('SITE_A')을 제거하고 한글 서비스명("네이버부동산")으로 깔끔히 변경하였습니다.
- **수집 개수 제한 해제 및 제너레이터(Generator) 배치 스트리밍 변환**: `SiteAAdapter`의 매물 생성 메서드를 단일 리스트 대신 `limit=None` 파라미터 기반 무제한 제너레이터 스트림 방식으로 전환하였습니다.
- **DB 배치 Upsert 및 메모리 최적화**: `CrawlPipelineService`에서 5,000건 단위마다 배치 commit을 수행하도록 보완하여 무제한/대량 수집 시 메모리 OOM(Out of Memory) 및 DB Session 타임아웃을 방지하였습니다.
- **전체 테스트 검증**: 총 36개의 유닛 및 통합 테스트(`pytest`)를 수행하여 모두 이상 없이 통과(100% Passed)함을 확인했습니다.
