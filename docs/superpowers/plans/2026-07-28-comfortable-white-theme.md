# Comfortable White Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver warm, high-legibility light and dark themes across Realty Radar using shared semantic surfaces.

**Architecture:** Add shared theme tokens and semantic surface helpers in the shared base template. Replace hard-coded light and dark surfaces in page templates, including HTML created by the favorites JavaScript. Preserve the persisted `rr_theme_v1` toggle.

**Tech Stack:** FastAPI, Jinja2 templates, Tailwind CSS CDN, Alpine.js, HTMX, pytest.

## Global Constraints

- Canvas: `#F6F5F2`; raised surface: `#FFFDF9`; secondary surface: `#EEEBE6`; divider: `#DEDAD4`.
- Primary, secondary, and muted light text: `#25262A`, `#51545C`, and `#6B6E76`.
- Preserve `rr_theme_v1` and application behavior; use semantic token surfaces for both themes.
- Add no dependency, new preference, or backend API change.

---

### Task 1: Shared token layer and regression guardrail

**Files:**
- Create: `tests/unit/test_light_theme_templates.py`
- Modify: `src/realty_radar/web/templates/base.html`

**Interfaces:**
- Consumes: the existing `dark` class on the HTML element.
- Produces: `.light-surface`, `.light-subtle-surface`, `.light-divider`, `.light-primary-text`, `.light-secondary-text`, and `.light-muted-text`, scoped under `html:not(.dark)`.

- [ ] **Step 1: Write a failing token test**

```python
from pathlib import Path

TEMPLATE_ROOT = Path("src/realty_radar/web/templates")

def test_base_defines_scoped_comfortable_light_tokens():
    base = (TEMPLATE_ROOT / "base.html").read_text(encoding="utf-8")
    assert "html:not(.dark)" in base
    assert "--rr-canvas: #F6F5F2" in base
    assert "--rr-surface: #FFFDF9" in base
    assert "--rr-text-primary: #25262A" in base
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python -m pytest tests/unit/test_light_theme_templates.py::test_base_defines_scoped_comfortable_light_tokens -v`

Expected: FAIL because the token layer does not exist.

- [ ] **Step 3: Add scoped tokens and shell styling**

Add this token block in `base.html`, then define helper classes under the same `html:not(.dark)` selector. Apply the helpers to the body, header, and footer without removing their `dark:*` classes.

```css
html:not(.dark) {
    --rr-canvas: #F6F5F2;
    --rr-surface: #FFFDF9;
    --rr-surface-subtle: #EEEBE6;
    --rr-border: #DEDAD4;
    --rr-text-primary: #25262A;
    --rr-text-secondary: #51545C;
    --rr-text-muted: #6B6E76;
}
```

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/unit/test_light_theme_templates.py -v; python -m pytest tests/integration/test_web_v2.py::test_home_exposes_hierarchical_auto_search_and_append_pager_contract -v`

Expected: PASS.

- [ ] **Step 5: Commit only task-owned files**

```powershell
git add tests/unit/test_light_theme_templates.py src/realty_radar/web/templates/base.html
git commit -m "feat: add comfortable light theme tokens"
```

### Task 2: Listings, filters, dialogs, and favorites

**Files:**
- Modify: `src/realty_radar/web/templates/listings/index.html`
- Modify: `src/realty_radar/web/templates/listings/_listing_cards.html`
- Modify: `src/realty_radar/web/templates/listings/list_partial.html`
- Modify: `src/realty_radar/web/templates/listings/list_append.html`
- Modify: `src/realty_radar/web/templates/listings/complex_listings_partial.html`
- Modify: `src/realty_radar/web/templates/listings/search_error.html`
- Modify: `tests/unit/test_light_theme_templates.py`

**Interfaces:**
- Consumes: Task 1 helper classes and existing listing/favorites IDs and data attributes.
- Produces: consistent warm surfaces for ordinary and HTMX listing responses plus JavaScript-built favorite entries.

- [ ] **Step 1: Add a failing listing template contract**

```python
def test_listing_templates_use_light_surfaces_and_keep_dark_variants():
    cards = (TEMPLATE_ROOT / "listings" / "_listing_cards.html").read_text(encoding="utf-8")
    index = (TEMPLATE_ROOT / "listings" / "index.html").read_text(encoding="utf-8")
    assert "light-surface" in cards
    assert "dark:bg-slate-800" in cards
    assert "light-surface" in index
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python -m pytest tests/unit/test_light_theme_templates.py::test_listing_templates_use_light_surfaces_and_keep_dark_variants -v`

Expected: FAIL because the helpers have not been added to listing templates.

- [ ] **Step 3: Apply semantic surfaces to every listing state**

Use `light-surface` for cards, dialogs, drawers, pagers, and empty states; use `light-subtle-surface` for grouped fields, table headers, and disabled controls. Update `FavoritesManager` class-name strings so dynamically generated entries select warm light styling when the document is not dark. Preserve every existing `dark:*` style and all IDs, event handlers, and data attributes.

- [ ] **Step 4: Run focused template and HTMX contracts**

Run: `python -m pytest tests/unit/test_light_theme_templates.py -v; python -m pytest tests/integration/test_web_v2.py -k "home_exposes_hierarchical_auto_search or htmx_page_navigation" -v`

Expected: PASS; pager, HTMX, and favorite-button contracts remain unchanged.

- [ ] **Step 5: Commit only task-owned files**

```powershell
git add tests/unit/test_light_theme_templates.py src/realty_radar/web/templates/listings
git commit -m "feat: refine listing light theme surfaces"
```

### Task 3: Account, settings, and job surfaces

**Files:**
- Modify: `src/realty_radar/web/templates/auth/login.html`
- Modify: `src/realty_radar/web/templates/auth/register.html`
- Modify: `src/realty_radar/web/templates/settings/index.html`
- Modify: `src/realty_radar/web/templates/settings/_inline_profile_modal.html`
- Modify: `src/realty_radar/web/templates/jobs/index.html`
- Modify: `src/realty_radar/web/templates/jobs/progress_partial.html`
- Modify: `tests/unit/test_light_theme_templates.py`

**Interfaces:**
- Consumes: Task 1 helpers and all existing form IDs/names, Alpine state, and HTMX targets.
- Produces: warm account, profile, and crawl-job surfaces without changing submission behavior.

- [ ] **Step 1: Add a failing regression check for forced dark surfaces**

```python
def test_non_listing_pages_use_light_surface_helpers():
    for relative_path in (
        "auth/login.html", "auth/register.html", "settings/index.html",
        "settings/_inline_profile_modal.html", "jobs/index.html",
    ):
        template = (TEMPLATE_ROOT / relative_path).read_text(encoding="utf-8")
        assert "light-surface" in template
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python -m pytest tests/unit/test_light_theme_templates.py::test_non_listing_pages_use_light_surface_helpers -v`

Expected: FAIL because these templates lack semantic light surfaces.

- [ ] **Step 3: Replace only light-side forced dark surfaces**

Apply `light-surface` to cards and dialogs and `light-subtle-surface` to settings groups, fields, and secondary panels. Pair replacements with the existing dark variants. Keep all `name`, `id`, Alpine, JavaScript, and `hx-*` attributes verbatim.

- [ ] **Step 4: Run focused behavior tests**

Run: `python -m pytest tests/unit/test_light_theme_templates.py -v; python -m pytest tests/integration/test_web_v2.py -k "home or invalid_search" -v`

Expected: PASS.

- [ ] **Step 5: Commit only task-owned files**

```powershell
git add tests/unit/test_light_theme_templates.py src/realty_radar/web/templates/auth src/realty_radar/web/templates/settings src/realty_radar/web/templates/jobs
git commit -m "feat: improve account and settings light theme"
```

### Task 4: Theme isolation and final verification

**Files:**
- Modify: `tests/unit/test_light_theme_templates.py`

**Interfaces:**
- Consumes: all touched templates and the existing theme switch.
- Produces: test evidence that the theme is scoped out of dark mode.

- [ ] **Step 1: Add a failing dark-isolation check**

```python
def test_comfortable_theme_rules_are_scoped_outside_dark_mode():
    base = (TEMPLATE_ROOT / "base.html").read_text(encoding="utf-8")
    assert "html:not(.dark) .light-surface" in base
    assert "html:not(.dark) .light-subtle-surface" in base
    assert "rr_theme_v1" in base
    assert 'classList.add("dark")' in base
```

- [ ] **Step 2: Run the test and confirm it fails before the selectors exist**

Run: `python -m pytest tests/unit/test_light_theme_templates.py::test_comfortable_theme_rules_are_scoped_outside_dark_mode -v`

Expected: FAIL until the scoped helper selectors are complete.

- [ ] **Step 3: Check both themes in a running browser**

Start the local web app and inspect the home filter, listing card/detail dialog, favorites drawer/compare dialog, login, register, settings modal, and jobs page. Toggle to dark mode before and after navigation; confirm the light helper styles never apply while the root has `dark`.

- [ ] **Step 4: Run the complete regression suite**

Run: `python -m pytest; git diff --check`

Expected: all tests pass and no whitespace errors are reported.

- [ ] **Step 5: Commit final regression coverage**

```powershell
git add tests/unit/test_light_theme_templates.py
git commit -m "test: cover comfortable light theme isolation"
```
