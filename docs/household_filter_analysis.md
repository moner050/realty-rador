# 세대수 필터 검색 결과 누락 원인 분석 보고서

## 1. 문제 현상
- 웹 검색 화면에서 '세대수' 필터를 조절하거나 최소 세대수를 설정할 경우, 매물 검색 결과가 0건으로 나오며 아무 매물도 검색되지 않는 현상 발생.

## 2. 기술적 원인 분석

### ① 크롤링 매물 정보와 단지 세대수 정보의 분리
- 크롤러 어댑터(`SiteAAdapter`)가 매물을 수집할 때 생성하는 `RawListing` 및 정규화 모델(`NormalizedListing`)에는 매물 단위의 가격, 면적, 층수, 설명 등의 데이터만 수집되며 세대수(`total_households`) 필드는 매물 데이터에 직접 포함되어 있지 않습니다.

### ② 매물-단지 매칭 시 신규 단지 생성 로직의 세대수 미설정 (NULL)
- 크롤링 수집 파이프라인(`CrawlPipelineService`) 실행 시 `ComplexMatchService.match_listing_complex()`가 동작합니다.
- 매칭되는 기존 단지가 없을 경우 새로운 단지 레코드(`ApartmentComplex`)를 신규 생성합니다:
  ```python
  new_complex = ApartmentComplex(
      official_name=listing.complex_name_raw,
      normalized_name=norm_name,
      road_address=listing.address_raw,
      # total_households 및 construction_year 미설정 -> DB 상 NULL 저장
  )
  ```
- 이 과정에서 `total_households`(총 세대수) 값이 설정되지 않아 DB에 `NULL`로 저장됩니다.

### ③ 검색 필터 쿼리 동작 (`NULL >= min_households`)
- `ListingSearchService.search_listings()`에서 세대수 필터가 적용될 때 다음과 같은 SQL 조건절이 추가됩니다:
  ```python
  if params.min_households:
      stmt = stmt.where(ApartmentComplex.total_households >= params.min_households)
  ```
- DB 내 단지들의 `total_households` 값이 모두 `NULL`이기 때문에, `NULL >= min_households` 평가 결과는 항상 `FALSE`가 되어 모든 매물이 검색 결과에서 제외됩니다.

## 3. 개선 및 해결 방안 (제안)
1. **모의 단지 생성 시 기본/랜덤 세대수 부여**:
   - `SiteAAdapter` 매물 수집 시 임의의 세대수(예: 300~3,000세대) 및 준공년도를 매물/단지 데이터에 포함하거나 `ComplexMatchService`에서 단지 생성 시 기본 세대수를 할당하도록 개선.
2. **공공데이터 동기화 연동**:
   - `PublicDataSyncService`를 통해 국토교통부/공공데이터 API로부터 단지별 실제 총 세대수 및 준공년도를 동기화 업데이트.
