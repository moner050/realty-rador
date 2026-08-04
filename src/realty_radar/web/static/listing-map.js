(function (window, document) {
    "use strict";

    const instances = new WeakMap();
    const VIEWPORT_DEBOUNCE_MS = 300;
    const MIN_SEARCH_ZOOM = 11;
    const MAX_LATITUDE_SPAN = 1.5;
    const MAX_LONGITUDE_SPAN = 1.5;

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

    function setLoading(root, instance) {
        const isLoading = instance.pendingMap || instance.pendingCards;
        const loading = root.querySelector("[data-map-loading]");
        if (loading) {
            loading.hidden = !isLoading;
            if (loading.classList) loading.classList.toggle("hidden", !isLoading);
            if (typeof loading.setAttribute === "function") loading.setAttribute("aria-hidden", String(!isLoading));
        }
        if (typeof root.setAttribute === "function") root.setAttribute("aria-busy", String(isLoading));
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

    function markViewportDirty(instance) {
        instance.mapRequestId += 1;
        instance.cardsRequestId += 1;
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
        instance.infoWindow.close();
    }

    function boundsFromValues(west, south, east, north) {
        return new window.naver.maps.LatLngBounds(
            new window.naver.maps.LatLng(south, west),
            new window.naver.maps.LatLng(north, east),
        );
    }

    function makeClusterOverlay(map, instance, cluster) {
        const marker = new window.naver.maps.Marker({
            map,
            position: new window.naver.maps.LatLng(cluster.latitude, cluster.longitude),
            title: `${cluster.complex_count}개 단지`,
            icon: {
                content: `<div class="rounded-full bg-indigo-600 px-3 py-1.5 text-xs font-extrabold text-white shadow-lg">${escapeHtml(cluster.complex_count)}개 단지</div>`,
                anchor: new window.naver.maps.Point(0, 0),
            },
        });
        const listener = window.naver.maps.Event.addListener(marker, "click", () => {
            markViewportDirty(instance);
            map.fitBounds(boundsFromValues(cluster.west, cluster.south, cluster.east, cluster.north));
        });
        instance.listeners.push(listener);
        instance.overlayListeners.push(listener);
        return marker;
    }

    function makeMarkerOverlay(map, instance, item) {
        const marker = new window.naver.maps.Marker({
            map,
            position: new window.naver.maps.LatLng(item.latitude, item.longitude),
            title: item.complex_name,
            icon: {
                content: `<div class="rounded-lg bg-white px-2 py-1 text-xs font-extrabold text-slate-900 shadow-lg ring-1 ring-indigo-200">${escapeHtml(formatPrice(item.min_price))} <span class="text-slate-500">${escapeHtml(item.listing_count)}건</span></div>`,
                anchor: new window.naver.maps.Point(0, 0),
            },
        });
        const listener = window.naver.maps.Event.addListener(marker, "click", () => {
            instance.infoWindow.setContent(
                `<div style="padding:10px;min-width:180px"><strong>${escapeHtml(item.complex_name)}</strong><br>` +
                `<span>${escapeHtml(item.address)}</span><br>` +
                `<span>매물 ${escapeHtml(item.listing_count)}건 · ${escapeHtml(formatPrice(item.min_price))}~${escapeHtml(formatPrice(item.max_price))}</span></div>`,
            );
            instance.infoWindow.open(map, marker);
        });
        instance.listeners.push(listener);
        instance.overlayListeners.push(listener);
        return marker;
    }

    function renderViewport(root, map, instance, payload) {
        clearOverlays(instance);
        (payload.clusters || []).forEach((cluster) => instance.overlays.push(makeClusterOverlay(map, instance, cluster)));
        (payload.markers || []).forEach((marker) => instance.overlays.push(makeMarkerOverlay(map, instance, marker)));
        const counts = [
            ["[data-map-matching-count]", payload.matching_complex_count],
            ["[data-map-mapped-count]", payload.mapped_complex_count],
            ["[data-map-unmapped-count]", payload.unmapped_complex_count],
        ];
        counts.forEach(([selector, count]) => {
            const target = root.querySelector(selector);
            if (target) target.textContent = String(count || 0);
        });
    }

    function requestMapData(root, map, instance, { initial = false } = {}) {
        const viewport = viewportFromMap(map);
        const baseUrl = root.dataset && root.dataset.mapDataUrl;
        if (!viewport || !baseUrl || typeof window.fetch !== "function") return;
        const requestId = ++instance.mapRequestId;
        instance.pendingMap = true;
        setLoading(root, instance);
        window.fetch(requestUrl(baseUrl, map, viewport, initial).toString())
            .then((response) => {
                if (!response.ok) throw new Error("map data failed");
                return response.json();
            })
            .then((payload) => {
                if (instance.mapRequestId !== requestId) return;
                renderViewport(root, map, instance, payload);
            })
            .catch(() => {
                if (instance.mapRequestId === requestId) setStatus(root, "지도 매물을 불러오지 못했습니다. 다시 시도해 주세요.");
            })
            .finally(() => {
                if (instance.mapRequestId === requestId) {
                    instance.pendingMap = false;
                    setLoading(root, instance);
                }
            });
    }

    function requestCards(root, map, instance) {
        const viewport = viewportFromMap(map);
        const baseUrl = root.dataset && root.dataset.mapCardsUrl;
        if (!canRefreshCards(map, viewport)) {
            setStatus(root, "지도를 조금 더 확대한 뒤 해당 영역의 매물을 확인해 주세요.");
            return;
        }
        if (!baseUrl || typeof window.fetch !== "function") return;
        const requestId = ++instance.cardsRequestId;
        instance.pendingCards = true;
        setLoading(root, instance);
        window.fetch(requestUrl(baseUrl, map, viewport, false).toString(), { headers: { "HX-Request": "true" } })
            .then((response) => {
                if (!response.ok) throw new Error("map cards failed");
                return response.text();
            })
            .then((html) => {
                if (instance.cardsRequestId !== requestId) return;
                const target = document.querySelector("#listing-collection");
                if (target && window.htmx && typeof window.htmx.swap === "function") {
                    window.htmx.swap(target, html, { swapStyle: "outerHTML" });
                }
            })
            .catch(() => {
                if (instance.cardsRequestId === requestId) setStatus(root, "지도 영역의 매물을 불러오지 못했습니다. 다시 시도해 주세요.");
            })
            .finally(() => {
                if (instance.cardsRequestId === requestId) {
                    instance.pendingCards = false;
                    setLoading(root, instance);
                }
            });
    }

    function scheduleViewportRefresh(root, map, instance) {
        if (instance.viewportTimer) clearTimeout(instance.viewportTimer);
        instance.viewportTimer = setTimeout(() => {
            requestMapData(root, map, instance);
            requestCards(root, map, instance);
        }, VIEWPORT_DEBOUNCE_MS);
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
            center: new window.naver.maps.LatLng(36.5, 127.8),
            zoom: 7,
        });
        const instance = {
            infoWindow: new window.naver.maps.InfoWindow(),
            listeners: [],
            mapRequestId: 0,
            cardsRequestId: 0,
            overlayListeners: [],
            overlays: [],
            pendingMap: false,
            pendingCards: false,
            viewportDirty: false,
            viewportTimer: null,
        };
        instance.listeners.push(
            window.naver.maps.Event.addListener(map, "dragstart", () => { markViewportDirty(instance); }),
            window.naver.maps.Event.addListener(map, "zoom_changed", () => { markViewportDirty(instance); }),
            window.naver.maps.Event.addListener(map, "idle", () => {
                if (!instance.viewportDirty) return;
                instance.viewportDirty = false;
                scheduleViewportRefresh(root, map, instance);
            }),
        );
        instances.set(root, instance);
        requestMapData(root, map, instance, { initial: true });
    }

    function unmount(source) {
        const root = findRoot(source);
        if (!root) return;
        const instance = instances.get(root);
        if (!instance) return;
        instance.mapRequestId += 1;
        instance.cardsRequestId += 1;
        if (instance.viewportTimer) clearTimeout(instance.viewportTimer);
        clearOverlays(instance);
        instance.listeners.forEach((listener) => window.naver.maps.Event.removeListener(listener));
        instance.infoWindow.close();
        instances.delete(root);
    }

    window.RealtyRadarListingMap = { mount, unmount };

    document.addEventListener("DOMContentLoaded", () => mount(document));
    document.addEventListener("htmx:beforeSwap", (event) => unmount(event.detail && event.detail.target));
    document.addEventListener("htmx:beforeCleanupElement", (event) => unmount(event.detail && event.detail.elt));
    document.addEventListener("htmx:afterSwap", (event) => mount(event.detail && event.detail.target));
})(window, document);
