import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const controllerSource = readFileSync(
  new URL('../../src/realty_radar/web/static/listing-map.js', import.meta.url),
  'utf8',
);

const singleClusterPayload = {
  mode: 'markers',
  markers: [],
  clusters: [{
    kind: 'cluster', latitude: 37.55, longitude: 126.85,
    west: 126.8, south: 37.5, east: 126.9, north: 37.6,
    complex_count: 12, listing_count: 35, min_price: 500000000, max_price: 700000000,
  }],
  matching_complex_count: 12, mapped_complex_count: 12, unmapped_complex_count: 0,
  mapped_listing_count: 35,
  bounds: null,
};

const sidoCirclePayload = {
  mode: 'sido',
  markers: [],
  clusters: [{
    kind: 'cluster', label: '서울특별시', latitude: 37.55, longitude: 126.85,
    west: 126.8, south: 37.5, east: 127.1, north: 37.7,
    complex_count: 12, listing_count: 12500, min_price: 500000000, max_price: 700000000,
  }],
  matching_complex_count: 12,
  mapped_complex_count: 12,
  unmapped_complex_count: 0,
  mapped_listing_count: 35,
  bounds: null,
};

function createRoot({ mapDataUrl, mapCardsUrl, mapComplexUrlTemplate = '/listings/complex/__complex_id__' }) {
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
  const summary = {
    hidden: true,
    classList: { toggle() {} },
    setAttribute() {},
  };
  const summaryCount = { textContent: '0' };
  const cardLoading = {
    hidden: true,
    classList: { toggle() {} },
    setAttribute() {},
  };
  const modalContent = {
    title: { textContent: '' },
    address: { textContent: '' },
    price: { textContent: '' },
    listings: { innerHTML: '' },
  };
  const modal = {
    open: false,
    showModalCalls: 0,
    closeCalls: 0,
    showModal() { this.open = true; this.showModalCalls += 1; },
    close() { this.open = false; this.closeCalls += 1; },
    querySelector(selector) {
      if (selector === '[data-map-complex-title]') return modalContent.title;
      if (selector === '[data-map-complex-address]') return modalContent.address;
      if (selector === '[data-map-complex-price]') return modalContent.price;
      if (selector === '[data-map-complex-listings]') return modalContent.listings;
      return null;
    },
  };
  const closeButton = {
    addEventListener(event, callback) { this.callback = event === 'click' ? callback : null; },
  };
  return {
    container,
    containerListeners,
    status,
    dataset: { mapDataUrl, mapCardsUrl, mapComplexUrlTemplate },
    matches(selector) { return selector === '[data-listing-map-root]'; },
    setAttribute() {},
    querySelector(selector) {
      if (selector === '[data-listings-map]') return container;
      if (selector === '[data-listing-map-status]') return status;
      if (selector === '[data-map-loading]') return loading;
      if (selector === '[data-map-summary]') return summary;
      if (selector === '[data-map-summary-count]') return summaryCount;
      if (selector === '[data-map-complex-modal]') return modal;
      if (selector === '[data-map-complex-close]') return closeButton;
      if (selector === '[data-map-matching-count]') return counts.matching;
      if (selector === '[data-map-mapped-count]') return counts.mapped;
      if (selector === '[data-map-unmapped-count]') return counts.unmapped;
      return null;
    },
    summary,
    summaryCount,
    cardLoading,
    modal,
    modalContent,
  };
}

function loadController({
  zoom = 7, mapData = singleClusterPayload, fetchImpl, fitBoundsEventDelay = null, htmx = {},
} = {}) {
  let currentZoom = zoom;
  let currentViewport = { west: 126.8, south: 37.5, east: 126.9, north: 37.6 };
  const state = {
    maps: [], overlays: [], listeners: [], removedListeners: 0,
    mapFetches: [], cardFetches: [], complexFetches: [], mapRoot: null,
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
      if (isMapRequest) state.mapFetches.push(requested);
      else if (requested.includes('/listings/complex/')) state.complexFetches.push(requested);
      else state.cardFetches.push(requested);
      if (fetchImpl) return fetchImpl(url, options);
      if (isMapRequest) return Promise.resolve({ ok: true, json: async () => mapData });
      return Promise.resolve({ ok: true, text: async () => '<section id="listing-collection"></section>' });
    },
    htmx,
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
          updateBy(position, nextZoom) {
            this.updateByCalls = this.updateByCalls || [];
            this.updateByCalls.push({ latitude: position.lat(), longitude: position.lng(), zoom: nextZoom });
            currentZoom = nextZoom;
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
      if (selector === '[data-card-loading]') return state.mapRoot && state.mapRoot.cardLoading;
      return null;
    },
  };
  state.document = document;
  vm.runInNewContext(controllerSource, { window: fakeWindow, document, URL, setTimeout, clearTimeout, AbortController });
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
  state.advanceDebounce = () => new Promise((resolve) => setTimeout(resolve, 1520));
  return { controller: fakeWindow.RealtyRadarListingMap, state };
}

test('zoomed-out map data renders one labelled sido circle and does not request cards', async () => {
  const { controller, state } = loadController({ zoom: 8, mapData: sidoCirclePayload });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  state.emitMap('zoom_changed');
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();

  assert.equal(state.maps[0].options.center.latitude, 37.55);
  assert.equal(state.maps[0].options.center.longitude, 126.9);
  assert.equal(state.maps[0].options.zoom, 8);
  assert.doesNotMatch(state.mapFetches[0], /map_initial=true/);
  const initialRequest = new URL(state.mapFetches[0]);
  assert.equal(initialRequest.searchParams.get('map_west'), '126.8');
  assert.equal(initialRequest.searchParams.get('map_north'), '37.6');
  assert.equal(state.overlays.length, 1);
  assert.equal(root.summary.hidden, true);
  assert.match(state.overlays[0].options.icon.content, /서울특별시/);
  assert.match(state.overlays[0].options.icon.content, /1\.3만 건/);
  assert.equal(state.cardFetches.length, 0);
});

test('initial metropolitan map waits 1.5 seconds after user movement before fetching map and cards together', async () => {
  const { controller, state } = loadController();
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.flushFetches();

  assert.equal(state.maps[0].options.center.latitude, 37.55);
  assert.equal(state.maps[0].options.center.longitude, 126.9);
  assert.equal(state.maps[0].options.zoom, 8);
  assert.equal(state.mapFetches.length, 0);
  assert.equal(state.cardFetches.length, 0);

  state.setViewport({ zoom: 12, west: 126.91, south: 37.61, east: 127.01, north: 37.71 });
  state.emitMap('zoom_changed');
  state.emitMap('idle');
  await new Promise((resolve) => setTimeout(resolve, 1400));
  await state.flushFetches();

  assert.equal(state.mapFetches.length, 0);
  assert.equal(state.cardFetches.length, 0);

  await new Promise((resolve) => setTimeout(resolve, 150));
  await state.flushFetches();

  assert.equal(state.mapFetches.length, 1);
  assert.equal(state.cardFetches.length, 1);
});

test('settled viewport starts markers and cards together after the shared delay', async () => {
  const { controller, state } = loadController({ zoom: 12 });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.flushFetches();
  state.setViewport({ zoom: 12, west: 126.91, south: 37.61, east: 127.01, north: 37.71 });
  state.emitMap('dragstart');
  state.emitMap('idle');
  await new Promise((resolve) => setTimeout(resolve, 1400));
  await state.flushFetches();

  assert.equal(state.mapFetches.length, 0);
  assert.equal(state.cardFetches.length, 0);

  await new Promise((resolve) => setTimeout(resolve, 150));
  await state.flushFetches();

  assert.equal(state.mapFetches.length, 1);
  assert.equal(state.cardFetches.length, 1);
});

test('a newer viewport aborts in-flight marker and card requests before the next refresh', async () => {
  const mapSignals = [];
  const cardSignals = [];
  const { controller, state } = loadController({
    zoom: 12,
    fetchImpl: (url, options = {}) => {
      (String(url).includes('/api/listings/map-data') ? mapSignals : cardSignals).push(options.signal);
      return new Promise(() => {});
    },
  });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  state.setViewport({ zoom: 12, west: 126.91, south: 37.61, east: 127.01, north: 37.71 });
  state.emitMap('dragstart');
  state.emitMap('idle');
  await state.advanceDebounce();
  state.setViewport({ zoom: 12, west: 127.01, south: 37.71, east: 127.11, north: 37.81 });
  state.emitMap('dragstart');

  assert.equal(mapSignals.length, 1);
  assert.equal(cardSignals.length, 1);
  assert.equal(mapSignals[0].aborted, true);
  assert.equal(cardSignals[0].aborted, true);
});

test('a list focus moves the mounted map directly to the supplied coordinate and zoom', async () => {
  const { controller, state } = loadController({ mapData: sidoCirclePayload });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  await state.flushFetches();

  assert.equal(controller.focus({ mapFocusLatitude: '37.551', mapFocusLongitude: '126.851' }), true);
  assert.deepEqual(state.maps[0].updateByCalls, [{ latitude: 37.551, longitude: 126.851, zoom: 15 }]);
});

test('a real complex marker opens a modal and loads that complex\'s matching listings', async () => {
  const markerPayload = {
    ...singleClusterPayload,
    markers: [{
      kind: 'marker', complex_id: 7, complex_name: '테스트 단지', address: '서울시 테스트로 7',
      latitude: 37.551, longitude: 126.851, listing_count: 2, min_price: 500000000, max_price: 550000000,
    }],
    clusters: [],
  };
  const { controller, state } = loadController({
    zoom: 15,
    mapData: markerPayload,
    fetchImpl: (url) => String(url).includes('/api/listings/map-data')
      ? Promise.resolve({ ok: true, json: async () => markerPayload })
      : Promise.resolve({ ok: true, text: async () => '<article>complex listing</article>' }),
  });
  const root = createRoot({
    mapDataUrl: '/api/listings/map-data',
    mapCardsUrl: '/listings/map-cards',
    mapComplexUrlTemplate: '/listings/complex/__complex_id__?trade_types=SALE',
  });

  controller.mount(root);
  state.setViewport({ zoom: 15, west: 126.91, south: 37.61, east: 127.01, north: 37.71 });
  state.emitMap('zoom_changed');
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();
  await state.clickOverlay(0);

  assert.equal(root.modal.showModalCalls, 1);
  assert.equal(root.modalContent.title.textContent, '테스트 단지');
  assert.equal(root.modalContent.address.textContent, '서울시 테스트로 7');
  assert.match(root.modalContent.price.textContent, /2건/);
  assert.equal(root.modalContent.listings.innerHTML, '<article>complex listing</article>');
  assert.equal(state.complexFetches[0], '/listings/complex/7?trade_types=SALE');
});

test('a delayed first viewport response cannot start a fit whose late events refresh map or cards', async () => {
  let resolveInitial;
  const { controller, state } = loadController({
    fetchImpl: () => new Promise((resolve) => { resolveInitial = resolve; }),
    fitBoundsEventDelay: 350,
  });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });

  controller.mount(root);
  state.emitMap('zoom_changed');
  state.emitMap('idle');
  await state.advanceDebounce();
  resolveInitial({
    ok: true,
    json: async () => ({ ...singleClusterPayload, bounds: [126.8, 37.5, 126.9, 37.6] }),
  });
  await state.flushFetches();
  await new Promise((resolve) => setTimeout(resolve, 700));
  await state.flushFetches();

  assert.equal(state.maps[0].options.center.latitude, 37.55);
  assert.equal(state.maps[0].options.center.longitude, 126.9);
  assert.equal(state.maps[0].options.zoom, 8);
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
  state.setViewport({ zoom: 12, west: 126.8, south: 37.5, east: 126.9, north: 37.6 });
  state.emitMap('zoom_changed');
  state.emitMap('idle');
  await state.advanceDebounce();
  pendingMaps[0]({ ok: true, json: async () => singleClusterPayload });
  await state.flushFetches();
  state.setViewport({ zoom: 12, west: 126.91, south: 37.61, east: 127.01, north: 37.71 });
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
  state.emitMap('zoom_changed');
  state.emitMap('idle');
  await state.advanceDebounce();
  state.emitMap('dragstart');
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();

  assert.equal(state.document.querySelector('[data-listing-map-root]'), mapRootBefore);
  assert.notEqual(state.collection, collectionBefore);
  assert.equal(state.collection.outerHTML, '<section id="listing-collection">latest</section>');
  assert.equal(state.collection.textContent, 'latest');
});

test('a valid cards response processes the replacement exactly once when HTMX process is available', async () => {
  const processed = [];
  const { controller, state } = loadController({
    zoom: 12,
    htmx: { process(element) { processed.push(element); } },
    fetchImpl: (url) => String(url).includes('/api/listings/map-data')
      ? Promise.resolve({ ok: true, json: async () => singleClusterPayload })
      : Promise.resolve({ ok: true, text: async () => '<section id="listing-collection">processed</section>' }),
  });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });
  state.mapRoot = root;
  const mapRootBefore = state.document.querySelector('[data-listing-map-root]');
  const collectionBefore = state.collection;

  controller.mount(root);
  state.emitMap('dragstart');
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();

  assert.notEqual(state.collection, collectionBefore);
  assert.deepEqual(processed, [state.collection]);
  assert.equal(state.collection.textContent, 'processed');
  assert.equal(state.document.querySelector('[data-listing-map-root]'), mapRootBefore);
});

test('an HTMX process failure keeps the replaced cards and map root visible while reporting the error', async () => {
  const { controller, state } = loadController({
    zoom: 12,
    htmx: { process() { throw new Error('process failed'); } },
    fetchImpl: (url) => String(url).includes('/api/listings/map-data')
      ? Promise.resolve({ ok: true, json: async () => singleClusterPayload })
      : Promise.resolve({ ok: true, text: async () => '<section id="listing-collection">still visible</section>' }),
  });
  const root = createRoot({ mapDataUrl: '/api/listings/map-data', mapCardsUrl: '/listings/map-cards' });
  state.mapRoot = root;
  const mapRootBefore = state.document.querySelector('[data-listing-map-root]');
  const collectionBefore = state.collection;

  controller.mount(root);
  state.emitMap('dragstart');
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();

  assert.notEqual(state.collection, collectionBefore);
  assert.equal(state.collection.textContent, 'still visible');
  assert.equal(state.document.querySelector('[data-listing-map-root]'), mapRootBefore);
  assert.notEqual(root.status.textContent, '');
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
  state.setViewport({ zoom: 12, west: 126.91, south: 37.61, east: 127.01, north: 37.71 });
  state.emitMap('dragstart');
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();

  assert.equal(state.mapFetches.length, 1);
  assert.equal(state.cardFetches.length, 1);
  const mapRequest = new URL(state.mapFetches[0]);
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
      state.setViewport({ zoom: 12, west: 126.92, south: 37.62, east: 127.02, north: 37.72 });
      state.emitMap('zoom_changed');
      state.emitContainer(root, inputEvent);
      state.emitMap('idle');
      await state.advanceDebounce();
      await state.flushFetches();

      assert.equal(state.mapFetches.length, 1);
      assert.equal(state.cardFetches.length, 1);
      const mapRequest = new URL(state.mapFetches[0]);
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
  state.setViewport({ zoom: 12, west: 126.8, south: 37.5, east: 126.9, north: 37.6 });
  state.emitMap('zoom_changed');
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();
  await state.clickOverlay(0);
  state.setViewport({ zoom: 12, west: 126.82, south: 37.52, east: 126.88, north: 37.58 });
  state.emitMap('zoom_changed');
  state.emitMap('idle');
  await state.advanceDebounce();
  await state.flushFetches();

  assert.deepEqual(state.maps[0].fitBoundsCalls[0], { west: 126.8, south: 37.5, east: 126.9, north: 37.6 });
  assert.equal(state.mapFetches.length, 2);
  assert.equal(state.cardFetches.length, 2);
  const mapRequest = new URL(state.mapFetches[1]);
  const cardRequest = new URL(state.cardFetches[1]);
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

  pendingMaps[1]({ ok: true, json: async () => singleClusterPayload });
  pendingCards[1]({ ok: true, text: async () => '<section id="listing-collection">latest</section>' });
  await state.flushFetches();
  const latestCollection = state.collection;
  pendingMaps[0]({ ok: true, json: async () => ({ ...singleClusterPayload, clusters: [] }) });
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
  state.emitMap('zoom_changed');
  state.emitMap('idle');
  await state.advanceDebounce();
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
