(function (window, document) {
    "use strict";

    const instances = new WeakMap();
    const VIEWPORT_SEARCH_DEBOUNCE_MS = 400;
    const INITIAL_LATITUDE = 37.55;
    const INITIAL_LONGITUDE = 126.9;
    const INITIAL_ZOOM = 11;
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
        
        const multiValueKeys = new Set(["trade_types", "direction_codes", "mortgage_codes", "sido_codes", "sigungu_codes", "floor_bands"]);
        const addParam = (key, value) => {
            if (!key || value === "" || value === null || value === undefined) return;
            if (multiValueKeys.has(key)) {
                const existing = url.searchParams.getAll(key);
                if (!existing.includes(value)) {
                    url.searchParams.append(key, value);
                }
            } else {
                url.searchParams.set(key, value);
            }
        };

        // 1. 메인 검색 폼 수집
        const form = document.querySelector("#listing-search-form");
        if (form) {
            const formData = new FormData(form);
            for (const [key, value] of formData.entries()) {
                addParam(key, value);
            }
        }

        // 2. 통합 필터 모달 내부의 모든 슬라이더 및 인풋 통합 수집
        const modal = document.querySelector("#detailed-filter-modal");
        if (modal) {
            modal.querySelectorAll("input, select").forEach((el) => {
                if (!el.name || el.disabled) return;
                if ((el.type === "checkbox" || el.type === "radio") && !el.checked) return;
                addParam(el.name, el.value);
            });
        }

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
        if (instance) instance.isManualClick = true;
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
        if (typeof modal.showModal === "function" && !modal.open) {
            modal.showModal();
            document.body.classList.add("overflow-hidden");
        }

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

                // 단지 매물 모달 정렬 이벤트 연동
                const sortSelect = modal.querySelector("[data-complex-modal-sort]");
                if (sortSelect) {
                    const sortListings = () => {
                        const cards = Array.from(listings.querySelectorAll("[data-listing-card]"));
                        if (!cards.length) return;
                        const mode = sortSelect.value;
                        cards.sort((a, b) => {
                            const pA = parseFloat(a.dataset.priceText?.replace(/[^0-9.]/g, "") || "0");
                            const pB = parseFloat(b.dataset.priceText?.replace(/[^0-9.]/g, "") || "0");
                            if (mode === "price_asc") return pA - pB;
                            if (mode === "price_desc") return pB - pA;
                            return 0;
                        });
                        cards.forEach((card) => listings.appendChild(card));
                    };
                    sortSelect.onchange = sortListings;
                    sortListings();
                }
            })
            .catch((error) => {
                if (instance.complexRequestId !== requestId || (error && error.name === "AbortError")) return;
                if (listings) listings.innerHTML = '<p class="text-sm font-semibold text-rose-600">단지 매물을 불러오지 못했습니다. 다시 시도해 주세요.</p>';
            });
    }

    function getDensityStyle(listingCount, maxCount) {
        const count = Number(listingCount) || 0;
        const max = Math.max(Number(maxCount) || 1, 1);
        const ratio = count / max;

        if (count >= 50 || ratio >= 0.40) {
            return {
                fillColor: "rgba(79, 70, 229, 0.48)",
                strokeColor: "#3730a3",
                strokeWeight: 2.5,
                badgeBgClass: "bg-indigo-700 dark:bg-indigo-600 border-indigo-300",
                pulseColor: "bg-amber-400",
            };
        }
        if (count >= 20 || ratio >= 0.20) {
            return {
                fillColor: "rgba(99, 102, 241, 0.32)",
                strokeColor: "#4f46e5",
                strokeWeight: 2,
                badgeBgClass: "bg-indigo-600 dark:bg-indigo-500 border-indigo-200",
                pulseColor: "bg-emerald-400",
            };
        }
        if (count >= 5 || ratio >= 0.08) {
            return {
                fillColor: "rgba(129, 140, 248, 0.20)",
                strokeColor: "#6366f1",
                strokeWeight: 1.5,
                badgeBgClass: "bg-indigo-500/90 dark:bg-indigo-600/90 border-indigo-200/80",
                pulseColor: "bg-cyan-300",
            };
        }
        return {
            fillColor: "rgba(197, 204, 253, 0.09)",
            strokeColor: "#a5b4fc",
            strokeWeight: 1,
            badgeBgClass: "bg-slate-700/85 dark:bg-slate-800/85 border-slate-400/60",
            pulseColor: "bg-slate-300",
        };
    }

    function makeClusterOverlay(map, instance, cluster, maxListingCount = 1) {
        const style = getDensityStyle(cluster.listing_count, maxListingCount);

        // 시/군/구 행정구역 영역 매물 밀도(개수)에 따른 동적 색상 진하기 셰이딩 오버레이
        if (cluster.west && cluster.south && cluster.east && cluster.north && window.naver && window.naver.maps) {
            const rect = new window.naver.maps.Rectangle({
                map: map,
                bounds: boundsFromValues(cluster.west, cluster.south, cluster.east, cluster.north),
                fillColor: style.fillColor,
                fillOpacity: 1.0,
                strokeColor: style.strokeColor,
                strokeWeight: style.strokeWeight,
                strokeOpacity: 0.85,
                strokeStyle: "solid",
                clickable: false,
            });
            instance.overlays.push(rect);
        }

        // 지명 글자를 배제하고 오직 건수 숫자 중심으로 콤팩트하게 표기
        const countText = `${escapeHtml(formatListingCount(cluster.listing_count))}`;
        const marker = new window.naver.maps.Marker({
            map,
            position: new window.naver.maps.LatLng(cluster.latitude, cluster.longitude),
            title: cluster.label ? `${cluster.label}: ${cluster.listing_count}건` : `${cluster.listing_count}건`,
            icon: {
                content: `<div class="rounded-full border-2 ${style.badgeBgClass} px-3 py-1 text-xs font-black text-white shadow-2xl hover:scale-110 transition-all cursor-pointer whitespace-nowrap pointer-events-auto shrink-0 select-none flex items-center justify-center gap-1" style="writing-mode: horizontal-tb !important; white-space: nowrap !important;">
                    <span class="inline-block w-1.5 h-1.5 rounded-full ${style.pulseColor} animate-pulse"></span>
                    <span>${countText}</span>
                </div>`,
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
        const priceLabel = item.min_price && item.max_price && item.min_price !== item.max_price
            ? `${formatPrice(item.min_price)} ~ ${formatPrice(item.max_price)}`
            : formatPrice(item.min_price);
        const marker = new window.naver.maps.Marker({
            map,
            position: new window.naver.maps.LatLng(item.latitude, item.longitude),
            title: item.complex_name,
            icon: {
                content: `<div class="rounded-xl border border-indigo-300 dark:border-indigo-700 bg-white/95 dark:bg-slate-900/95 px-2.5 py-1.5 shadow-xl text-center pointer-events-auto shrink-0 select-none backdrop-blur leading-tight" style="writing-mode: horizontal-tb !important; white-space: nowrap !important;">
                    <div class="text-[11px] font-extrabold text-slate-900 dark:text-white truncate max-w-[180px]">${escapeHtml(item.complex_name)}</div>
                    <div class="text-[11px] font-black text-indigo-600 dark:text-indigo-400 flex items-center justify-center gap-1 mt-0.5">
                        <span>${escapeHtml(priceLabel)}</span>
                        <span class="text-[10px] font-bold text-slate-500 dark:text-slate-400">(${escapeHtml(item.listing_count)}건)</span>
                    </div>
                </div>`,
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
        const clusters = payload.clusters || [];
        const maxListingCount = Math.max(...clusters.map((c) => Number(c.listing_count) || 0), 1);
        clusters.forEach((cluster) => instance.overlays.push(makeClusterOverlay(map, instance, cluster, maxListingCount)));
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
        // 단지/매물 클릭 수동 포커스 상태가 아닐 때만 경계 기반 리스트 갱신 (리스트 증발 방지)
        if (!instance.isManualClick && canRefreshCards(map, viewport) && instance.lastCardsViewportKey !== key) {
            instance.cardsTimer = setTimeout(
                () => requestCards(root, map, instance, key),
                VIEWPORT_SEARCH_DEBOUNCE_MS,
            );
        } else if (!canRefreshCards(map, viewport)) {
            setStatus(root, "지도를 멈추면 현재 범위의 매물 수를 집계합니다.");
        }
    }

    const REGION_CENTERS = {
        11: { lat: 37.5665, lng: 126.9780, zoom: 11 },
        28: { lat: 37.4563, lng: 126.7052, zoom: 10 },
        41: { lat: 37.4138, lng: 127.5183, zoom: 9 },
        11305: { lat: 37.6396, lng: 127.0257, zoom: 13 },
        11620: { lat: 37.4784, lng: 126.9516, zoom: 13 },
        11320: { lat: 37.6688, lng: 127.0471, zoom: 13 },
        11680: { lat: 37.5172, lng: 127.0473, zoom: 13 },
        11650: { lat: 37.4837, lng: 127.0324, zoom: 13 },
        11710: { lat: 37.5145, lng: 127.1061, zoom: 13 },
        11440: { lat: 37.5663, lng: 126.9016, zoom: 13 },
        11200: { lat: 37.5635, lng: 127.0365, zoom: 13 },
        11215: { lat: 37.5385, lng: 127.0823, zoom: 13 },
        11350: { lat: 37.6542, lng: 127.0568, zoom: 13 },
        11500: { lat: 37.5509, lng: 126.8495, zoom: 13 },
        11470: { lat: 37.5170, lng: 126.8665, zoom: 13 },
        11560: { lat: 37.5264, lng: 126.8963, zoom: 13 },
        11590: { lat: 37.5124, lng: 126.9398, zoom: 13 },
        11170: { lat: 37.5326, lng: 126.9900, zoom: 13 },
        11110: { lat: 37.5730, lng: 126.9794, zoom: 13 },
        11140: { lat: 37.5641, lng: 126.9979, zoom: 13 },
        11230: { lat: 37.5744, lng: 127.0400, zoom: 13 },
        11260: { lat: 37.6065, lng: 127.0927, zoom: 13 },
        11290: { lat: 37.5894, lng: 127.0167, zoom: 13 },
        11380: { lat: 37.6027, lng: 126.9291, zoom: 13 },
        11410: { lat: 37.5791, lng: 126.9368, zoom: 13 },
        11530: { lat: 37.4954, lng: 126.8874, zoom: 13 },
        11545: { lat: 37.4568, lng: 126.8955, zoom: 13 },
        11740: { lat: 37.5301, lng: 127.1238, zoom: 13 },
        41281: { lat: 37.6584, lng: 126.8320, zoom: 12 },
        41135: { lat: 37.3827, lng: 127.1189, zoom: 12 },
    };

    function autoCenterMapOnRegion(map, url) {
        if (!map || !url) return;
        try {
            const parsed = new URL(url, window.location.origin);
            const sigunguCodes = parsed.searchParams.getAll("sigungu_codes").concat(parsed.searchParams.get("sigungu_code") || []);
            const sidoCode = parsed.searchParams.get("sido_code");
            let target = null;
            for (const code of sigunguCodes) {
                const num = parseInt(code, 10);
                if (REGION_CENTERS[num]) { target = REGION_CENTERS[num]; break; }
            }
            if (!target && sidoCode) {
                const num = parseInt(sidoCode, 10);
                if (REGION_CENTERS[num]) target = REGION_CENTERS[num];
            }
            if (target && window.naver && window.naver.maps) {
                map.setCenter(new window.naver.maps.LatLng(target.lat, target.lng));
                if (target.zoom) map.setZoom(target.zoom);
            }
        } catch (e) {
            console.warn("[Realty Radar] autoCenterMapOnRegion error:", e);
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
        instance.isManualClick = false;
        if (instance.mapTimer) clearTimeout(instance.mapTimer);
        if (instance.cardsTimer) clearTimeout(instance.cardsTimer);
        cancelMapRequest(root, instance);
        cancelCardsRequest(root, instance);
        autoCenterMapOnRegion(instance.map, config.mapCardsUrl);
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
        activeInstance.isManualClick = true;
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
            viewportDirty: true,
            isManualClick: false,
            mapTimer: null,
            cardsTimer: null,
            mapAbortController: null,
            cardsAbortController: null,
            complexAbortController: null,
            lastMapViewportKey: null,
            lastCardsViewportKey: null,
            mapQueryKey: root.dataset && (root.dataset.mapQueryKey || root.dataset.mapDataUrl),
        };
        const modalElement = root.querySelector("[data-map-complex-modal]");
        if (modalElement && typeof modalElement.addEventListener === "function") {
            modalElement.addEventListener("close", () => document.body.classList.remove("overflow-hidden"));
        }
        const closeButton = root.querySelector("[data-map-complex-close]");
        if (closeButton && typeof closeButton.addEventListener === "function") {
            instance.closeModal = () => {
                const modal = root.querySelector("[data-map-complex-modal]");
                if (modal && typeof modal.close === "function") {
                    modal.close();
                    document.body.classList.remove("overflow-hidden");
                }
            };
            closeButton.addEventListener("click", instance.closeModal);
        }
        instance.listeners.push(
            window.naver.maps.Event.addListener(map, "dragstart", () => {
                instance.isManualClick = false;
                markViewportDirty(root, instance);
            }),
            window.naver.maps.Event.addListener(map, "zoom_changed", () => markViewportDirty(root, instance)),
            window.naver.maps.Event.addListener(map, "idle", () => {
                if (!instance.viewportDirty) return;
                instance.viewportDirty = false;
                scheduleViewportRefresh(root, map, instance);
            }),
        );
        instances.set(root, instance);
        activeInstance = instance;
        // 마운트 직후 최초 1회 뷰포트 데이터 즉시 로드 트리거
        scheduleViewportRefresh(root, map, instance);
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
    document.addEventListener("submit", (event) => {
        if (event.target && event.target.id === "listing-search-form") {
            instances.forEach((instance, root) => {
                instance.lastMapViewportKey = null;
                instance.lastCardsViewportKey = null;
                if (instance.map) {
                    const viewport = viewportFromMap(instance.map);
                    const key = viewportKey(instance.map, viewport);
                    if (viewport && key) {
                        requestMapData(root, instance.map, instance, { key });
                        requestCards(root, instance.map, instance, key);
                    }
                }
            });
        }
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
