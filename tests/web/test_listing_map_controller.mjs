import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const controllerSource = readFileSync(
  new URL('../../src/realty_radar/web/static/listing-map.js', import.meta.url),
  'utf8',
);

function createRoot(payload, { mapSearchUrl = '' } = {}) {
  const container = {};
  const payloadElement = { textContent: JSON.stringify(payload) };
  const status = { textContent: '' };
  return {
    container,
    status,
    dataset: { mapSearchUrl },
    matches(selector) {
      return selector === '[data-listing-map-root]';
    },
    querySelector(selector) {
      if (selector === '[data-listings-map]') return container;
      if (selector === '[data-listing-map-payload]') return payloadElement;
      if (selector === '[data-listing-map-status]') return status;
      return null;
    },
  };
}

function loadController({ fetchImpl } = {}) {
  const state = { maps: [], markers: [], removedListeners: 0, listeners: [], fetches: [], swaps: 0 };
  const fakeWindow = {
    fetch: fetchImpl || (async (url) => {
      state.fetches.push(String(url));
      return { ok: true, text: async () => '<div id="search-results"></div>' };
    }),
    htmx: {
      swap() {
        state.swaps += 1;
      },
    },
    naver: {
      maps: {
        LatLng: class LatLng {
          constructor(latitude, longitude) {
            this.latitude = latitude;
            this.longitude = longitude;
          }
        },
        LatLngBounds: class LatLngBounds {
          extend() {}
        },
        Map: class Map {
          constructor(container, options) {
            this.container = container;
            this.options = options;
            state.maps.push(this);
          }
          fitBounds() {}
          getZoom() { return 14; }
          getBounds() {
            return {
              getSW() { return { lat: () => 37.5, lng: () => 126.8 }; },
              getNE() { return { lat: () => 37.6, lng: () => 126.9 }; },
            };
          }
        },
        Marker: class Marker {
          constructor(options) {
            this.options = options;
            state.markers.push(this);
          }
          setMap(map) {
            this.map = map;
          }
        },
        InfoWindow: class InfoWindow {
          open() {}
          close() {}
        },
        Event: {
          addListener(target, event, callback) {
            const listener = { target, event, callback };
            state.listeners.push(listener);
            return listener;
          },
          removeListener() {
            state.removedListeners += 1;
          },
        },
      },
    },
  };
  const document = {
    readyState: 'complete',
    addEventListener() {},
    querySelector(selector) {
      return selector === '#search-results' ? {} : null;
    },
  };
  vm.runInNewContext(controllerSource, { window: fakeWindow, document, URL, setTimeout, clearTimeout });
  state.emitMap = (event) => {
    state.listeners
      .filter((listener) => state.maps.includes(listener.target) && listener.event === event)
      .forEach((listener) => listener.callback());
  };
  return { controller: fakeWindow.RealtyRadarListingMap, state };
}

test('unmount disposes markers before a replacement fragment mounts', () => {
  const { controller, state } = loadController();
  const firstRoot = createRoot([
    {
      complex_id: 1,
      complex_name: '첫 단지',
      address: '서울특별시 강서구 테스트로 1',
      latitude: 37.55,
      longitude: 126.85,
      listing_count: 1,
      min_price: 500000000,
      max_price: 500000000,
    },
  ]);
  const secondRoot = createRoot([
    {
      complex_id: 2,
      complex_name: '둘째 단지',
      address: '서울특별시 강서구 테스트로 2',
      latitude: 37.56,
      longitude: 126.86,
      listing_count: 2,
      min_price: 600000000,
      max_price: 650000000,
    },
  ]);

  controller.mount(firstRoot);
  controller.unmount(firstRoot);
  controller.mount(secondRoot);

  assert.equal(state.maps.length, 2);
  assert.equal(state.markers.length, 2);
  assert.equal(state.markers[0].map, null);
  assert.ok(state.removedListeners >= 1);
});

test('mount skips an invalid marker instead of manufacturing a fallback coordinate', () => {
  const { controller, state } = loadController();
  const root = createRoot([
    {
      complex_id: 1,
      complex_name: '좌표 없음 단지',
      address: '서울특별시 강서구 테스트로 1',
      latitude: null,
      longitude: null,
      listing_count: 1,
      min_price: 500000000,
      max_price: 500000000,
    },
  ]);

  controller.mount(root);

  assert.equal(state.maps.length, 0);
  assert.equal(state.markers.length, 0);
  assert.equal(root.status.textContent, '위치 확인 중');
});

test('a settled user map interaction requests bounds without cursor or history mutation', async () => {
  const { controller, state } = loadController();
  const root = createRoot([
    {
      complex_id: 1,
      complex_name: '테스트 단지',
      address: '서울',
      latitude: 37.55,
      longitude: 126.85,
      listing_count: 1,
      min_price: 500000000,
      max_price: 500000000,
    },
  ], { mapSearchUrl: '/listings/search?sort_by=price_asc&cursor=old-page' });

  controller.mount(root);
  state.emitMap('dragstart');
  state.emitMap('idle');
  await new Promise((resolve) => setTimeout(resolve, 350));

  assert.match(state.fetches[0], /map_west=126\.8/);
  assert.match(state.fetches[0], /map_south=37\.5/);
  assert.match(state.fetches[0], /map_east=126\.9/);
  assert.match(state.fetches[0], /map_north=37\.6/);
  assert.doesNotMatch(state.fetches[0], /cursor=/);
  assert.equal(state.swaps, 1);
});

test('a stale map response cannot replace the latest viewport result', async () => {
  const pending = [];
  const { controller, state } = loadController({
    fetchImpl: () => new Promise((resolve) => pending.push(resolve)),
  });
  const root = createRoot([
    {
      complex_id: 1,
      complex_name: '테스트 단지',
      address: '서울',
      latitude: 37.55,
      longitude: 126.85,
      listing_count: 1,
      min_price: 500000000,
      max_price: 500000000,
    },
  ], { mapSearchUrl: '/listings/search?sort_by=price_asc' });

  controller.mount(root);
  state.emitMap('dragstart');
  state.emitMap('idle');
  await new Promise((resolve) => setTimeout(resolve, 350));
  state.emitMap('dragstart');
  state.emitMap('idle');
  await new Promise((resolve) => setTimeout(resolve, 350));

  pending[1]({ ok: true, text: async () => '<div id="search-results">latest</div>' });
  await Promise.resolve();
  await Promise.resolve();
  pending[0]({ ok: true, text: async () => '<div id="search-results">stale</div>' });
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(state.swaps, 1);
});
