# 백엔드 리스트 파라미터 파싱 및 모달 높이 고정 계획서 (fix_request_list_and_dialog_viewport_plan.md)

## 1. 개요
백엔드 _request_list()의 str 수신 처리 보강으로 방향 필터 미적용 버그를 해결하고, 모달 다이얼로그의 h-screen top-0 bottom-0 고정으로 높이 여백 현상을 영구 차단함.

## 2. 변경 파일
- `src/realty_radar/web/routes/home.py`: _request_list() str 타입 분할 파싱 보강.
- `src/realty_radar/web/templates/listings/index.html`: detailed-filter-modal top-0 bottom-0 h-screen max-h-screen 고정.
