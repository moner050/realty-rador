# 중복 폼 인풋 제거 및 모달 핀 고정 계획서 (fix_duplicate_form_inputs_and_modal_scroll_plan.md)

## 1. 개요
중복 파라미터 전송(trade_types=SALE&trade_types=SALE 등)을 제거하고, 모달 헤더/푸터를 핀 고정하여 방향 선택 시 높이 찌그러짐 현상을 완벽히 수정함.

## 2. 변경 파일
- `src/realty_radar/web/templates/listings/index.html`: 중복 인풋 정리 및 모달 헤더/푸터 shrink-0 핀 고정.
- `src/realty_radar/web/static/listing-map.js`: URL 파라미터 중복 제거 및 파싱 보강.
