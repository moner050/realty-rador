# Map-first listing UX design

## Goal

Make the default search experience a large central map followed by listings
visible in that map area, while improving listing comparison before map
interaction and visual polish.

## Product decisions

- The previous view switcher remains removed. There is one default map-first
  layout, not a list/split/map mode choice.
- Existing purchase, price, area, commute, loan, and saved search filters stay
  active. The current map viewport adds an AND condition to those filters.
- Map viewport bounds are transient client state. They are not saved as a user
  search preference and do not cause URL history churn.
- A listing without a verified complex coordinate cannot be truthfully assigned
  to a viewport. It is excluded from the map-bounded list and reported as a
  separate coordinate-pending count.

## Delivery order

### 1. Listing comparison first

- Reorder cards into a consistent hierarchy: price and complex identity,
  location and transaction facts, then decision factors such as area,
  construction year, households, affordability, loan status, and commute.
- Make unavailable enrichment visible as `확인 대기`, rather than leaving a
  blank or presenting a zero value.
- Reuse the existing favorite payloads to add an in-page comparison tray for
  selected listings. It compares price, area, loan availability, commute, and
  construction year without creating a separate comparison route.

### 2. Map-first bounded search

- Layout: compact filter summary, central desktop map (about 56% of viewport
  height), a result summary, then responsive listing cards below. On mobile,
  map precedes a one-column list.
- On Naver map `idle`, debounce for 300ms and request the current bounds plus
  existing filters. A later interaction cancels or supersedes an older request.
- Add optional west, south, east, and north bounds to the listing search
  contract. The database query joins verified `ComplexCurrent` coordinates and
  returns only listings inside those bounds.
- Reset the result page when bounds change. Markers and cards come from the
  same result identifiers, and the map shows the count for the active area.
- Enforce a minimum useful zoom/maximum area before automatic map search. When
  the view is too broad, retain the last valid result and explain how to zoom
  in instead of issuing an unbounded query.

### 3. Visual polish

- Use one visual hierarchy for filter summary, result count, cards, map
  controls, primary actions, hover/focus states, and loading feedback.
- Keep light/dark colors semantic and scoped. Avoid global text overrides that
  can make primary action labels unreadable.
- Use skeleton/loading feedback for cards during a map-bound update and an
  explicit empty-state distinction: no matching listings, overly broad map,
  and coordinates pending.

## Data and performance constraints

- Map bounds must use persisted, verified coordinates only; do not geocode in
  the hot search request and never generate fallback coordinates.
- Add an index suitable for active listing-to-complex coordinate lookup only
  after measuring the real query with `EXPLAIN ANALYZE`.
- Preserve existing cursor validation. Map-bound responses have their own
  filter fingerprint and must not reuse a cursor from another viewport.
- Keep normal non-map result pages below their current response-size and query
  safety expectations.

## Error handling

- A failed or stale map request never replaces a newer successful result.
- Missing map configuration leaves the list usable and explains the map state.
- Geocode-pending complexes show a count but do not appear as inaccurately
  placed markers or viewport results.

## Verification

- Unit tests cover coordinate-bound predicates, boundary inclusivity, cursor
  fingerprint changes, and coordinate-pending counts.
- Integration tests cover the HTML/API map-bounded result, marker/card identity,
  profile filters retained with bounds, and visible state messages.
- Browser verification covers initial map-first render, zoom/move result update,
  stale-request protection, card comparison selection, responsive layout, and
  light/dark readability.
- Use `EXPLAIN ANALYZE` and a representative benchmark before accepting a new
  coordinate-query index.
