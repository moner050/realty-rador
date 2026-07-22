# 작업 계획서: 단지 관리 페이지 삭제 및 UI 네비게이션 정리

## 1. 개요
사용자의 요청에 따라 단지 관리 페이지(`/complexes`) 및 관련 웹 라우터, 템플릿, 헤더 네비게이션 링크를 완전히 제거합니다.

## 2. 작업 상세 항목
1. **네비게이션 헤더 메뉴 삭제**:
   - `src/realty_radar/web/templates/base.html`에서 '단지 관리' 링크 태그 삭제.
2. **웹 메인 애플리케이션 라우터 제거**:
   - `src/realty_radar/web/main.py`에서 `complexes_router` 임포트 및 라우터 등록(`app.include_router(complexes_router)`) 구문 삭제.
3. **불필요한 라우터 및 템플릿 파일 삭제**:
   - `src/realty_radar/web/routes/complexes.py` 파일 제거.
   - `src/realty_radar/web/templates/complexes/detail.html` 파일 및 `complexes/` 디렉터리 삭제.

## 3. 검증 계획
- `python -m pytest tests/unit tests/integration` 실행하여 테스트 이상 없음 확인.
- 웹 페이지(`http://127.0.0.1:8000`)에서 상단 네비게이션에 '단지 관리' 메뉴가 제거되었는지 확인.

## 4. 수행 결과 보고
- **네비게이션 헤더 메뉴 정리 완료**: `base.html` 헤더에서 '단지 관리' 메뉴 링크를 완전히 제거했습니다.
- **라우터 및 템플릿 정리 완료**: 불필요한 라우터(`src/realty_radar/web/routes/complexes.py`) 및 템플릿(`src/realty_radar/web/templates/complexes/detail.html`)을 삭제하고 `main.py` 라우터 마운트 설정을 정돈했습니다.
- **테스트 검증**: 38개 유닛 및 통합 테스트를 실행하여 오류 없이 통과(`38 passed`)함을 확인했습니다.
