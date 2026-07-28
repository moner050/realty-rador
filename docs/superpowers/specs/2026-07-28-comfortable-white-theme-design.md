# Comfortable White Theme Design

## Goal

Replace the light theme's clinical white and inconsistent dark surfaces with a high-legibility, premium warm-neutral visual system. Rebuild dark-mode surfaces and contrast with the same semantic tokens while keeping the theme toggle, stored preference key, server behavior, and page structure unchanged.

## Visual direction

- Canvas: `#F6F5F2`, a low-glare warm off-white rather than blue-gray or pure white.
- Raised surface: `#FFFDF9`, used for cards, dialogs, and navigation.
- Subtle surface: `#EEEBE6`, used for read-only, grouped, and disabled areas.
- Primary text: `#25262A`; secondary text: `#51545C`; muted text: `#6B6E76`.
- Dividers: `#DEDAD4`; focus and primary actions retain the indigo visual language.
- Elevation: thin warm borders and restrained shadows. Hover may increase elevation but must not rely on shadow alone to communicate state.

## Scope

Apply the light-theme system to the shared shell and every user-facing template with light-mode surfaces: search/filter UI, listing and complex cards, dialogs, favorites drawer and its JavaScript-rendered contents, login/register, settings, and crawl-job pages. Components currently using unconditional slate-900/slate-800 classes in the settings and favorites UIs must receive explicit light-mode equivalents.

Do not change API routes, Jinja data, user-preference storage, or the `rr_theme_v1` toggle flow.

## Implementation approach

Use a shared CSS token layer in `base.html` for both themes and explicit semantic classes for shared surfaces, filters, cards, result controls, and forms. This prevents broad utility-string overrides from recoloring primary buttons or leaving hard-coded dark panels in the light theme.

Use the following semantic roles consistently:

- App canvas and header/footer: warm canvas and raised surface.
- Cards, dialogs, drawers, forms: raised surface with a warm divider.
- Grouped/secondary content, disabled controls, table headers: subtle surface.
- Primary, secondary, and muted text: the three contrast levels above; no light-mode `text-slate-400` for essential content.
- Status chips: retain their existing indigo, emerald, sky, and amber meanings with sufficiently dark text and gentle backgrounds.

## Acceptance criteria

1. In light mode, no main content panel, settings field group, favorites drawer/card, modal, or auth card renders as an unintended dark slate surface.
2. Primary and secondary text on light surfaces remains clearly readable; muted text is reserved for non-essential supporting copy.
3. Active, hover, focus, selected, disabled, and error states remain distinguishable without depending only on color.
4. Toggling to dark mode preserves interactions and renders all text, controls, and surfaces with the dark token contrast levels.
5. Existing template and application tests pass, and the affected pages render without browser-console errors.

## Non-goals

- No new theme choice, persisted setting, font family, layout redesign, or backend change.
- No modification of dark-mode styling beyond avoiding accidental light-mode overrides.
