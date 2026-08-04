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

    function readMarkers(root) {
        const payload = root.querySelector("[data-listing-map-payload]");
        if (!payload) return [];
        try {
            const parsed = JSON.parse(payload.textContent);
            return Array.isArray(parsed)
                ? parsed.filter((marker) => (
                    marker.latitude !== null
                    && marker.latitude !== ""
                    && marker.longitude !== null
                    && marker.longitude !== ""
                    && Number.isFinite(Number(marker.latitude))
                    && Number.isFinite(Number(marker.longitude))
                ))
                : [];
        } catch (_) {
            return [];
        }
    }

    function setStatus(root, message) {
        const status = root.querySelector("[data-listing-map-status]");
        if (status) status.textContent = message;
    }

    function setLoading(root, isLoading) {
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

    function requestViewport(root, map, instance) {
        const viewport = viewportFromMap(map);
        const zoom = typeof map.getZoom === "function" ? Number(map.getZoom()) : null;
        if (!viewport || !Number.isFinite(zoom)) {
            setStatus(root, "현재 지도 범위를 읽을 수 없습니다.");
            return;
        }
        if (
            zoom < MIN_SEARCH_ZOOM
            || viewport.north - viewport.south > MAX_LATITUDE_SPAN
            || viewport.east - viewport.west > MAX_LONGITUDE_SPAN
        ) {
            setStatus(root, "지도를 조금 더 확대한 뒤 이 영역의 매물을 확인해 주세요.");
            return;
        }
        const baseUrl = root.dataset && root.dataset.mapSearchUrl;
        if (!baseUrl || typeof window.fetch !== "function") return;

        const url = new URL(baseUrl, (window.location && window.location.origin) || "http://localhost");
        url.searchParams.delete("cursor");
        url.searchParams.set("map_west", String(viewport.west));
        url.searchParams.set("map_south", String(viewport.south));
        url.searchParams.set("map_east", String(viewport.east));
        url.searchParams.set("map_north", String(viewport.north));

        const requestId = ++instance.requestId;
        setLoading(root, true);
        window.fetch(url.toString(), { headers: { "HX-Request": "true" } })
            .then((response) => {
                if (!response.ok) throw new Error("map search failed");
                return response.text();
            })
            .then((html) => {
                if (instance.requestId !== requestId) return;
                const target = document.querySelector("#search-results");
                if (!target || !window.htmx || typeof window.htmx.swap !== "function") return;
                window.htmx.swap(target, html, { swapStyle: "outerHTML" });
            })
            .catch(() => {
                if (instance.requestId === requestId) {
                    setStatus(root, "지도 범위의 매물을 불러오지 못했습니다. 다시 시도해 주세요.");
                }
            })
            .finally(() => {
                if (instance.requestId === requestId) setLoading(root, false);
            });
    }

    function scheduleViewportSearch(root, map, instance) {
        if (instance.viewportTimer) clearTimeout(instance.viewportTimer);
        instance.viewportTimer = setTimeout(
            () => requestViewport(root, map, instance),
            VIEWPORT_DEBOUNCE_MS,
        );
    }

    function mount(source) {
        const root = findRoot(source);
        if (!root || instances.has(root)) return;
        const container = root.querySelector("[data-listings-map]");
        const markers = readMarkers(root);
        if (!container || markers.length === 0) {
            if (container) setStatus(root, "위치 확인 중");
            return;
        }
        if (!window.naver || !window.naver.maps) {
            setStatus(root, "네이버 지도 연결에 실패했습니다.");
            return;
        }

        const firstPosition = new window.naver.maps.LatLng(markers[0].latitude, markers[0].longitude);
        const map = new window.naver.maps.Map(container, {
            center: firstPosition,
            zoom: 14,
        });
        const bounds = new window.naver.maps.LatLngBounds();
        const infoWindow = new window.naver.maps.InfoWindow();
        const mapMarkers = [];
        const listeners = [];
        for (const item of markers) {
            const position = new window.naver.maps.LatLng(item.latitude, item.longitude);
            const marker = new window.naver.maps.Marker({
                map,
                position,
                title: item.complex_name,
            });
            bounds.extend(position);
            listeners.push(
                window.naver.maps.Event.addListener(marker, "click", () => {
                    infoWindow.setContent(
                        `<div style="padding:10px;min-width:180px"><strong>${escapeHtml(item.complex_name)}</strong><br>` +
                        `<span>${escapeHtml(item.address)}</span><br>` +
                        `<span>매물 ${item.listing_count}개 · ${formatPrice(item.min_price)}~${formatPrice(item.max_price)}</span></div>`,
                    );
                    infoWindow.open(map, marker);
                }),
            );
            mapMarkers.push(marker);
        }
        map.fitBounds(bounds, { top: 24, right: 24, bottom: 24, left: 24 });
        const instance = {
            infoWindow,
            listeners,
            markers: mapMarkers,
            requestId: 0,
            viewportDirty: false,
            viewportTimer: null,
        };
        listeners.push(
            window.naver.maps.Event.addListener(map, "dragstart", () => {
                instance.viewportDirty = true;
            }),
            window.naver.maps.Event.addListener(map, "zoom_changed", () => {
                instance.viewportDirty = true;
            }),
            window.naver.maps.Event.addListener(map, "idle", () => {
                if (!instance.viewportDirty) return;
                instance.viewportDirty = false;
                scheduleViewportSearch(root, map, instance);
            }),
        );
        instances.set(root, instance);
    }

    function unmount(source) {
        const root = findRoot(source);
        if (!root) return;
        const instance = instances.get(root);
        if (!instance) return;
        instance.requestId += 1;
        if (instance.viewportTimer) clearTimeout(instance.viewportTimer);
        instance.infoWindow.close();
        instance.listeners.forEach((listener) => window.naver.maps.Event.removeListener(listener));
        instance.markers.forEach((marker) => marker.setMap(null));
        instances.delete(root);
    }

    window.RealtyRadarListingMap = { mount, unmount };

    document.addEventListener("DOMContentLoaded", () => mount(document));
    document.addEventListener("htmx:beforeSwap", (event) => unmount(event.detail && event.detail.target));
    document.addEventListener("htmx:beforeCleanupElement", (event) => unmount(event.detail && event.detail.elt));
    document.addEventListener("htmx:afterSwap", (event) => mount(event.detail && event.detail.target));
})(window, document);
