# 8대 기능 개선 및 Redis 캐시 도입 통합 계획서

## 1. 개요 및 요구사항 정의

본 계획서는 부동산 검색 및 크롤링 시스템의 사용자 편의성 향상, 필터 버그 수정, 수집/조회 속도 극대화를 위한 **8대 통합 개선 계획서**입니다.

---

## 2. 8대 개선 항목별 기술 상세 계획

### 1) 수동 크롤링 지역 선택 기능 추가 (전체 / 서울 / 경기 / 인천)
- **위치**: `jobs/index.html` 수동 크롤링 폼
- **방안**: 
  - 수동 크롤링 폼에 드롭다운 셀렉트 박스 추가: `ALL_METRO` (서울/경기/인천 전체), `서울특별시`, `경기도`, `인천광역시`.
  - 선택한 지역이 `crawl_jobs.py` 라우터로 전달되어 해당 지역만 타겟팅 수집 실행.

### 2) 고급필터 영역 전체 클릭 접기/펼치기 개선
- **위치**: `listings/index.html`
- **방안**: 
  - `advanced-filter-header` 전체 영역에 `cursor-pointer` 및 `onclick="toggleAdvancedFilters()"` 이벤트 부여.
  - 내부 자식 요소 클릭 시 이벤트 버블링 문제없이 전체 바 클릭 시 Accordion 토글 구동.

### 3) 검색 시 페이지 번호 1페이지 자동 리셋
- **위치**: `listings/index.html`
- **방안**: 
  - 검색어 입력 후 검색 버튼 클릭, 거래유형 변경, 시/도 선택 변경 시 JS에서 `document.getElementById('filter-page').value = 1;` 을 강제 호출하여 이전 3페이지 고정 현상 완전 해결.

### 4) 정렬 스위처 위치 이동 (상단 스티키 바 배치)
- **위치**: `listings/index.html` -> `listings/list_partial.html`
- **방안**: 
  - 검색 결과 목록 상단의 스티키 서머리 바(`sticky top-16`) 우측으로 정렬 스위처(`filter-sort-by`)를 이동 배치하여 스크롤 시에도 항상 고정 노출.

### 5) 단기임대 매물 자동 식별 및 필터링 기능 구현
- **위치**: `normalizer.py`, `models/listing.py`, `search_service.py`, `index.html`, `list_partial.html`
- **방안**:
  - **식별 로직**: 설명문구(`description_raw`)에 "단기", "단기임대", "깔세", "월세선납", "1개월", "지분" 등이 포함되거나, 매매 거래인데 보증금/가격이 3,000만원 이하인 경우 `is_short_term = True` 판정.
  - **UI 표기**: 매물 카드에 **"단기임대"** 주황색 뱃지 표기.
  - **검색 필터**: `exclude_short_term` (단기임대 제외, 기본값 ON) 필터 옵션 추가하여 매매/전세 검색 시 노이즈 제거.

### 6) 지역 필터 불일치 / 격리 오류 완전 수정
- **위치**: `search_service.py`, `advanced_filter.py`
- **원인 분석**: `region_name` 검색 시 `ApartmentComplex.sigungu` / `dong` 과 `Listing.address_raw` 조인 시 `OR` 조건이나 Partial Match로 인해 서울 선택 시 고양시 매물이 섞이는 현상.
- **해결 방안**:
  - `sido`, `sigungu`, `dong` 필드를 정밀 분리하여 `ApartmentComplex`와 `Listing`을 `AND` 조건으로 엄격 격리 쿼리 적용.

### 7) 초고속 병렬 데이터 수집 튜닝 (12시간 -> 수분 이내)
- **위치**: `adapter.py`
- **방안**:
  - Playwright 동적 Bearer 토큰 캡처 후 `httpx.AsyncClient` 파이프라인에 세션 쿠키와 토큰을 이관.
  - 65개 구/시를 `asyncio.Semaphore(15)` 병렬 워커 풀로 동시 전송하여 수집 소요시간을 12시간에서 **3~5분 이내**로 100배 고속화.

### 8) Redis 캐시 서버 연동 (데이터 조회 속도 1ms 극대화)
- **위치**: `infrastructure/cache/redis_client.py`, `search_service.py`
- **방안**:
  - 현재 로컬 구동 중인 Redis (`localhost:6379`) 연동 클라이언트 구축.
  - 인기 지역/필터 검색 결과(Paging JSON/HTML)를 `redis.setex(cache_key, 300, data)`로 캐싱하여 MySQL 쿼리 없이 **1ms** 만에 응답!

---

## 3. 구현 단계 및 검증 수단

1. **Phase 1**: UI/UX 필터 수정 (지역 선택, 고급필터 클릭 영역, 페이지 1 리셋, 정렬 위치 이동)
2. **Phase 2**: 단기임대 매물 식별 알고리즘 및 지역 필터 버그 수정
3. **Phase 3**: Redis 캐싱 클라이언트 및 초고속 병렬 크롤러 튜닝
4. **Verification**: `python -m pytest tests/` 전체 51개 테스트 검증 및 성능 측정
