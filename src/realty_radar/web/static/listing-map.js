(function (window, document) {
    "use strict";

    const instances = new WeakMap();

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
        instances.set(root, { infoWindow, listeners, markers: mapMarkers });
    }

    function unmount(source) {
        const root = findRoot(source);
        if (!root) return;
        const instance = instances.get(root);
        if (!instance) return;
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
