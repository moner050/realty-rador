from pathlib import Path


TEMPLATE_ROOT = Path("src/realty_radar/web/templates")


def test_embedded_filter_surface_keeps_light_theme_contrast():
    listings = (TEMPLATE_ROOT / "listings" / "index.html").read_text(encoding="utf-8")

    assert 'data-slider-variant="embedded"' in listings
    assert 'text-slate-900 dark:text-slate-100' in listings
    assert 'border-slate-200 dark:border-slate-800' in listings


def test_base_defines_scoped_comfortable_light_tokens():
    base = (TEMPLATE_ROOT / "base.html").read_text(encoding="utf-8")

    assert "html:not(.dark)" in base
    assert "--rr-canvas: #F6F5F2" in base
    assert "--rr-surface: #FFFDF9" in base
    assert "--rr-text-primary: #25262A" in base
    assert "--rr-surface-raised" in base
    assert "theme-surface" in base
    assert 'comfort-light [class*="text-white"]' not in base


def test_listing_templates_use_light_surfaces_and_keep_dark_variants():
    cards = (TEMPLATE_ROOT / "listings" / "_listing_cards.html").read_text(encoding="utf-8")
    partial = (TEMPLATE_ROOT / "listings" / "list_partial.html").read_text(encoding="utf-8")

    assert "theme-listing-card" in cards
    assert "dark:bg-slate-800" in cards
    assert "theme-result-toolbar" in partial


def test_non_listing_pages_use_light_surface_helpers():
    for relative_path in (
        "auth/login.html",
        "auth/register.html",
        "settings/_inline_profile_modal.html",
        "jobs/index.html",
    ):
        template = (TEMPLATE_ROOT / relative_path).read_text(encoding="utf-8")
        assert "theme-surface" in template


def test_search_detail_controls_and_profile_modal_use_light_safe_text_helpers():
    listings = (TEMPLATE_ROOT / "listings" / "index.html").read_text(encoding="utf-8")
    modal = (TEMPLATE_ROOT / "settings" / "_inline_profile_modal.html").read_text(encoding="utf-8")

    assert 'id="transaction-advanced-filters"' in listings
    assert 'text-xs font-semibold text-white hover:text-indigo-300' not in listings
    assert 'font-semibold text-xs text-white hover:text-indigo-300' not in listings
    assert "theme-profile-modal" in modal
    assert 'href="/settings"' not in modal


def test_quick_filter_presets_use_soft_indigo_without_overriding_primary_button_text():
    base = (TEMPLATE_ROOT / "base.html").read_text(encoding="utf-8")
    listings = (TEMPLATE_ROOT / "listings" / "index.html").read_text(encoding="utf-8")

    assert ".theme-soft-accent" in base
    assert 'html:not(.dark) #listing-search-form .text-white' not in base
    assert listings.count("theme-soft-accent") >= 4


def test_housing_quick_filter_uses_soft_emerald_contrast():
    base = (TEMPLATE_ROOT / "base.html").read_text(encoding="utf-8")
    listings = (TEMPLATE_ROOT / "listings" / "index.html").read_text(encoding="utf-8")

    assert ".theme-soft-emerald" in base
    assert 'data-quick-preset="tidy-town" class="theme-soft-emerald' in listings
    assert "bg-emerald-950/40" not in listings


def test_listing_filter_choices_define_visible_checked_state_for_both_themes():
    base = (TEMPLATE_ROOT / "base.html").read_text(encoding="utf-8")
    listings = (TEMPLATE_ROOT / "listings" / "index.html").read_text(encoding="utf-8")

    assert 'html:not(.dark) #listing-search-form.theme-filter-choice label:has(input[type="checkbox"]:checked)' in base
    assert 'html.dark .theme-filter-choice label:has(input[type="checkbox"]:checked)' in base
    assert '<form id="listing-search-form" class="theme-filter-choice' in listings
