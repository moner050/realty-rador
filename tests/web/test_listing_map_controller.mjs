import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const controllerSource = readFileSync(
  new URL('../../src/realty_radar/web/static/listing-map.js', import.meta.url),
  'utf8',
);

function createRoot(payload) {
  const container = {};
  const payloadElement = { textContent: JSON.stringify(payload) };
  const status = { textContent: '' };
  return {
    container,
    status,
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

function loadController() {
  const state = { maps: [], markers: [], removedListeners: 0 };
  const fakeWindow = {
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
          addListener() {
            return {};
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
  };
  vm.runInNewContext(controllerSource, { window: fakeWindow, document });
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
  assert.equal(state.removedListeners, 1);
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
