# 모달 이중 스크롤바 및 하단 빈 공간 제거 계획서 (modal_scrollbar_and_empty_space_fix_plan.md)

## 1. 개요
`<dialog>`에 `overflow-hidden`을 적용하여 외부 스크롤바를 차단하고, 탭 바와 본문, 푸터의 flex 분치를 `shrink-0` 및 `flex-1 min-h-0 overflow-y-auto`로 재구성하여 하단 빈 공간 삭제 및 단일 스크롤바를 달성함.

## 2. 변경 파일
- `src/realty_radar/web/templates/listings/index.html`: `detailed-filter-modal` dialog 및 자식 요소 flex 구조 수정.
