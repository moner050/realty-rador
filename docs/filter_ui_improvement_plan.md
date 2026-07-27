# 매물 검색 필터 UX/UI 및 슬라이더 수치 표기 개선 계획서

## 1. 개요 및 목적
1. 듀얼 슬라이더 최소(min)와 최대(max) 손잡이가 동일 수치에 다다라 완전히 포개졌을 때, 두 원이 먹통이 되지 않도록 **가로 나란히 정렬(좌/우 오프셋)**하여 각각 개별 조작이 가능하도록 개선합니다.
2. 수치가 동일할 때 툴팁 및 커서 감지 동적 Z-Index 조작성을 강화합니다.

## 2. 주요 개선 사항
1. **두 원 겹침 시 가로 나란히 정렬 (Horizontal Side-by-Side Thumb Alignment)**
   - `minVal === maxVal` 또는 겹침 감지 시 `data-overlapping="true"` 상태를 부여.
   - CSS `::-webkit-slider-thumb` 및 `::-moz-range-thumb`에 오프셋 적용:
     - 최소(min) 썸: `transform: translateX(-7px)` (좌측 배치)
     - 최대(max) 썸: `transform: translateX(7px)` (우측 배치)
   - 두 원이 동일 수치일 때 가로로 나란히 배치되어 사용자가 좌측 원을 잡으면 최소값, 우측 원을 잡으면 최대값이 쉽게 조작됨.

2. **툴팁 및 pointermove 커서 감지 스마트 Z-Index 강화**
   - 겹침 상태에서 커서 위치(좌측 반구/우측 반구)에 따라 min/max 핸들에 `z-index: 35`를 동적 할당하여 클릭 실패 현상 완전 차단.
   - 툴팁 배지도 좌/우로 나누어 명확히 수치를 보여주도록 보정.

## 3. 작업 대상 파일
- `src/realty_radar/web/templates/listings/index.html`

## 4. 검증 계획
- Pytest 테스트 전체 수행하여 슬라이더 UI 렌더링 및 기능 100% 정상 작동 검증.
