(function (window, document) {
    "use strict";

    const triggerSelector = "[data-map-filter-trigger], [data-filter-panel-open]";

    function escapeName(name) {
        const value = String(name || "");
        if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(value);
        return value.replace(/["\\]/g, "\\$&");
    }

    function namedControls(form, names) {
        return names.flatMap((name) => Array.from(form.querySelectorAll('[name="' + escapeName(name) + '"]')));
    }

    function resetControl(control) {
        if (control.type === "checkbox" || control.type === "radio") {
            control.checked = false;
            return;
        }
        control.value = "";
    }

    function setTriggersExpanded(source, expanded) {
        source.querySelectorAll(triggerSelector).forEach((button) => {
            button.setAttribute("aria-expanded", String(expanded));
        });
    }

    function mount(source = document) {
        const form = source.querySelector("#listing-search-form");
        const panel = source.querySelector("#detailed-filter-modal");
        if (!form || !panel || panel.dataset.filterPanelMounted === "true") return;
        panel.dataset.filterPanelMounted = "true";

        source.addEventListener("click", (event) => {
            const opener = event.target.closest && event.target.closest(triggerSelector);
            if (opener) {
                if (typeof panel.showModal === "function" && !panel.open) {
                    panel.showModal();
                    document.body.classList.add("overflow-hidden");
                }
                opener.setAttribute("aria-expanded", "true");
                return;
            }

            if (event.target.closest && event.target.closest("[data-filter-panel-apply]")) {
                form.requestSubmit();
                if (typeof panel.close === "function" && panel.open) {
                    panel.close();
                    document.body.classList.remove("overflow-hidden");
                }
                return;
            }

            const clearTabBtn = event.target.closest && event.target.closest("[data-clear-filter-tab]");
            if (clearTabBtn) {
                const activeTabPanel = panel.querySelector(".filter-tab-content:not([hidden])");
                if (activeTabPanel) {
                    activeTabPanel.querySelectorAll("input, select").forEach(resetControl);
                }
                form.requestSubmit();
                return;
            }

            const chip = event.target.closest && event.target.closest("[data-applied-filter-clear]");
            if (!chip) return;
            const names = String(chip.dataset.filterClearNames || "").split(",").filter(Boolean);
            if (!names.length) return;
            namedControls(form, names).forEach(resetControl);
            form.requestSubmit();
        });

        panel.addEventListener("close", () => {
            setTriggersExpanded(source, false);
            document.body.classList.remove("overflow-hidden");
        });
    }

    window.RealtyRadarListingFilterPanel = { mount };
    document.addEventListener("DOMContentLoaded", () => mount(document));
})(window, document);
