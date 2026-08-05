import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const controllerSource = readFileSync(
  new URL('../../src/realty_radar/web/static/listing-filter-panel.js', import.meta.url),
  'utf8',
);

function element(kind, dataset = {}) {
  const attributes = new Map();
  return {
    kind,
    dataset,
    type: 'text',
    value: '',
    checked: false,
    closest(selector) {
      if (selector.includes(`data-${kind}`)) return this;
      return null;
    },
    getAttribute(name) { return attributes.get(name) ?? null; },
    setAttribute(name, value) { attributes.set(name, String(value)); },
  };
}

function loadFilterPanel({ controls = {} } = {}) {
  const listeners = [];
  const form = {
    requestSubmitCalls: 0,
    requestSubmit() { this.requestSubmitCalls += 1; },
    querySelectorAll(selector) {
      const name = selector.match(/^\[name="(.+)"\]$/)?.[1];
      return name && controls[name] ? [controls[name]] : [];
    },
  };
  const closeListeners = [];
  const modal = {
    dataset: {},
    open: false,
    showModalCalls: 0,
    closeCalls: 0,
    showModal() { this.open = true; this.showModalCalls += 1; },
    close() {
      this.open = false;
      this.closeCalls += 1;
      closeListeners.forEach((listener) => listener());
    },
    addEventListener(event, callback) {
      if (event === 'close') closeListeners.push(callback);
    },
  };
  const mapTrigger = element('map-filter-trigger');
  const toolbarTrigger = element('filter-panel-open');
  const applyButton = element('filter-panel-apply');
  const clearPriceChip = element('applied-filter-clear', {
    filterClearNames: 'min_price_eok,max_price_eok',
  });
  const document = {
    readyState: 'loading',
    querySelector(selector) {
      if (selector === '#listing-search-form') return form;
      if (selector === '#detailed-filter-modal') return modal;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === '[data-map-filter-trigger], [data-filter-panel-open]') {
        return [mapTrigger, toolbarTrigger];
      }
      return [];
    },
    addEventListener(event, callback) { listeners.push({ event, callback }); },
  };
  const window = {};
  vm.runInNewContext(controllerSource, { window, document, CSS: undefined });

  return {
    form,
    modal,
    mapTrigger,
    toolbarTrigger,
    applyButton,
    clearPriceChip,
    controls,
    click(target) {
      const listener = listeners.find((item) => item.event === 'click');
      listener.callback({ target });
    },
    mount() { window.RealtyRadarListingFilterPanel.mount(document); },
  };
}

test('filter triggers open the drawer and announce expanded state', () => {
  const state = loadFilterPanel();
  state.mount();

  state.click(state.mapTrigger);

  assert.equal(state.modal.showModalCalls, 1);
  assert.equal(state.mapTrigger.getAttribute('aria-expanded'), 'true');
});

test('apply submits the existing form once and closes the drawer', () => {
  const state = loadFilterPanel();
  state.mount();
  state.modal.open = true;

  state.click(state.applyButton);

  assert.equal(state.form.requestSubmitCalls, 1);
  assert.equal(state.modal.closeCalls, 1);
  assert.equal(state.mapTrigger.getAttribute('aria-expanded'), 'false');
});

test('applied-condition clear resets matching controls before one submit', () => {
  const state = loadFilterPanel({
    controls: {
      min_price_eok: { type: 'hidden', value: '4' },
      max_price_eok: { type: 'hidden', value: '7' },
    },
  });
  state.mount();

  state.click(state.clearPriceChip);

  assert.equal(state.controls.min_price_eok.value, '');
  assert.equal(state.controls.max_price_eok.value, '');
  assert.equal(state.form.requestSubmitCalls, 1);
});

