# [Plan] Playwright networkidle 타임아웃 오류 수정 및 안정성 향상 계획

## 1. 개요 및 원인 분석

Ubuntu 클라우드 등 Headless 브라우저 환경에서 즉시 수동 크롤링 실행 시 다음 오류 발생:
`Playwright 브라우저 초기화 오류: Page.goto: Timeout 20000ms exceeded.`
`navigating to "https://new.land.naver.com/complexes/1001", waiting until "networkidle"`

### 원인:
`wait_until="networkidle"` 옵션은 최소 500ms 동안 네트워크 통신이 완전 무통신 상태가 될 때까지 기다립니다.
그러나 네이버 부동산과 같은 리치 웹 앱은 외부 분석 트래커, 광고, 롱폴링, 폰트/이미지 비동기 로딩으로 인해 통신이 끊이지 않아 20초 타임아웃이 발생합니다.

---

## 2. 해결 방안

1. `src/realty_radar/crawler/adapters/site_a/adapter.py` 의 `goto` 옵션을 `wait_until="domcontentloaded"`로 변경.
2. `goto` 호출 시 타임아웃 방지를 위해 `try...except` 안전 구문을 적용하여 DOM 로드 완료 후 토큰 캡처를 대기하도록 개선.
3. 타임아웃 예외로 인해 크롤링 전체가 중단되지 않고 안정적으로 자격 증명 토큰 캡처 및 수집이 진행되도록 보장.

---

## 3. 작업 항목

- [x] `src/realty_radar/crawler/adapters/site_a/adapter.py` 수정
- [x] 테스트 실행 (`python -m pytest`)
