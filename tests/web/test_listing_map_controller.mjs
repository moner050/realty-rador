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
  const containerListeners = [];
  const container = {
    addEventListener(event, callback) { containerListeners.push({ event, callback }); },
    removeEventListener(event, callback) {
      const index = containerListeners.findIndex((item) => item.event === event && item.callback === callback);
      if (index >= 0) containerListeners.splice(index, 1);
    },
  };
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
    containerListeners,
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

function loadController({ zoom = 7, mapData = singleClusterPayload, fetchImpl, fitBoundsEventDelay = null } = {}) {
  let currentZoom = zoom;
  let currentViewport = { west: 126.8, south: 37.5, east: 126.9, north: 37.6 };
  const state = {
    maps: [], overlays: [], listeners: [], removedListeners: 0,
    mapFetches: [], cardFetches: [], mapRoot: null,
  };
  function collectionFromHTML(html) {
    const markup = String(html).trim();
    return {
      id: 'listing-collection',
      outerHTML: markup,
      textContent: markup.replace(/<[^>]+>/g, ''),
      replaceWith(replacement) {
        if (state.collection === this) {
          state.collection = replacement;
        }
      },
    };
  }
  state.collection = collectionFromHTML('<section id="listing-collection">initial</section>');
  const fakeWindow = {
    location: { origin: 'http://localhost' },
    fetch: (url, options) => {
      const requested = String(url);
      const isMapRequest = requested.includes('/api/listings/map-data');
      (isMapRequest ? state.mapFetches : state.cardFetches).push(requested);
      if (fetchImpl) return fetchImpl(url, options);
      if (isMapRequest) return Promise.resolve({ ok: true, json: async () => mapData });
      return Promise.resolve({ ok: true, text: async () => '<section id="listing-collection"></section>' });
    },
    htmx: {},
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
            if (fitBoundsEventDelay !== null) {
              setTimeout(() => {
                state.emitMap('zoom_changed');
                state.emitMap('idle');
              }, fitBoundsEventDelay);
            }
          }
          getZoom() { return currentZoom; }
          getBounds() {
            return {
              getSW() { return { lat: () => currentViewport.south, lng: () => currentViewport.west }; },
              getNE() { return { lat: () => currentViewport.north, lng: () => currentViewport.east }; },
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
    createElement(tagName) {
      assert.equal(tagName, 'template');
      let collections = [];
      return {
        content: {
          querySelectorAll(selector) {
            return selector === '#listing-collection' ? collections : [];
          },
        },
        set innerHTML(html) {
          const matches = String(html).match(/id=(["'])listing-collection\1/g) || [];
          collections = matches.map(() => collectionFromHTML(html));
        },
      };
    },
    querySelector(selector) {
      if (selector === '#listing-collection') return state.collection;
      if (selector === '[data-listing-map-root]') return state.mapRoot;
      return null;
    },
  };
  state.document = document;
  vm.runInNewContext(controllerSource, { window: fakeWindow, document, URL, setTimeout, clearTimeout });
  state.flushFetches = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
  state.emitMap = (event) => state.listeners
    .filter((listener) => state.maps.includes(listener.target) && listener.event === event)
    .forEach((listener) => listener.callback());
  state.emitContainer = (root, event) => root.containerListeners
    .filter((listener) => listener.event === event)
    .forEach((listener) => listener.callback());
  state.setViewport = ({ zoom: nextZoom = currentZoom, west, south, east, north }) => {
    currentZoom = nextZoom;
    currentViewport = { west, south, east, north };
  };
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

test('a delayed initial bounds response cannot start a fit whose late events refresh map or cards', async () => {
  let resolveInitial;
  const { controller, state } = loadController({
    fetchImpl: () => new Promise((resolve) => { resolveInitial = resolve; }),
    fitBoundsEventDelay: 350,
  });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.advanceDebounce();
  resolveInitial({
    ok: true,
    json: async () => ({ ...singleClusterPayload, bounds: [126.8, 37.5, 126.9, 37.6] }),
  });
  await state.flushFetches();
  await new Promise((resolve) => setTimeout(resolve, 700));
  await state.flushFetches();

  assert.equal(state.maps[0].options.center.latitude, 36.5);
  assert.equal(state.maps[0].options.center.longitude, 127.8);
  assert.equal(state.maps[0].options.zoom, 7);
  assert.deepEqual(state.maps[0].fitBoundsCalls, []);
  assert.equal(state.mapFetches.length, 1);
  assert.equal(state.cardFetches.length, 0);
});

test('map and card responses for the previous viewport are ignored during the debounce window', async () => {
  const pendingMaps = [];
  const pendingCards = [];
  const { controller, state } = loadController({
    zoom: 12,
    fetchImpl: (url) => new Promise((resolve) => {
      (String(url).includes('/api/listings/map-data') ? pendingMaps : pendingCards).push(resolve);
    }),
  });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });
  const collectionBefore = state.collection;

  controller.mount(root);
  pendingMaps[0]({ ok: true, json: async () => singleClusterPayload });
  await state.flushFetches();
  state.emitMap('dragstart');
  state.emitMap('idle');
  await state.advanceDebounce();
  state.emitMap('dragstart');
  pendingMaps[1]({ ok: true, json: async () => singleClusterPayload });
  pendingCards[0]({ ok: true, text: async () => '<section id="listing-collection">stale</section>' });
  await state.flushFetches();

  assert.equal(state.overlays.length, 1);
  assert.equal(state.collection, collectionBefore);
});

test('a valid cards response replaces the collection without an HTMX swap API and preserves the map root', async () => {
  const { controller, state } = loadController({
    zoom: 12,
    fetchImpl: (url) => String(url).includes('/api/listings/map-data')
      ? Promise.resolve({ ok: true, json: async () => singleClusterPayload })
      : Promise.resolve({ ok: true, text: async () => '<section id="listing-collection">latest</section>' }),
  });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });
  state.mapRoot = root;
  const mapRootBefore = state.document.querySelector('[data-listing-map-root]');
  const collectionBefore = state.collection;

  controller.mount(root);
  await state.flushFetches();
  state.emitMap('dragstart');
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();

  assert.equal(state.document.querySelector('[data-listing-map-root]'), mapRootBefore);
  assert.notEqual(state.collection, collectionBefore);
  assert.equal(state.collection.outerHTML, '<section id="listing-collection">latest</section>');
  assert.equal(state.collection.textContent, 'latest');
});

test('malformed cards HTML keeps the current collection visible and reports the map-card error', async () => {
  const { controller, state } = loadController({
    zoom: 12,
    fetchImpl: (url) => String(url).includes('/api/listings/map-data')
      ? Promise.resolve({ ok: true, json: async () => singleClusterPayload })
      : Promise.resolve({ ok: true, text: async () => '<div>missing collection</div>' }),
  });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });
  const collectionBefore = state.collection;

  controller.mount(root);
  await state.flushFetches();
  state.emitMap('dragstart');
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();

  assert.equal(state.collection, collectionBefore);
  assert.equal(state.collection.textContent, 'initial');
  assert.notEqual(root.status.textContent, '');
});

test('a user drag during the initial period refreshes exactly the changed settled viewport', async () => {
  const { controller, state } = loadController({
    mapData: { ...singleClusterPayload, bounds: [126.8, 37.5, 126.9, 37.6] },
  });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.flushFetches();
  state.setViewport({ zoom: 12, west: 126.91, south: 37.61, east: 127.01, north: 37.71 });
  state.emitMap('dragstart');
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();

  assert.equal(state.mapFetches.length, 2);
  assert.equal(state.cardFetches.length, 1);
  const mapRequest = new URL(state.mapFetches[1]);
  const cardRequest = new URL(state.cardFetches[0]);
  for (const request of [mapRequest, cardRequest]) {
    assert.equal(request.searchParams.get('map_west'), '126.91');
    assert.equal(request.searchParams.get('map_south'), '37.61');
    assert.equal(request.searchParams.get('map_east'), '127.01');
    assert.equal(request.searchParams.get('map_north'), '37.71');
    assert.equal(request.searchParams.get('map_zoom'), '12');
  }
});

test('wheel, keyboard, pointer, and touch zooms refresh exactly once even when NAVER emits first', async (t) => {
  for (const inputEvent of ['wheel', 'keydown', 'pointerdown', 'touchstart']) {
    await t.test(inputEvent, async () => {
      const { controller, state } = loadController({
        mapData: { ...singleClusterPayload, bounds: [126.8, 37.5, 126.9, 37.6] },
      });
      const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

      controller.mount(root);
      await state.flushFetches();
      state.setViewport({ zoom: 12, west: 126.92, south: 37.62, east: 127.02, north: 37.72 });
      state.emitMap('zoom_changed');
      state.emitContainer(root, inputEvent);
      state.emitMap('idle');
      await state.advanceDebounce();
      await state.flushFetches();

      assert.equal(state.mapFetches.length, 2);
      assert.equal(state.cardFetches.length, 1);
      const mapRequest = new URL(state.mapFetches[1]);
      const cardRequest = new URL(state.cardFetches[0]);
      for (const request of [mapRequest, cardRequest]) {
        assert.equal(request.searchParams.get('map_west'), '126.92');
        assert.equal(request.searchParams.get('map_south'), '37.62');
        assert.equal(request.searchParams.get('map_east'), '127.02');
        assert.equal(request.searchParams.get('map_north'), '37.72');
        assert.equal(request.searchParams.get('map_zoom'), '12');
      }
    });
  }
});

test('a cluster click during the initial period fits its bounds and refreshes the changed settled viewport once', async () => {
  const { controller, state } = loadController({
    mapData: { ...singleClusterPayload, bounds: [126.7, 37.4, 127.0, 37.7] },
  });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.flushFetches();
  await state.clickOverlay(0);
  state.setViewport({ zoom: 12, west: 126.82, south: 37.52, east: 126.88, north: 37.58 });
  state.emitMap('zoom_changed');
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();

  assert.deepEqual(state.maps[0].fitBoundsCalls[0], { west: 126.8, south: 37.5, east: 126.9, north: 37.6 });
  assert.equal(state.mapFetches.length, 2);
  assert.equal(state.cardFetches.length, 1);
  const mapRequest = new URL(state.mapFetches[1]);
  const cardRequest = new URL(state.cardFetches[0]);
  for (const request of [mapRequest, cardRequest]) {
    assert.equal(request.searchParams.get('map_west'), '126.82');
    assert.equal(request.searchParams.get('map_south'), '37.52');
    assert.equal(request.searchParams.get('map_east'), '126.88');
    assert.equal(request.searchParams.get('map_north'), '37.58');
    assert.equal(request.searchParams.get('map_zoom'), '12');
  }
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
  const latestCollection = state.collection;
  pendingMaps[0]({ ok: true, json: async () => ({ ...singleClusterPayload, clusters: [] }) });
  pendingMaps[1]({ ok: true, json: async () => ({ ...singleClusterPayload, clusters: [] }) });
  pendingCards[0]({ ok: true, text: async () => '<section id="listing-collection">stale</section>' });
  await state.flushFetches();

  assert.equal(state.overlays.length, 1);
  assert.equal(state.collection, latestCollection);
  assert.equal(state.collection.textContent, 'latest');
});

test('unmount cancels a pending viewport refresh and removes dynamic overlays and every map listener', async () => {
  const { controller, state } = loadController({ mapData: singleClusterPayload });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.flushFetches();
  state.setViewport({ zoom: 12, west: 126.91, south: 37.61, east: 127.01, north: 37.71 });
  state.emitMap('dragstart');
  state.emitMap('idle');
  controller.unmount(root);
  await state.advanceDebounce();
  await state.flushFetches();

  assert.equal(state.overlays[0].map, null);
  assert.equal(state.removedListeners, state.listeners.length);
  assert.equal(state.mapFetches.length, 1);
  assert.equal(state.cardFetches.length, 0);
});
