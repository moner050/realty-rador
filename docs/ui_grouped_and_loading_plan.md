# [Plan] 아파트 묶어보기 초기 접힘(Collapsed) 상태 설정 및 실시간 로딩 인디케이터 고도화

## 1. 개요
1. **아파트 묶어보기 초기 접힘 처리**: 동일 아파트 묶어서 보기 모드(`group_by_complex`) 선택 시 초기 렌더링 시점에 매물 목록이 전부 펼쳐진 상태(`open: true`)였던 것을 **기본 묶인(접힌, Collapsed) 상태(`open: false` & `hidden`)로 변경**하여 사용자가 클릭할 때 펼쳐지도록 수정.
2. **실시간 필터 변경 로딩 인디케이터(Loading Indicator)**: 검색 필터 조절 및 변경 시 HTMX 요청이 처리되는 동안 사용자가 직관적으로 로딩 상태를 인식할 수 있는 **스피너 및 안내 마스크 오버레이 바** 추가.

---

## 2. 세부 구현 계획

### 1) 동일 아파트 묶어서 보기 아코디언 초기 닫힘 설정 (`src/realty_radar/web/templates/listings/list_partial.html`)
- `x-data="{ open: false }"`로 기본 변경.
- 그룹 매물 감싸는 div 태그에 `hidden` 클래스를 기본 부여하여 최초 로딩 시 100% 깔끔하게 묶여진 아파트 단지 카드로 표현.
- 헤더 클릭 시 `open = !open` 및 `.classList.toggle('hidden')`으로 부드럽게 토글.

### 2) HTMX 검색 필터 로딩 인디케이터 추가 (`src/realty_radar/web/templates/listings/index.html`)
- `#search-filter-form`에 `hx-indicator="#search-loading-indicator"` 속성 부여.
- `#search-loading-indicator` 로딩 마스크 템플릿(회전 애니메이션 스피너 + "조건에 맞는 매물을 실시간 조회 중입니다...") 추가.
- `.htmx-request.htmx-indicator` CSS 디스플레이 제어 적용.

---

## 3. 검증
- 단위/통합 테스트 실행 (`python -m pytest`)
- 템플릿 구문 및 로딩 오버레이 렌더링 검증.
