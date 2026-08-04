import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const controllerSource = readFileSync(
  new URL('../../src/realty_radar/web/static/listing-map.js', import.meta.url),
  'utf8',
);

const singleClusterPayload = {
  markers: [],
  clusters: [{
    kind: 'cluster', latitude: 37.55, longitude: 126.85,
    west: 126.8, south: 37.5, east: 126.9, north: 37.6,
    complex_count: 12, listing_count: 35, min_price: 500000000, max_price: 700000000,
  }],
  matching_complex_count: 12, mapped_complex_count: 12, unmapped_complex_count: 0,
  bounds: null,
};

function createRoot({ mapDataUrl, mapCardsUrl }) {
  const container = {};
  const status = { textContent: '' };
  const loading = {
    hidden: true,
    classList: { toggle() {} },
    setAttribute() {},
  };
  const counts = {
    matching: { textContent: '0' },
    mapped: { textContent: '0' },
    unmapped: { textContent: '0' },
  };
  return {
    container,
    status,
    dataset: { mapDataUrl, mapCardsUrl },
    matches(selector) { return selector === '[data-listing-map-root]'; },
    setAttribute() {},
    querySelector(selector) {
      if (selector === '[data-listings-map]') return container;
      if (selector === '[data-listing-map-status]') return status;
      if (selector === '[data-map-loading]') return loading;
      if (selector === '[data-map-matching-count]') return counts.matching;
      if (selector === '[data-map-mapped-count]') return counts.mapped;
      if (selector === '[data-map-unmapped-count]') return counts.unmapped;
      return null;
    },
  };
}

function loadController({ zoom = 7, mapData = singleClusterPayload, fetchImpl } = {}) {
  const state = {
    maps: [], overlays: [], listeners: [], removedListeners: 0,
    mapFetches: [], cardFetches: [], cardSwaps: 0, mapSwaps: 0,
  };
  const fakeWindow = {
    location: { origin: 'http://localhost' },
    fetch: fetchImpl || (async (url) => {
      const requested = String(url);
      if (requested.includes('/api/listings/map-data')) {
        state.mapFetches.push(requested);
        return { ok: true, json: async () => mapData };
      }
      state.cardFetches.push(requested);
      return { ok: true, text: async () => '<section id="listing-collection"></section>' };
    }),
    htmx: {
      swap(target) {
        if (target && target.id === 'listing-collection') state.cardSwaps += 1;
        else state.mapSwaps += 1;
      },
    },
    naver: {
      maps: {
        LatLng: class LatLng {
          constructor(latitude, longitude) { this.latitude = latitude; this.longitude = longitude; }
          lat() { return this.latitude; }
          lng() { return this.longitude; }
        },
        LatLngBounds: class LatLngBounds {
          constructor(southwest, northeast) {
            this.west = southwest && southwest.lng();
            this.south = southwest && southwest.lat();
            this.east = northeast && northeast.lng();
            this.north = northeast && northeast.lat();
          }
        },
        Point: class Point {
          constructor(x, y) { this.x = x; this.y = y; }
        },
        Map: class Map {
          constructor(container, options) {
            this.container = container; this.options = options; this.fitBoundsCalls = [];
            state.maps.push(this);
          }
          fitBounds(bounds) {
            this.fitBoundsCalls.push({ west: bounds.west, south: bounds.south, east: bounds.east, north: bounds.north });
          }
          getZoom() { return zoom; }
          getBounds() {
            return {
              getSW() { return { lat: () => 37.5, lng: () => 126.8 }; },
              getNE() { return { lat: () => 37.6, lng: () => 126.9 }; },
            };
          }
        },
        Marker: class Marker {
          constructor(options) { this.options = options; this.map = options.map; state.overlays.push(this); }
          setMap(map) { this.map = map; }
        },
        InfoWindow: class InfoWindow {
          setContent() {}
          open() {}
          close() {}
        },
        Event: {
          addListener(target, event, callback) {
            const listener = { target, event, callback };
            state.listeners.push(listener);
            return listener;
          },
          removeListener() { state.removedListeners += 1; },
        },
      },
    },
  };
  const document = {
    addEventListener() {},
    querySelector(selector) {
      return selector === '#listing-collection' ? { id: 'listing-collection' } : null;
    },
  };
  vm.runInNewContext(controllerSource, { window: fakeWindow, document, URL, setTimeout, clearTimeout });
  state.flushFetches = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
  state.emitMap = (event) => state.listeners
    .filter((listener) => state.maps.includes(listener.target) && listener.event === event)
    .forEach((listener) => listener.callback());
  state.clickOverlay = async (index) => {
    const listener = state.listeners.find((item) => item.target === state.overlays[index] && item.event === 'click');
    assert.ok(listener, 'the overlay has a click listener');
    listener.callback();
    await state.flushFetches();
  };
  state.advanceDebounce = () => new Promise((resolve) => setTimeout(resolve, 320));
  return { controller: fakeWindow.RealtyRadarListingMap, state };
}

test('map data renders a count cluster and does not swap cards while zoomed out', async () => {
  const { controller, state } = loadController({ mapData: singleClusterPayload });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.flushFetches();

  assert.equal(state.maps[0].options.center.latitude, 36.5);
  assert.equal(state.maps[0].options.center.longitude, 127.8);
  assert.equal(state.maps[0].options.zoom, 7);
  assert.match(state.mapFetches[0], /map_initial=true/);
  assert.equal(state.overlays.length, 1);
  assert.match(state.overlays[0].options.icon.content, /12\uac1c \ub2e8\uc9c0/);
  assert.equal(state.cardFetches.length, 0);
});

test('the first map payload applies its all-results bounds once', async () => {
  const { controller, state } = loadController({
    mapData: { ...singleClusterPayload, bounds: [126.8, 37.5, 126.9, 37.6] },
  });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.flushFetches();

  assert.deepEqual(state.maps[0].fitBoundsCalls, [
    { west: 126.8, south: 37.5, east: 126.9, north: 37.6 },
  ]);
});

test('cluster click fits its stored bounds and a valid idle later refreshes cards only', async () => {
  const { controller, state } = loadController({ zoom: 12, mapData: singleClusterPayload });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.flushFetches();
  await state.clickOverlay(0);
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();

  assert.deepEqual(state.maps[0].fitBoundsCalls[0], { west: 126.8, south: 37.5, east: 126.9, north: 37.6 });
  assert.equal(state.cardSwaps, 1);
  assert.equal(state.mapSwaps, 0);
  assert.equal(state.maps.length, 1);
});

test('stale map and card responses cannot replace the latest settled viewport', async () => {
  const pendingMaps = [];
  const pendingCards = [];
  const { controller, state } = loadController({
    zoom: 12,
    fetchImpl: (url) => new Promise((resolve) => {
      (String(url).includes('/api/listings/map-data') ? pendingMaps : pendingCards).push(resolve);
    }),
  });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  state.emitMap('dragstart');
  state.emitMap('idle');
  await state.advanceDebounce();
  state.emitMap('dragstart');
  state.emitMap('idle');
  await state.advanceDebounce();

  pendingMaps[2]({ ok: true, json: async () => singleClusterPayload });
  pendingCards[1]({ ok: true, text: async () => '<section id="listing-collection">latest</section>' });
  await state.flushFetches();
  pendingMaps[0]({ ok: true, json: async () => ({ ...singleClusterPayload, clusters: [] }) });
  pendingMaps[1]({ ok: true, json: async () => ({ ...singleClusterPayload, clusters: [] }) });
  pendingCards[0]({ ok: true, text: async () => '<section id="listing-collection">stale</section>' });
  await state.flushFetches();

  assert.equal(state.overlays.length, 1);
  assert.equal(state.cardSwaps, 1);
});

test('unmount removes dynamic overlays and every map listener', async () => {
  const { controller, state } = loadController({ mapData: singleClusterPayload });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.flushFetches();
  controller.unmount(root);

  assert.equal(state.overlays[0].map, null);
  assert.equal(state.removedListeners, state.listeners.length);
});
