# 지도 클러스터 및 마커 오버레이 가로 고정 계획서 (map_overlay_horizontal_layout_plan.md)

## 1. 개요
지도 테두리에 위치한 클러스터/마커 뱃지가 지도 벽에 부딪혀 세로로 꺾이거나 두 줄로 출력되는 현상을 해결하고, 어떤 위치에서도 가로 한 줄(`whitespace-nowrap`)로만 표기되도록 강제 고정함.

## 2. 세부 조치
- `src/realty_radar/web/static/listing-map.js`:
  - `makeClusterOverlay` 및 `makeMarkerOverlay` 내 HTML 오버레이 컨테이너에 `style="writing-mode: horizontal-tb !important; white-space: nowrap !important;"` 및 `whitespace-nowrap overflow-hidden text-ellipsis` 속성 부여.
