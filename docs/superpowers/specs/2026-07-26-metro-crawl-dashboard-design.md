# 수도권 전체 수동 수집 현황

## 목표

수집현황 화면에서 서울·경기·인천의 모든 시/군/구를 한 번에 수동 등록하고, 기존 worker가 처리하는 과정과 완료 여부를 확인한다.

## 설계

- 전체 수집은 각 시/군/구 `cortarNo`마다 하나의 `crawl_job`을 만든다. 각 job은 기존 pipeline에서 해당 시/군/구의 동 목록을 수집한다.
- 한 번의 버튼 클릭은 UUID 기반 batch ID를 `manual-metro:<batch-id>:<sigungu-code>` 형태의 기존 `dedupe_key`에 보관한다. 새 테이블이나 migration은 만들지 않는다.
- 활성 전체 수집 batch가 있으면 새 버튼은 비활성화한다. worker가 없으면 모든 job은 queued 상태로 남아 화면에 `worker 대기 중`으로 나타난다.
- 진행 화면은 가장 최근 전체 수집 batch를 대상으로 총 시군구 수와 queued/running/success/retry/failed 수를 계산한다. 서울·경기·인천별로 각 시군구의 이름, 상태, 수집·저장 건수, 오류를 표시한다.
- HTMX가 5초마다 진행 영역만 교체한다. 버튼 POST 성공 시 같은 영역을 즉시 교체한다.

## 안전성

- job은 기존 lease, heartbeat, retry, scope-completeness 경로를 그대로 사용한다.
- 전체 수집 버튼은 job을 등록할 뿐 worker process를 웹 서버에서 시작하지 않는다.
- 중복 active batch는 만들지 않으며, 완료/실패 batch 기록은 조회용으로 보존한다.

## 검증

- service: 수도권 전체 job 수, batch dedupe, 활성 batch 차단, 시군구별 상태 집계를 테스트한다.
- route: 인증된 POST가 batch를 만들고 HTMX progress fragment를 반환하는지 테스트한다.
- template: 전체 수집 버튼, worker 대기 상태, 시도별 시군구 표와 HTMX polling을 확인한다.
