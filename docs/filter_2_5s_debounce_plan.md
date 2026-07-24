# 필터 선택 시 2.5초 자동 검색 지연 (Debounce) 구현 계획서

필터 조작 시 즉시 조회되던 방식을 필터 조작 완료 후 2.5초(2,500ms) 동안 대기한 뒤 자동 검색이 구동되도록 지연 시간을 조절하는 구현 계획서입니다.

---

## 1. 개요 및 요구사항

- **기존 방식**: 필터 변경 시 즉시(또는 300ms 만에) 백엔드로 HTMX 조회 요청이 전송됨.
- **수정 목표**: 슬라이더 이동, 드롭다운 선택, 태그 칩 클릭 등 필터 변경 이벤트 발생 시 **2.5초(2500ms) 동안 추가 조작이 없으면 자동으로 조회가 구동**되도록 디바운스(Debounce) 로직을 연동.
- **직접 검색 시**: '검색' 버튼 클릭 또는 텍스트 입력 후 엔터 키 입력 시에는 2.5초 대기 없이 즉시(0초) 검색 실행.

---

## 2. 파일별 수정 계획

### [1] `src/realty_radar/web/templates/listings/index.html`
- HTML Form 트리거 속성 변경: `hx-trigger="change delay:2500ms, submit"`
- JavaScript `triggerFormSubmit(immediate = false)` 디바운서 연동:
  ```javascript
  let formDebounceTimer = null;

  function triggerFormSubmit(immediate = false) {
      saveFiltersToLocalStorage();
      if (formDebounceTimer) {
          clearTimeout(formDebounceTimer);
          formDebounceTimer = null;
      }
      if (immediate) {
          htmx.trigger('#search-filter-form', 'submit');
      } else {
          formDebounceTimer = setTimeout(() => {
              htmx.trigger('#search-filter-form', 'submit');
          }, 2500);
      }
  }
  ```

---

## 3. 검증 계획
- pytest 및 gradle 검증 수행.
- 필터 조건 조작 후 2.5초 간격으로 자동 조회가 구동되는지 검증.
