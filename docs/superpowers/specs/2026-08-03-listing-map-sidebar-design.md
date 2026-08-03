# Listing map sidebar design

## Goal

Keep the search result list as the primary view and show its map in a permanent
right sidebar on desktop. Remove the list, split, and map-only view controls.
The map must populate for the current search result even when its complexes have
not been geocoded yet.

## Scope

- Preserve the existing two-column result layout: listing cards on the left and
  a sticky map sidebar on the right. On narrow screens, the map follows the list.
- Remove the view-mode switcher and its JavaScript; there is no alternate view.
- After a result response renders, load only its map sidebar through HTMX.
- The sidebar endpoint re-runs the same search filter, identifies the result
  complexes, and geocodes only their pending or retryable failed addresses.
- Limit the targeted geocoding work to the current page's complexes. Existing
  verified coordinates are reused and no coordinates are invented.
- Render the refreshed marker payload in the sidebar. If configuration is absent,
  an address is not found, or geocoding fails, show an explicit status message.

## Data flow

1. The normal search route renders cards immediately and places a loading map
   sidebar beside them.
2. HTMX requests a map-sidebar route with the same filter query.
3. The route searches the current page, runs the existing bounded geocode
   backfill for only those complex IDs, commits successful status changes, and
   builds markers from verified coordinates.
4. HTMX replaces only the map sidebar content. The existing map controller
   mounts the Naver map from the refreshed JSON payload.

## Error handling

- A missing public map client ID displays the existing configuration message.
- Missing or failed geocodes do not fabricate a marker. The sidebar states how
  many result complexes could not be mapped.
- The list response is never held up by Naver Geocoding. A map-side request
  failure leaves a clear retryable status message in the sidebar.

## Verification

- Template/route tests prove the mode switcher is absent and the sidebar is
  always present in a search response.
- Route tests prove an initially pending result triggers targeted backfill and
  returns a verified marker without exposing the NCP secret.
- Existing map-controller tests continue to mount after an HTMX sidebar swap.
- Run focused tests, the JavaScript controller test, and the complete pytest
  suite.
