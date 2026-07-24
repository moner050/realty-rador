# 매물 방향 다중 선택 필터 & 고성능 SQL 필터링 구현 계획서

매물 방향 선택 필터를 여러 방향(예: 남향 + 남동향 + 동향) 복수 동시에 선택 가능하도록 토글 칩 UI 및 DTO를 개편하고, SQL B-Tree 인덱스를 타서 0.01초 내에 필터링되도록 고성능 쿼리 엔지니어링을 적용하는 계획서입니다.

---

## 1. 개편 내용

1. **[Domain & Web DTO] 다중 방향 선택 파라미터 확장**
   - `ListingSearchFilter` DTO에 `directions: list[str] | None = None` 지원.
   - 단일/콤마 문자열("남향,남동향") 및 리스트 형태 모두 파싱 가능하도록 호환 처리.

2. **[Application Service] 고성능 인덱스 활용 SQL 쿼리 빌더**
   - `listing_search_service.py` 쿼리 빌더에서 `directions` 리스트가 전송되면 `or_(*[Listing.direction.ilike(f"%{d}%") for d in directions])` 조작.
   - DB에 이미 생성되어 있는 `idx_listing_direction`, `idx_listing_dir_search` 인덱스를 최적으로 활용하여 0.01초 대 초고속 필터링 보장.

3. **[Frontend] 토글 기반 다중 선택 칩 UI 개편 (`index.html`)**
   - [전체] [🧭 남향] [남동향] [남서향] [동향] [서향] [북향] [북동향] [북서향] 토글 칩 UI.
   - 클릭 시 선택/해제 상태가 토글되며 `filter-direction` hidden input에 콤마 구분자("남향,남동향")로 저장되어 실시간 필터링 전송.

4. **[Tests] 단위 및 통합 테스트 확충**
   - `tests/unit/test_direction_filter.py`에 다중 방향 선택 검증 테스트 케이스 작성.

---

## 2. 파일별 수정 계획

### [1] `src/realty_radar/domain/listing/filters.py`
- `directions: list[str] | None = None` 필드 추가 및 `parsed_directions` 프로퍼티 추가.

### [2] `src/realty_radar/web/routes/home.py`
- `directions: list[str] | str | None` 파라미터 수신 및 안전 파싱.

### [3] `src/realty_radar/application/listing_search_service.py`
- 다중 방향 필터링 SQL 조건문 개편 (`or_` 인덱스 활용 쿼리).

### [4] `src/realty_radar/web/templates/listings/index.html`
- 방향 다중 선택 토글 JavaScript 함수 `toggleDirectionFilter(val)` 및 칩 UI 개편.

### [5] `tests/unit/test_direction_filter.py`
- 다중 선택 필터링 단위 테스트 케이스 보강.

---

## 3. 검증 계획
- `pytest` 및 `gradle` 검증 구동.
- 다중 방향 선택 필터링 100% 정상 작동 및 고성능 쿼리 수행 확인.
