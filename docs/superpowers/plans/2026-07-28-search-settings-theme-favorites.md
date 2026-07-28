# Search Settings, Theme, and Favorites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Keep policy-loan settings only in search, make the specified search UI readable in light mode, and preserve guest and signed-in favorites across account transitions.

**Architecture:** The settings route retains only the inline profile update endpoint while direct visits to \`/settings\` redirect to search. Search rendering receives explicit favorite DTOs instead of serializing SQLAlchemy entities in Jinja. The existing browser \`FavoritesManager\` remains the guest localStorage owner; the preference API persists signed-in state and merges it after sign-in.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, Tailwind CSS CDN, Alpine.js, HTMX, localStorage, pytest, Playwright.

## Global Constraints

- Preserve search SQL, loan eligibility calculation, filter persistence, and the \`/settings/inline\` contract.
- Do not change the \`user_preference\` schema or \`/api/user/preference\` URL.
- Use \`article_id\` and \`complex_id\` for deduplication.
- Keep the three guest localStorage keys until a successful signed-in preference sync.
- Never clear guest localStorage after an API failure.

---

### Task 1: Remove the standalone settings surface

**Files:**
- Modify: \`src/realty_radar/web/templates/base.html:226-246\`
- Modify: \`src/realty_radar/web/routes/settings.py:111-190\`
- Delete: \`src/realty_radar/web/templates/settings/index.html\`
- Modify: \`tests/unit/test_light_theme_templates.py\`
- Modify: \`tests/integration/test_web_v2.py\`

**Interfaces:**
- Consumes: \`get_request_user_profile()\` and \`update_inline_settings()\`.
- Produces: \`GET /settings -> 303 /\`, no header settings link, and the unchanged \`POST /settings/inline -> 204\` endpoint.

- [ ] **Step 1: Write the failing route and header contract**

\`\`\`python
def test_settings_url_redirects_to_search_and_header_has_no_settings_link():
    response = TestClient(app).get("/settings", follow_redirects=False)
    base = (TEMPLATE_ROOT / "base.html").read_text(encoding="utf-8")

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert 'href="/settings"' not in base
\`\`\`

- [ ] **Step 2: Run the test to verify it fails**

Run: \`python -m pytest tests/integration/test_web_v2.py -k settings_url_redirects -v\`

Expected: FAIL because the current route renders the standalone page.

- [ ] **Step 3: Write the minimal implementation**

\`\`\`python
@router.get("", name="settings_index")
def get_settings() -> RedirectResponse:
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
\`\`\`

Delete the header link, standalone template, and its screen-only POST handler. Keep helper functions and inline save handler.

- [ ] **Step 4: Run focused tests**

Run: \`python -m pytest tests/integration/test_web_v2.py -k settings_url_redirects -v; python -m pytest tests/unit/test_light_theme_templates.py -v\`

Expected: PASS.

- [ ] **Step 5: Commit**

\`\`\`bash
git add src/realty_radar/web/templates/base.html src/realty_radar/web/routes/settings.py src/realty_radar/web/templates/settings/index.html tests/unit/test_light_theme_templates.py tests/integration/test_web_v2.py
git commit -m "feat: remove standalone settings page"
\`\`\`

### Task 2: Make search details and the profile modal theme-safe

**Files:**
- Modify: \`src/realty_radar/web/templates/listings/index.html:130-420\`
- Modify: \`src/realty_radar/web/templates/settings/_inline_profile_modal.html:1-205\`
- Modify: \`tests/unit/test_light_theme_templates.py\`

**Interfaces:**
- Consumes: the shared \`theme-surface\`, \`theme-form-grid\`, \`theme-primary-text\`, \`theme-secondary-text\`, \`theme-control\`, and \`theme-divider\` styles.
- Produces: readable labels, helper text, inputs, cards, and dividers in both themes without changing filter/form names.

- [ ] **Step 1: Write the failing template contract**

\`\`\`python
def test_search_detail_controls_and_profile_modal_use_theme_safe_text():
    listings = (TEMPLATE_ROOT / "listings" / "index.html").read_text(encoding="utf-8")
    modal = (TEMPLATE_ROOT / "settings" / "_inline_profile_modal.html").read_text(encoding="utf-8")

    assert "theme-form-grid" in listings
    assert 'text-slate-300"><span>동 코드 직접 입력</span>' not in listings
    assert "theme-surface max-h-[90vh]" in modal
    assert 'text-white">{{ label }}</span>' not in modal
\`\`\`

- [ ] **Step 2: Run the test to verify it fails**

Run: \`python -m pytest tests/unit/test_light_theme_templates.py -k theme_safe_text -v\`

Expected: FAIL on unconditional dark surface/text classes.

- [ ] **Step 3: Write the minimal implementation**

\`\`\`html
<label class="theme-secondary-text space-y-1 text-xs font-medium">
  <span>동 코드 직접 입력</span>
  <input class="theme-control w-full rounded-lg px-3 text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500">
</label>
\`\`\`

Use \`theme-form-grid\` for modal cards and \`theme-control\` for editable/read-only inputs. Preserve all IDs, names, Alpine expressions, and money-formatting logic.

- [ ] **Step 4: Run focused tests**

Run: \`python -m pytest tests/unit/test_light_theme_templates.py -v; python -m pytest tests/integration/test_web_v2.py -k result_header_owns_sort_control -v\`

Expected: PASS.

- [ ] **Step 5: Commit**

\`\`\`bash
git add src/realty_radar/web/templates/listings/index.html src/realty_radar/web/templates/settings/_inline_profile_modal.html tests/unit/test_light_theme_templates.py
git commit -m "fix: improve search settings light theme contrast"
\`\`\`

### Task 3: Pass explicit favorite payloads to cards

**Files:**
- Modify: \`src/realty_radar/web/routes/home.py:327-403,502-550,620-650\`
- Modify: \`src/realty_radar/web/templates/listings/_listing_cards.html:43-56,143-152\`
- Modify: \`src/realty_radar/web/templates/listings/list_partial.html:56-57\`
- Modify: \`src/realty_radar/web/templates/listings/complex_listings_partial.html:1-5\`
- Modify: \`tests/integration/test_web_v2.py\`

**Interfaces:**
- Consumes: ORM listing attributes and attached \`eligible_loans\`.
- Produces: \`_favorite_listing_payload(item) -> dict[str, object]\`, \`_favorite_complex_payload(group) -> dict[str, object]\`, and favorite payload maps in full/HTMX contexts.

- [ ] **Step 1: Write the failing card-payload contract**

\`\`\`python
def test_listing_and_complex_favorite_buttons_include_stable_ids():
    response = TestClient(app).get("/")
    grouped = TestClient(app).get("/?group_by_complex=true")

    assert 'toggleListingFavorite({&quot;article_id&quot;:' in response.text
    assert 'toggleComplexFavorite({&quot;complex_id&quot;:' in grouped.text
    assert "toggleListingFavorite([])" not in response.text
    assert "toggleComplexFavorite([])" not in grouped.text
\`\`\`

Seed one \`ListingCurrent\` and \`ComplexCurrent\` using the test database pattern already used in this module.

- [ ] **Step 2: Run it to verify the observed failure**

Run: \`python -m pytest tests/integration/test_web_v2.py -k favorite_buttons_include_stable_ids -v\`

Expected: FAIL because Jinja serializes the ORM/slot objects as \`[]\`.

- [ ] **Step 3: Write the minimal payload serializer and template wiring**

\`\`\`python
def _favorite_listing_payload(item: object) -> dict[str, object]:
    return {
        "article_id": item.article_id,
        "complex_id": item.complex_id,
        "complex_name": item.complex_name,
        "address": item.address,
        "trade_type": item.trade_type,
        "primary_price": item.primary_price,
        "exclusive_area_x100": item.exclusive_area_x100,
        "floor_no": item.floor_no,
        "direction_code": item.direction_code,
        "household_count": item.household_count,
        "construction_year": item.construction_year,
        "eligible_loans": [{"loan_type_name": loan.loan_type_name} for loan in item.eligible_loans],
    }
\`\`\`

Build matching minimal complex payloads. Pass lookup maps to every full and partial rendering path. Use \`onclick="event.stopPropagation(); toggleListingFavorite(...)"\` for listing cards; preserve group-button event cancellation.

- [ ] **Step 4: Run focused tests**

Run: \`python -m pytest tests/integration/test_web_v2.py -k "favorite_buttons_include_stable_ids or listing_card_shows_populated_detail_fields" -v\`

Expected: PASS.

- [ ] **Step 5: Commit**

\`\`\`bash
git add src/realty_radar/web/routes/home.py src/realty_radar/web/templates/listings/_listing_cards.html src/realty_radar/web/templates/listings/list_partial.html src/realty_radar/web/templates/listings/complex_listings_partial.html tests/integration/test_web_v2.py
git commit -m "fix: serialize favorites card payloads"
\`\`\`

### Task 4: Persist and merge guest and signed-in favorites

**Files:**
- Modify: \`src/realty_radar/web/templates/listings/index.html:1083-1468\`
- Create: \`tests/integration/test_user_preferences.py\`
- Modify: \`tests/unit/test_light_theme_templates.py\`

**Interfaces:**
- Consumes: \`POST /api/user/preference\`, \`GET /api/user/preference\`, authenticated session cookies, and the three guest localStorage keys.
- Produces: ID-deduplicated guest/server merge, API-persisted signed-in favorites, and preserved guest data on failed sync.

- [ ] **Step 1: Write the failing authenticated persistence test**

\`\`\`python
def test_authenticated_preference_persists_favorites_across_requests(preference_client):
    favorites = {
        "listings": [{"article_id": 101}],
        "complexes": [{"complex_id": 202}],
        "isGroupMode": True,
    }

    assert preference_client.post("/api/user/preference", json={"favorites": favorites}).status_code == 200
    assert preference_client.get("/api/user/preference").json()["favorites"] == favorites
\`\`\`

Create \`preference_client\` with SQLite, \`Base.metadata.create_all\`, a \`UserAccount\`, a \`get_db\` override, and a valid session cookie using the existing dashboard-test fixture pattern.

- [ ] **Step 2: Run it and investigate any API failure before browser code**

Run: \`python -m pytest tests/integration/test_user_preferences.py -v\`

Expected: PASS with the existing API; if it fails, fix only the identified API persistence defect.

- [ ] **Step 3: Write the failing guest merge safety contract**

\`\`\`python
def test_favorites_manager_keeps_guest_storage_and_merges_by_ids():
    template = (TEMPLATE_ROOT / "listings" / "index.html").read_text(encoding="utf-8")

    assert 'this.load(this.STORAGE_KEY_LISTINGS, [])' in template
    assert 'String(x.article_id) === String(item.article_id)' in template
    assert 'String(x.complex_id) === String(c.complex_id)' in template
    assert "localStorage.removeItem(this.STORAGE_KEY_LISTINGS)" not in template
\`\`\`

- [ ] **Step 4: Implement only required merge/sync behavior**

Keep localStorage writes before network activity. Have \`syncToServer()\` return whether the response is OK; do not clear guest storage on errors. Keep existing ID-based server/local merging and re-save the merged result after successful load. Update only favorite dynamic HTML classes touched by this work to use light/dark-safe classes.

- [ ] **Step 5: Run API and browser checks**

Run: \`python -m pytest tests/integration/test_user_preferences.py tests/unit/test_light_theme_templates.py -v\`

Use Playwright with the installed Chrome executable to place a guest favorite in localStorage, reload, sign in, confirm the preference POST contains the merged payload, reload as that user, and confirm the sidebar count restores from \`GET /api/user/preference\`.

- [ ] **Step 6: Commit**

\`\`\`bash
git add src/realty_radar/web/templates/listings/index.html tests/integration/test_user_preferences.py tests/unit/test_light_theme_templates.py
git commit -m "fix: persist and merge user favorites"
\`\`\`

### Task 5: Full regression and visual verification

**Files:**
- Verify only; modify only if a named regression identifies a task-owned defect.

**Interfaces:**
- Consumes: completed Tasks 1-4.
- Produces: fresh evidence for routing, light-mode contrast, guest persistence, signed-in restoration, and search behavior.

- [ ] **Step 1: Run focused regression tests**

Run: \`python -m pytest tests/unit/test_light_theme_templates.py tests/integration/test_user_preferences.py tests/integration/test_web_v2.py -v\`

Expected: PASS.

- [ ] **Step 2: Run the full suite**

Run: \`python -m pytest -v\`

Expected: PASS except explicitly skipped environment-marked tests.

- [ ] **Step 3: Verify in Chrome**

Check \`/settings\` redirects to \`/\`; the header has no settings link; profile modal, price/area detail, and advanced detail are readable in light and dark modes; guest favorite add/remove survives reload; and login, reload, logout, then login restores the DB-backed list.

- [ ] **Step 4: Commit any regression-only task-owned edit**

\`\`\`bash
git add tests
git commit -m "test: cover settings and favorites regressions"
\`\`\`

