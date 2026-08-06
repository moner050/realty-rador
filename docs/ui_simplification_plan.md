# UI 단순화 및 상세 주거 조건 상시 펼침 계획서 (ui_simplification_plan.md)

## 1. 작업 개요
1. 우측 매물검색 필터 패널의 검색 결과 툴바에서 정렬 기준 드롭다운 선택 UI 제거.
2. 상세 검색 조건 설정 -> 주거 스펙 탭의 `상세 주거 조건` accordion 접힘 구조를 제거하여 항상 펼쳐진 상태로 표시.

## 2. 세부 변경 파일
- [src/realty_radar/web/templates/listings/_search_result_summary.html](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/templates/listings/_search_result_summary.html): `정렬` 선택 UI 구문 삭제.
- [src/realty_radar/web/templates/listings/index.html](file:///c:/workspace/personal/real-estate-search/src/realty_radar/web/templates/listings/index.html): `<details id="advanced-housing-conditions">` -> `<section>` 구조 변환.
