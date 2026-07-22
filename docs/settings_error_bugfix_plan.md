# 작업 계획 및 분석 보고서: 설정 페이지 접속 에러 수정

## 1. 문제 현상 분석
설정 페이지(`/settings`) 접속 시 템플릿 렌더링 에러(Jinja2 Template Error)가 발생하며 페이지 로드가 정상적으로 이루어지지 않음.

## 2. 근본 기술적 원인 분석
- `src/realty_radar/web/routes/settings.py`에서 `Jinja2Templates`를 생성하여 화면을 렌더링하고 있으나, 커스텀 진자 필터를 등록하는 `register_jinja_filters(templates)` 호출이 누락되어 있음.
- 이로 인해 `settings/index.html` 파일 내부에서 사용되는 `comma_number` 등의 커스텀 Jinja2 필터를 파싱하지 못하고 렌더링 에러가 발생함.

## 3. 수정 방안
- `src/realty_radar/web/routes/settings.py` 상단에 `from realty_radar.web.jinja_filters import register_jinja_filters` 임포트를 추가합니다.
- `templates = Jinja2Templates(...)` 호출 직후 `register_jinja_filters(templates)`를 호출하여 커스텀 필터들을 바인딩하도록 수정합니다.

## 4. 검증 계획
- `pytest tests/integration/test_web.py` 실행하여 웹 통합 테스트 통과 확인.
- 설정 페이지 접속 및 업데이트 시 정상 렌더링되는지 확인.

## 5. 조치 결과 보고
- **Jinja2 커스텀 필터 등록 반영**: [settings.py](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/routes/settings.py) 라우터의 템플릿 환경에 `register_jinja_filters(templates)`를 바인딩함으로써 설정 페이지(`/settings`) 로드 시 발생하는 Jinja2 렌더링 에러를 완전히 정상화했습니다.
- **웹 페이지 테스트 연동 및 통과**: [test_web.py](file:///c:/workspace/personal/real-estate-search/tests/integration/test_web.py) 통합 테스트 파일에 설정 화면 렌더링 검증(`test_settings_page`) 및 설정 정보 전송/정제 검증(`test_update_settings`) 케이스를 신규 추가해 총 42개 전체 테스트 100% 통과(`42 passed`)를 검증했습니다.
