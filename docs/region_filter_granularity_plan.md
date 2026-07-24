# [Plan] 시/군/구 세분화 지역 필터 고도화 계획

## 1. 개요
기존에 '시/군/구'가 단일 텍스트/통합 문자열로 묶여 필터링되던 방식을 **시(시/도 및 시), 군, 구**로 명확히 분리하여 각각 독립적으로 지정/검색할 수 있도록 고도화합니다.

---

## 2. 세부 변경 사항

### A. Domain DTO 모델 (`src/realty_radar/domain/listing/models.py`)
- `ListingFilterParams` 클래스에 분리된 지역 파라미터 추가:
  - `sido`: 시/도 (예: 서울특별시, 경기도, 인천광역시 등)
  - `city`: 시 (예: 과천시, 하남시, 성남시, 수원시, 고양시 등)
  - `county`: 군 (예: 가평군, 양평군, 강화군 등)
  - `district`: 구 (예: 강남구, 서초구, 송파구, 분당구, 마포구 등)

### B. 검색 서비스 (`src/realty_radar/application/listing_search_service.py`)
- SQLAlchemy 쿼리 구문 고도화:
  - `sido` 조건: `Listing.sido` 및 `Listing.address_raw` 매칭
  - `city` 조건: `Listing.sigungu` 및 `address_raw` 내 '시' 패턴 검색
  - `county` 조건: `Listing.sigungu` 및 `address_raw` 내 '군' 패턴 검색
  - `district` 조건: `Listing.sigungu` 및 `address_raw` 내 '구' 패턴 검색
  - `region_name` 입력 시 자동으로 토큰 분석 후 시/군/구 파싱 fallback 연동

### C. 웹 컨트롤러/라우트 (`src/realty_radar/web/routes/home.py`, `routes.py`)
- `sido`, `city`, `county`, `district` Query 파라미터 수신 및 `ListingFilterParams` 매핑

### D. 웹 템플릿 UI (`src/realty_radar/web/templates/listings/index.html`)
- 필터 영역에 **시/도(Sido), 시(City), 군(County), 구(District)** 각각 선택/입력 가능한 UI 요소 제공.
- 퀵 칩(Quick Region Chips) 클릭 시 수식어 패턴(시/군/구) 자동 파싱 및 입력 세팅 기능 개선.

---

## 3. 작업 순서
1. `src/realty_radar/domain/listing/models.py` 수정
2. `src/realty_radar/application/listing_search_service.py` 수정
3. `src/realty_radar/web/routes/home.py` 및 관련 라우터 수정
4. `src/realty_radar/web/templates/listings/index.html` UI 수정
5. 단위/통합 테스트 작성 및 Gradle(pytest) 검증 실행
