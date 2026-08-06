# 다이얼로그 모달 미닫힘 수리 계획서 (fix_dialog_unclosed_visibility_plan.md)

## 1. 개요
dialog:not([open]) 시 display: none !important 처리를 추가하여 닫힘 상태에서 모달 패널이 계속 뜨는 현상을 수정함.

## 2. 변경 파일
- `src/realty_radar/web/templates/listings/index.html`: dialog:not([open]):hidden CSS 및 닫기 처리 강화.
- `src/realty_radar/web/static/listing-filter-panel.js`: panel.close() 및 backdrop 닫기 보강.
