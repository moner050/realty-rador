# 수동 수집 작업 시작 안내 창 및 알림 배너 구현 계획서

## 1. 개요
사용자가 수집 현황 대시보드(`/jobs`)에서 수동 수집 시작 버튼을 누를 때, 수집 작업이 성공적으로 등록되어 백그라운드 Worker가 수집을 진행함을 직관적으로 알 수 있도록 **작업 시작 안내 팝업/토스트 및 대시보드 상태 알림 배너**를 추가합니다.

## 2. 주요 구현 사양

### 1) 버튼 클릭/폼 제출 시 안내 창 (Front-end UX)
- 수동 수집 시작 폼 제출 시 (`#metro-crawl-form` submit 이벤트 또는 htmx event):
  - 안내 문구: `"🚀 수동 수집 작업이 등록되었습니다!\n백그라운드 Worker 프로세스가 선택된 지역의 매물을 순차적으로 수집합니다."`
  - 브라우저 안내 알림 창(Alert/Toast) 표출.

### 2) 대시보드 진행 현황 상단 안내 배너 (`progress_partial.html`)
- 수집 진행 중(`metro_progress.is_active`) 상태일 때, 상단에 수집 활성화 안내 배너 표출:
  - 텍스트: `🚀 수동 수집 작업이 진행 중입니다. (Worker가 매물을 순차 수집 중이며 5초마다 자동 갱신됩니다)`

## 3. 대상 파일
- `src/realty_radar/web/templates/jobs/progress_partial.html`
- `src/realty_radar/web/templates/jobs/index.html`

## 4. 검증 계획
- pytest 연동 검증 (`pytest tests/integration/test_crawl_jobs_dashboard.py`)
- 수동 수집 폼 제출 및 안내 배너/팝업 표출 동작 확인
