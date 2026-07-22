# 작업 계획서: 공공데이터 API 연동을 통한 아파트 단지 세대수 및 준공년도 동기화

## 1. 개요
모의 데이터 사용 대신 국토교통부 공공데이터 API 연동을 통해 아파트 단지의 총 세대수(`total_households`) 및 준공년도(`construction_year`)를 동기화하여 매물 검색 시 세대수 필터가 정상 작동하도록 구현합니다.

## 2. 상세 작업 계획

### 2.1 공공데이터 API 클라이언트 강화 (`PublicDataApiClient`)
- 위치: `src/realty_radar/enrichment/public_data/client.py`
- 국토교통부 공동주택 기본정보 Open API 연동 메서드 `fetch_complex_basis_info` 구현.
- API 응답(XML/JSON)에서 총 세대수(`kaptdaCnt`/`total_households`), 준공년도(`build_year`) 파싱.

### 2.2 공공데이터 동기화 서비스 업데이트 (`PublicDataSyncService`)
- 위치: `src/realty_radar/enrichment/public_data/sync_service.py`
- `sync_complex_public_data(complex_id: int)`에서 공공데이터 API를 통해 세대수 및 준공년도를 수집하여 `ApartmentComplex` DB 레코드에 저장.

### 2.3 단지 매칭 서비스 연동 (`ComplexMatchService`)
- 위치: `src/realty_radar/application/complex_match_service.py`
- 신규 단지 생성 또는 세대수 미설정 단지 매칭 시 공공데이터 동기화 서비스를 자동 호출하여 세대수 정보를 최신화.

## 3. 검증 계획
- `pytest tests/unit/test_public_data_client.py tests/integration/test_public_data_sync.py` 테스트 실행.
- 웹 UI 상에서 세대수 필터링 조절 시 매물 검색 정상 동작 검증.

## 4. 수행 결과 보고
- **공공데이터 API 파싱 연동**: `PublicDataApiClient`에 국토교통부 공동주택 기본정보 API(`AptBasisInfoServiceV2`) 연동 및 XML 파서를 구축하여 실제 총 세대수(`total_households`) 및 준공년도(`construction_year`) 추출 로직을 완성했습니다.
- **세대수 동기화 자동화**: `PublicDataSyncService` 및 `ComplexMatchService`를 연결하여, 크롤링 수집 후 단지가 생성되거나 연결될 때 세대수가 없는 단지는 자동으로 공공데이터 조회를 통해 DB에 세대수를 업데이트하도록 구현했습니다.
- **테스트 통과**: 38개의 모든 유닛 및 통합 테스트를 실행하여 100% 통과(`38 passed`)함을 확인하였습니다. 세대수 필터링 조건 설정 시 조회가 정상 작동하게 됩니다.
