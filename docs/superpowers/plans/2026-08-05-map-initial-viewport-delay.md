# 지도 초기 범위 및 1.5초 조회 지연 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수도권 범위의 빈 초기 지도를 보여 주고, 첫 사용자 지도 조작 후 1.5초가 지난 시점에만 지도와 목록을 동시에 조회한다.

**Architecture:** 지도 클라이언트가 초기 요청을 만들지 않고 안내 상태로 시작한다. 첫 `idle` 이벤트 이후 하나의 1.5초 디바운스 시점에 지도 JSON과 확대 상태의 카드 HTML 요청을 병렬로 시작하며, 기존 요청 취소·최신 뷰포트 키 검증을 그대로 사용한다.

**Tech Stack:** NAVER Maps V3 browser API, vanilla JavaScript, FastAPI templates, Node test runner.

## Global Constraints

- 초기 지도는 서울·경기·인천이 보이는 수도권 중심과 줌 8로 시작한다.
- 초기 지도·카드 API 요청은 만들지 않는다.
- 사용자 드래그·확대·축소가 멈춘 뒤 1.5초에 지도 요청과 가능한 카드 요청을 동시에 시작한다.
- `zoom < 11` 요약, 확대 마커·카드, 필터 비영속성, 모달, 요청 취소·최신 응답 보호는 유지한다.
- 스키마·마이그레이션·수집·지오코딩은 변경하지 않는다.

---

### Task 1: 클라이언트 시간 제어 회귀 테스트

**Files:**
- Modify: `tests/web/test_listing_map_controller.mjs:118-300`

**Interfaces:**
- Consumes: `RealtyRadarListingMap.mount(root)`, fake map event emitter, `state.mapFetches`, `state.cardFetches`.
- Produces: 초기 뷰포트와 1.5초 지연을 보호하는 브라우저 컨트롤러 계약.

- [ ] **Step 1: 초기 수도권 지도와 무요청 동작의 실패 테스트를 작성한다.**

```js
test('initial map shows the metropolitan viewport without fetching listings', async () => {
  const { controller, state } = loadController();
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.advanceBy(1600);

  assert.deepEqual(state.maps[0].options.center, { latitude: 37.55, longitude: 126.9 });
  assert.equal(state.maps[0].options.zoom, 8);
  assert.equal(state.mapFetches.length, 0);
  assert.equal(state.cardFetches.length, 0);
});
```

- [ ] **Step 2: 테스트가 기존 즉시 초기 지도 요청 때문에 실패하는지 확인한다.**

Run: `node --test tests/web/test_listing_map_controller.mjs`

Expected: FAIL because the current map uses nationwide center/zoom and calls `/api/listings/map-data` from `mount`.

- [ ] **Step 3: 1.5초 이전 무요청과 동일 시점 병렬 조회의 실패 테스트를 작성한다.**

```js
test('a settled user viewport starts map and cards together after 1.5 seconds', async () => {
  const { controller, state } = loadController({ zoom: 12 });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  state.emitMap('zoom_changed');
  state.emitMap('idle');
  await state.advanceBy(1499);
  assert.equal(state.mapFetches.length, 0);
  assert.equal(state.cardFetches.length, 0);

  await state.advanceBy(1);
  assert.equal(state.mapFetches.length, 1);
  assert.equal(state.cardFetches.length, 1);
});
```

- [ ] **Step 4: 테스트가 기존 100ms/450ms 타이머 때문에 실패하는지 확인한다.**

Run: `node --test tests/web/test_listing_map_controller.mjs`

Expected: FAIL because the map request begins before 1.5 seconds and the card request has a separate delay.

- [ ] **Step 5: 기존 작업트리 변경과 분리된 상태를 확인한다.**

Run: `git status --short`

Expected: 기존 사용자 승인 지도 상호작용 변경은 그대로 유지하고, 이번 테스트 변경만 추가로 보인다. 사용자가 커밋을 요청하기 전에는 파일 일부를 임의로 stage하거나 commit하지 않는다.

### Task 2: 수도권 초기 상태와 단일 1.5초 디바운스

**Files:**
- Modify: `src/realty_radar/web/static/listing-map.js:5-430`
- Modify: `src/realty_radar/web/templates/listings/_map_sidebar.html:1-20`
- Test: `tests/web/test_listing_map_controller.mjs`

**Interfaces:**
- Consumes: NAVER `Map` constructor, `dragstart`, `zoom_changed`, `idle`, existing `AbortController` and viewport-key helpers.
- Produces: `mount(root)` with no fetch, `scheduleViewportRefresh(root, map, instance)` with one 1.5-second start time for both request channels.

- [ ] **Step 1: 지도 상수와 초기 안내 문구를 최소 범위로 구현한다.**

```js
const INITIAL_CENTER = { latitude: 37.55, longitude: 126.9 };
const INITIAL_ZOOM = 8;
const VIEWPORT_SEARCH_DEBOUNCE_MS = 1500;

const map = new window.naver.maps.Map(container, {
  center: new window.naver.maps.LatLng(INITIAL_CENTER.latitude, INITIAL_CENTER.longitude),
  zoom: INITIAL_ZOOM,
});
setStatus(root, '지도를 확대하거나 이동하면 현재 영역의 매물을 찾습니다.');
```

Remove the direct `requestMapData(root, map, instance)` call at the end of `mount`.

- [ ] **Step 2: 지도와 카드 타이머를 동일한 1.5초 시점에 예약한다.**

```js
if (instance.lastMapViewportKey !== key) {
  instance.mapTimer = setTimeout(
    () => requestMapData(root, map, instance, { key }),
    VIEWPORT_SEARCH_DEBOUNCE_MS,
  );
}
if (canRefreshCards(map, viewport) && instance.lastCardsViewportKey !== key) {
  instance.cardsTimer = setTimeout(
    () => requestCards(root, map, instance, key),
    VIEWPORT_SEARCH_DEBOUNCE_MS,
  );
}
```

Keep `markViewportDirty` cancellation, viewport-key checks, and stale-response checks unchanged. Do not add a server route, cache, index, or migration.

- [ ] **Step 3: focused controller tests를 실행해 통과를 확인한다.**

Run: `node --test tests/web/test_listing_map_controller.mjs`

Expected: PASS, including existing stale-request, cluster, listing-focus, marker-modal, and unmount contracts.

- [ ] **Step 4: 변경 범위를 확인한다.**

Run:

```bash
git diff -- src/realty_radar/web/static/listing-map.js src/realty_radar/web/templates/listings/_map_sidebar.html tests/web/test_listing_map_controller.mjs
git status --short
```

Expected: 변경은 초기 지도 위치, 1.5초 단일 디바운스, 초기 안내 문구와 회귀 테스트로 한정된다. 사용자가 커밋을 요청하기 전에는 stage하거나 commit하지 않는다.

### Task 3: 성능 검증 및 다음 서버 최적화 판단

**Files:**
- Modify: none unless the commands expose a regression.
- Test: `tests/web/test_listing_map_controller.mjs`, full `tests` suite.

**Interfaces:**
- Consumes: running local app with its configured database and existing map endpoints.
- Produces: persisted command evidence for client timing and a decision boundary for future database work.

- [ ] **Step 1: 전체 자동 테스트와 공백 diff 검사를 실행한다.**

Run:

```bash
python -m pytest
node --test tests/web/test_listing_map_controller.mjs
git diff --check
```

Expected: all tests pass and `git diff --check` has no errors.

- [ ] **Step 2: 실제 데이터가 연결된 사용자 로컬 서버에서 지도·카드 API를 각각 3회 측정한다.**

Run:

```powershell
curl.exe --silent --output NUL --write-out '%{http_code} %{time_total} %{size_download}' 'http://127.0.0.1:8000/api/listings/map-data?map_west=126.85&map_south=37.45&map_east=127.15&map_north=37.70&map_zoom=12'
curl.exe --silent --output NUL --write-out '%{http_code} %{time_total} %{size_download}' 'http://127.0.0.1:8000/listings/map-cards?map_west=126.85&map_south=37.45&map_east=127.15&map_north=37.70&map_zoom=12'
```

Expected: both endpoints return HTTP 200. Compare the three timings with the observed baseline: map 1.06–1.35s / 339KB and cards 2.17–2.20s / 453KB.

- [ ] **Step 3: 서버 최적화의 변경 게이트를 기록한다.**

If the post-change raw API times remain near the baseline, do not claim that a client timer made the database faster. First run read-only `EXPLAIN ANALYZE` against the live map-bound listing query and inspect the selected index. Only after that evidence should a separate approved task choose between an `complex_current` coordinate-range index and adaptive cluster coarsening; neither is included in this plan.

- [ ] **Step 4: 검증 후 작업트리 상태를 기록한다.**

Run:

```bash
git status --short
git diff --check
```

Expected: 임시 성능 측정 파일이 남지 않고, 사용자 승인 전에는 커밋을 만들지 않는다.
