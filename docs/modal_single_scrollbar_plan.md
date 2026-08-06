# 모달 이중 스크롤바 제거 및 단일화 계획서 (modal_single_scrollbar_plan.md)

## 1. 개요
상세 검색 조건 모달(`detailed-filter-modal`) 내 자식 탭 4종 요소에 지정되어 있던 중복 `overflow-y-auto` 클래스를 제거하여 오른쪽 스크롤바가 1개만 노출되도록 정리함.

## 2. 변경 파일
- `src/realty_radar/web/templates/listings/index.html`: `filter-tab-content-*` 자식 탭 요소의 `overflow-y-auto` 삭제.
