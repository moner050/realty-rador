(function (window, document) {
    "use strict";

    const instances = new WeakMap();
    const VIEWPORT_SEARCH_DEBOUNCE_MS = 1500;
    const INITIAL_LATITUDE = 37.55;
    const INITIAL_LONGITUDE = 126.9;
    const INITIAL_ZOOM = 8;
    const FOCUS_ZOOM = 15;
    const MIN_SEARCH_ZOOM = 11;
    const MAX_LATITUDE_SPAN = 1.5;
    const MAX_LONGITUDE_SPAN = 1.5;
    let activeInstance = null;

    function findRoot(source) {
        if (!source) return null;
        if (typeof source.matches === "function" && source.matches("[data-listing-map-root]")) return source;
        return typeof source.querySelector === "function"
            ? source.querySelector("[data-listing-map-root]")
            : null;
    }

    function formatPrice(won) {
        return `${Number(won).toLocaleString("ko-KR")}원`;
    }

    function formatListingCount(count) {
        const numeric = Number(count) || 0;
        if (numeric >= 10_000) return `${(numeric / 10_000).toFixed(1).replace(/\.0$/, "")}만 건`;
        if (numeric >= 1_000) return `${(numeric / 1_000).toFixed(1).replace(/\.0$/, "")}천 건`;
        return `${numeric.toLocaleString("ko-KR")}건`;
    }

    function escapeHtml(value) {
        return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function setStatus(root, message) {
        const status = root.querySelector("[data-listing-map-status]");
        if (status) status.textContent = message;
    }

    function setIndicator(element, isLoading) {
        if (!element) return;
        element.hidden = !isLoading;
        if (element.classList) element.classList.toggle("hidden", !isLoading);
        if (typeof element.setAttribute === "function") element.setAttribute("aria-hidden", String(!isLoading));
    }

    function syncLoading(root, instance) {
        setIndicator(root.querySelector("[data-map-loading]"), instance.pendingMap);
        setIndicator(document.querySelector("[data-card-loading]"), instance.pendingCards);
        if (typeof root.setAttribute === "function") {
            root.setAttribute("aria-busy", String(instance.pendingMap || instance.pendingCards));
        }
    }

    function coordinateValue(point, name) {
        if (!point) return null;
        const value = point[name];
        const numeric = Number(typeof value === "function" ? value.call(point) : value);
        return Number.isFinite(numeric) ? numeric : null;
    }

    function viewportFromMap(map) {
        if (!map || typeof map.getBounds !== "function") return null;
        const bounds = map.getBounds();
        if (!bounds || typeof bounds.getSW !== "function" || typeof bounds.getNE !== "function") return null;
        const southwest = bounds.getSW();
        const northeast = bounds.getNE();
        const west = coordinateValue(southwest, "lng");
        const south = coordinateValue(southwest, "lat");
        const east = coordinateValue(northeast, "lng");
        const north = coordinateValue(northeast, "lat");
        if ([west, south, east, north].some((value) => value === null) || west >= east || south >= north) return null;
        return { west, south, east, north };
    }

    function viewportKey(map, viewport) {
        const zoom = Number(map.getZoom());
        if (!viewport || !Number.isFinite(zoom)) return null;
        return [zoom, viewport.west, viewport.south, viewport.east, viewport.north]
            .map((value) => Number(value).toFixed(6))
            .join(":");
    }

    function canRefreshCards(map, viewport) {
        const zoom = typeof map.getZoom === "function" ? Number(map.getZoom()) : null;
        return Boolean(
            viewport
            && Number.isFinite(zoom)
            && zoom >= MIN_SEARCH_ZOOM
            && viewport.north - viewport.south <= MAX_LATITUDE_SPAN
            && viewport.east - viewport.west <= MAX_LONGITUDE_SPAN
        );
    }

    function makeAbortController() {
        return typeof AbortController === "function" ? new AbortController() : null;
    }

    function cancelMapRequest(root, instance) {
        if (instance.mapAbortController) instance.mapAbortController.abort();
        instance.mapAbortController = null;
        instance.mapRequestId += 1;
        if (instance.pendingMap) {
            instance.pendingMap = false;
            syncLoading(root, instance);
        }
    }

    function cancelCardsRequest(root, instance) {
        if (instance.cardsAbortController) instance.cardsAbortController.abort();
        instance.cardsAbortController = null;
        instance.cardsRequestId += 1;
        if (instance.pendingCards) {
            instance.pendingCards = false;
            syncLoading(root, instance);
        }
    }

    function markViewportDirty(root, instance) {
        cancelMapRequest(root, instance);
        cancelCardsRequest(root, instance);
        instance.viewportDirty = true;
    }

    function requestUrl(baseUrl, map, viewport, initial) {
        const url = new URL(baseUrl, (window.location && window.location.origin) || "http://localhost");
        url.searchParams.delete("cursor");
        url.searchParams.set("map_west", String(viewport.west));
        url.searchParams.set("map_south", String(viewport.south));
        url.searchParams.set("map_east", String(viewport.east));
        url.searchParams.set("map_north", String(viewport.north));
        url.searchParams.set("map_zoom", String(map.getZoom()));
        if (initial) url.searchParams.set("map_initial", "true");
        return url;
    }

    function removeListeners(instance, listeners) {
        listeners.forEach((listener) => window.naver.maps.Event.removeListener(listener));
        instance.listeners = instance.listeners.filter((listener) => !listeners.includes(listener));
    }

    function clearOverlays(instance) {
        removeListeners(instance, instance.overlayListeners);
        instance.overlayListeners = [];
        instance.overlays.forEach((overlay) => overlay.setMap(null));
        instance.overlays = [];
    }

    function boundsFromValues(west, south, east, north) {
        return new window.naver.maps.LatLngBounds(
            new window.naver.maps.LatLng(south, west),
            new window.naver.maps.LatLng(north, east),
        );
    }

    function processDynamicContent(element) {
        if (window.htmx && typeof window.htmx.process === "function") window.htmx.process(element);
        if (window.Alpine && typeof window.Alpine.initTree === "function") window.Alpine.initTree(element);
    }

    function openComplexModal(root, instance, item) {
        const modal = root.querySelector("[data-map-complex-modal]");
        const template = root.dataset && root.dataset.mapComplexUrlTemplate;
        if (!modal || !template || typeof window.fetch !== "function") return;
        const title = modal.querySelector("[data-map-complex-title]");
        const address = modal.querySelector("[data-map-complex-address]");
        const price = modal.querySelector("[data-map-complex-price]");
        const listings = modal.querySelector("[data-map-complex-listings]");
        if (title) title.textContent = item.complex_name;
        if (address) address.textContent = item.address;
        if (price) price.textContent = `${item.listing_count}건 · ${formatPrice(item.min_price)} ~ ${formatPrice(item.max_price)}`;
        if (listings) listings.innerHTML = '<p class="text-sm font-semibold text-slate-500">매물을 불러오는 중입니다.</p>';
        if (typeof modal.showModal === "function" && !modal.open) modal.showModal();

        if (instance.complexAbortController) instance.complexAbortController.abort();
        const controller = makeAbortController();
        instance.complexAbortController = controller;
        const requestId = ++instance.complexRequestId;
        const url = template.replace("__complex_id__", encodeURIComponent(String(item.complex_id)));
        const options = { headers: { "HX-Request": "true" } };
        if (controller) options.signal = controller.signal;
        window.fetch(url, options)
            .then((response) => {
                if (!response.ok) throw new Error("complex listings failed");
                return response.text();
            })
            .then((html) => {
                if (instance.complexRequestId !== requestId || !listings) return;
                listings.innerHTML = html;
                processDynamicContent(listings);
            })
            .catch((error) => {
                if (instance.complexRequestId !== requestId || (error && error.name === "AbortError")) return;
                if (listings) listings.innerHTML = '<p class="text-sm font-semibold text-rose-600">단지 매물을 불러오지 못했습니다. 다시 시도해 주세요.</p>';
            });
    }

    function makeClusterOverlay(map, instance, cluster) {
        const label = cluster.label
            ? `${escapeHtml(cluster.label)} · ${escapeHtml(formatListingCount(cluster.listing_count))}`
            : `${escapeHtml(formatListingCount(cluster.listing_count))} · ${escapeHtml(cluster.complex_count)}개 단지`;
        const marker = new window.naver.maps.Marker({
            map,
            position: new window.naver.maps.LatLng(cluster.latitude, cluster.longitude),
            title: cluster.label || `${cluster.complex_count}개 단지`,
            icon: {
                content: `<div class="rounded-full bg-indigo-600 px-3 py-1.5 text-xs font-extrabold text-white shadow-lg">${label}</div>`,
                anchor: new window.naver.maps.Point(0, 0),
            },
        });
        const listener = window.naver.maps.Event.addListener(marker, "click", () => {
            markViewportDirty(instance.root, instance);
            map.fitBounds(boundsFromValues(cluster.west, cluster.south, cluster.east, cluster.north));
        });
        instance.listeners.push(listener);
        instance.overlayListeners.push(listener);
        return marker;
    }

    function makeMarkerOverlay(root, map, instance, item) {
        const marker = new window.naver.maps.Marker({
            map,
            position: new window.naver.maps.LatLng(item.latitude, item.longitude),
            title: item.complex_name,
            icon: {
                content: `<div class="rounded-lg bg-white px-2 py-1 text-xs font-extrabold text-slate-900 shadow-lg ring-1 ring-indigo-200">${escapeHtml(formatPrice(item.min_price))} <span class="text-slate-500">${escapeHtml(item.listing_count)}건</span></div>`,
                anchor: new window.naver.maps.Point(0, 0),
            },
        });
        const listener = window.naver.maps.Event.addListener(marker, "click", () => openComplexModal(root, instance, item));
        instance.listeners.push(listener);
        instance.overlayListeners.push(listener);
        return marker;
    }

    function renderViewport(root, map, instance, payload) {
        const counts = [
            ["[data-map-matching-count]", payload.matching_complex_count],
            ["[data-map-mapped-count]", payload.mapped_complex_count],
            ["[data-map-unmapped-count]", payload.unmapped_complex_count],
        ];
        counts.forEach(([selector, count]) => {
            const target = root.querySelector(selector);
            if (target) target.textContent = String(count || 0);
        });
        const summary = root.querySelector("[data-map-summary]");
        const summaryCount = root.querySelector("[data-map-summary-count]");
        if (payload.mode === "summary") {
            clearOverlays(instance);
            if (summaryCount) summaryCount.textContent = String(payload.mapped_listing_count || 0);
            setIndicator(summary, true);
            setStatus(root, "지도를 더 확대하면 단지와 해당 영역의 매물을 확인할 수 있습니다.");
            return;
        }
        setIndicator(summary, false);
        clearOverlays(instance);
        (payload.clusters || []).forEach((cluster) => instance.overlays.push(makeClusterOverlay(map, instance, cluster)));
        (payload.markers || []).forEach((marker) => instance.overlays.push(makeMarkerOverlay(root, map, instance, marker)));
        const modeMessages = {
            sido: "시·도별 조건 충족 매물 수입니다. 원을 누르면 해당 지역으로 확대합니다.",
            sigungu: "시군구별 조건 충족 매물 수입니다. 원을 누르면 해당 지역으로 확대합니다.",
            clusters: "가까운 단지 묶음입니다. 원을 누르면 해당 위치로 확대합니다.",
            markers: "단지를 누르면 조건에 맞는 매물을 확인할 수 있습니다.",
        };
        setStatus(root, modeMessages[payload.mode] || "");
    }

    function requestMapData(root, map, instance, { initial = false, key = null } = {}) {
        const viewport = viewportFromMap(map);
        const baseUrl = root.dataset && root.dataset.mapDataUrl;
        const currentKey = key || viewportKey(map, viewport);
        if (!viewport || !baseUrl || !currentKey || typeof window.fetch !== "function") return;
        if (!initial && instance.lastMapViewportKey === currentKey) return;
        cancelMapRequest(root, instance);
        const controller = makeAbortController();
        instance.mapAbortController = controller;
        const requestId = ++instance.mapRequestId;
        instance.pendingMap = true;
        syncLoading(root, instance);
        const options = controller ? { signal: controller.signal } : undefined;
        window.fetch(requestUrl(baseUrl, map, viewport, initial).toString(), options)
            .then((response) => {
                if (!response.ok) throw new Error("map data failed");
                return response.json();
            })
            .then((payload) => {
                if (instance.mapRequestId !== requestId) return;
                instance.lastMapViewportKey = currentKey;
                renderViewport(root, map, instance, payload);
            })
            .catch((error) => {
                if (instance.mapRequestId === requestId && (!error || error.name !== "AbortError")) {
                    setStatus(root, "지도 매물을 불러오지 못했습니다. 다시 시도해 주세요.");
                }
            })
            .finally(() => {
                if (instance.mapRequestId === requestId) {
                    instance.pendingMap = false;
                    instance.mapAbortController = null;
                    syncLoading(root, instance);
                }
            });
    }

    function replaceListingCollection(html) {
        const template = document.createElement("template");
        template.innerHTML = html;
        const replacements = template.content.querySelectorAll("#listing-collection");
        const target = document.querySelector("#listing-collection");
        if (replacements.length !== 1 || !target) return false;
        const replacement = replacements[0];
        target.replaceWith(replacement);
        processDynamicContent(replacement);
        return true;
    }

    function requestCards(root, map, instance, key) {
        const viewport = viewportFromMap(map);
        const baseUrl = root.dataset && root.dataset.mapCardsUrl;
        if (!canRefreshCards(map, viewport)) {
            setStatus(root, "지도를 조금 더 확대한 뒤 해당 영역의 매물을 확인해 주세요.");
            return;
        }
        if (!baseUrl || !key || instance.lastCardsViewportKey === key || typeof window.fetch !== "function") return;
        cancelCardsRequest(root, instance);
        const controller = makeAbortController();
        instance.cardsAbortController = controller;
        const requestId = ++instance.cardsRequestId;
        instance.pendingCards = true;
        syncLoading(root, instance);
        const options = { headers: { "HX-Request": "true" } };
        if (controller) options.signal = controller.signal;
        window.fetch(requestUrl(baseUrl, map, viewport, false).toString(), options)
            .then((response) => {
                if (!response.ok) throw new Error("map cards failed");
                return response.text();
            })
            .then((html) => {
                if (instance.cardsRequestId !== requestId) return;
                if (!replaceListingCollection(html)) throw new Error("map cards invalid");
                instance.lastCardsViewportKey = key;
            })
            .catch((error) => {
                if (instance.cardsRequestId === requestId && (!error || error.name !== "AbortError")) {
                    setStatus(root, "지도 영역의 매물을 불러오지 못했습니다. 다시 시도해 주세요.");
                }
            })
            .finally(() => {
                if (instance.cardsRequestId === requestId) {
                    instance.pendingCards = false;
                    instance.cardsAbortController = null;
                    syncLoading(root, instance);
                }
            });
    }

    function scheduleViewportRefresh(root, map, instance) {
        const viewport = viewportFromMap(map);
        const key = viewportKey(map, viewport);
        if (!viewport || !key) return;
        if (instance.mapTimer) clearTimeout(instance.mapTimer);
        if (instance.cardsTimer) clearTimeout(instance.cardsTimer);
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
        } else if (!canRefreshCards(map, viewport)) {
            setStatus(root, "지도를 멈추면 현재 범위의 매물 수를 집계합니다.");
        }
    }

    function refreshSearchConfig(root, config) {
        const instance = instances.get(root);
        if (!instance || !config || config.queryKey === instance.mapQueryKey) return;
        root.dataset.mapDataUrl = config.mapDataUrl;
        root.dataset.mapCardsUrl = config.mapCardsUrl;
        root.dataset.mapComplexUrlTemplate = config.mapComplexUrlTemplate;
        root.dataset.mapQueryKey = config.queryKey;
        instance.mapQueryKey = config.queryKey;
        instance.lastMapViewportKey = null;
        instance.lastCardsViewportKey = null;
        if (instance.mapTimer) clearTimeout(instance.mapTimer);
        if (instance.cardsTimer) clearTimeout(instance.cardsTimer);
        cancelMapRequest(root, instance);
        cancelCardsRequest(root, instance);
        const viewport = viewportFromMap(instance.map);
        const key = viewportKey(instance.map, viewport);
        if (!viewport || !key) return;
        requestMapData(root, instance.map, instance, { key });
        requestCards(root, instance.map, instance, key);
    }

    function searchConfig() {
        const config = document.querySelector("#map-search-config");
        if (!config || !config.dataset) return null;
        return {
            queryKey: config.dataset.mapQueryKey,
            mapDataUrl: config.dataset.mapDataUrl,
            mapCardsUrl: config.dataset.mapCardsUrl,
            mapComplexUrlTemplate: config.dataset.mapComplexUrlTemplate,
        };
    }

    function focus(data) {
        const latitude = Number(data && (data.mapFocusLatitude || data.latitude));
        const longitude = Number(data && (data.mapFocusLongitude || data.longitude));
        if (!activeInstance || !Number.isFinite(latitude) || !Number.isFinite(longitude)) return false;
        const { root, map } = activeInstance;
        markViewportDirty(root, activeInstance);
        map.updateBy(new window.naver.maps.LatLng(latitude, longitude), FOCUS_ZOOM);
        setTimeout(() => {
            if (!activeInstance || activeInstance.root !== root || !activeInstance.viewportDirty) return;
            activeInstance.viewportDirty = false;
            scheduleViewportRefresh(root, map, activeInstance);
        }, 0);
        return true;
    }

    function mount(source) {
        const root = findRoot(source);
        if (!root || instances.has(root)) return;
        const container = root.querySelector("[data-listings-map]");
        if (!container) return;
        if (!window.naver || !window.naver.maps) {
            setStatus(root, "네이버 지도 연결에 실패했습니다.");
            return;
        }
        const map = new window.naver.maps.Map(container, {
            center: new window.naver.maps.LatLng(INITIAL_LATITUDE, INITIAL_LONGITUDE),
            zoom: INITIAL_ZOOM,
        });
        const instance = {
            root,
            map,
            listeners: [],
            mapRequestId: 0,
            cardsRequestId: 0,
            complexRequestId: 0,
            overlayListeners: [],
            overlays: [],
            pendingMap: false,
            pendingCards: false,
            viewportDirty: false,
            mapTimer: null,
            cardsTimer: null,
            mapAbortController: null,
            cardsAbortController: null,
            complexAbortController: null,
            lastMapViewportKey: null,
            lastCardsViewportKey: null,
            mapQueryKey: root.dataset && (root.dataset.mapQueryKey || root.dataset.mapDataUrl),
        };
        const closeButton = root.querySelector("[data-map-complex-close]");
        if (closeButton && typeof closeButton.addEventListener === "function") {
            instance.closeModal = () => {
                const modal = root.querySelector("[data-map-complex-modal]");
                if (modal && typeof modal.close === "function") modal.close();
            };
            closeButton.addEventListener("click", instance.closeModal);
        }
        instance.listeners.push(
            window.naver.maps.Event.addListener(map, "dragstart", () => markViewportDirty(root, instance)),
            window.naver.maps.Event.addListener(map, "zoom_changed", () => markViewportDirty(root, instance)),
            window.naver.maps.Event.addListener(map, "idle", () => {
                if (!instance.viewportDirty) return;
                instance.viewportDirty = false;
                scheduleViewportRefresh(root, map, instance);
            }),
        );
        instances.set(root, instance);
        activeInstance = instance;
        setStatus(root, "지도를 확대하거나 이동하면 현재 영역의 매물을 찾습니다.");
    }

    function unmount(source) {
        const root = findRoot(source);
        if (!root) return;
        const instance = instances.get(root);
        if (!instance) return;
        cancelMapRequest(root, instance);
        cancelCardsRequest(root, instance);
        if (instance.complexAbortController) instance.complexAbortController.abort();
        if (instance.mapTimer) clearTimeout(instance.mapTimer);
        if (instance.cardsTimer) clearTimeout(instance.cardsTimer);
        clearOverlays(instance);
        instance.listeners.forEach((listener) => window.naver.maps.Event.removeListener(listener));
        const closeButton = root.querySelector("[data-map-complex-close]");
        if (closeButton && instance.closeModal && typeof closeButton.removeEventListener === "function") {
            closeButton.removeEventListener("click", instance.closeModal);
        }
        if (activeInstance === instance) activeInstance = null;
        instances.delete(root);
    }

    window.RealtyRadarListingMap = { mount, unmount, focus, refreshSearchConfig };

    document.addEventListener("click", (event) => {
        const target = event.target && typeof event.target.closest === "function"
            ? event.target.closest("[data-map-focus]")
            : null;
        if (!target || (event.target.closest && event.target.closest("button, a, dialog"))) return;
        focus(target.dataset);
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        const target = event.target && typeof event.target.closest === "function"
            ? event.target.closest("[data-map-focus]")
            : null;
        if (!target) return;
        event.preventDefault();
        focus(target.dataset);
    });
    document.addEventListener("DOMContentLoaded", () => mount(document));
    document.addEventListener("htmx:beforeSwap", (event) => {
        const target = event.detail && event.detail.target;
        if (findRoot(target)) unmount(target);
    });
    document.addEventListener("htmx:beforeCleanupElement", (event) => {
        const element = event.detail && event.detail.elt;
        if (findRoot(element)) unmount(element);
    });
    document.addEventListener("htmx:afterSwap", (event) => mount(event.detail && event.detail.target));
    document.addEventListener("htmx:afterSettle", () => {
        mount(document);
        const root = findRoot(document);
        if (root) refreshSearchConfig(root, searchConfig());
    });
})(window, document);
