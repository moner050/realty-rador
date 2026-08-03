# NAVER Maps Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render only verified apartment-complex coordinates on a NAVER Map that remains correct after HTMX search updates.

**Architecture:** Coordinates belong to `complex_current`, not the listing hot table. A server-side geocoder fills missing complex coordinates and an application service performs one batch lookup for the visible complex IDs. The rendered result embeds only a public map key and verified marker payload; a browser module owns map creation and disposal for each HTMX result fragment.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy/Alembic, MySQL 8.4, SQLite tests, NAVER Maps JavaScript API v3, Node built-in test runner.

## Global Constraints

- Keep the `listing_current` search query join-free; map coordinates are retrieved by one separate batch query for the current page.
- Never generate fallback coordinates. A missing or failed geocode is absent from the marker payload and shown as `위치 확인 중`.
- The browser receives `NAVER_MAP_CLIENT_ID` only. `NAVER_MAP_CLIENT_SECRET` stays server-side and is never rendered or logged.
- Use `python -m pytest`, not bare `pytest`.
- Do not run the geocode backfill without a configured production key and an explicit operator command.
- Preserve normal and grouped search behavior, cursor validation, and existing result-card interactions.

---

### Task 1: Coordinate model and NAVER map configuration

**Files:**
- Modify: `src/realty_radar/config.py`
- Modify: `src/realty_radar/infrastructure/database/models/v2.py`
- Modify: `src/realty_radar/application/listing_batch_writer.py`
- Create: `migrations/versions/2026_08_03_0009_complex_geocode.py`
- Modify: `.env.example`
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/test_v2_schema.py`
- Test: `tests/unit/test_listing_batch_writer.py`

**Interfaces:**
- Produces `Settings.naver_map_client_id: str | None` and `Settings.naver_map_client_secret: str | None`.
- Produces nullable `ComplexCurrent.latitude`, `longitude`, `geocode_status`, `geocoded_address_hash`, `geocoded_at`, `geocode_attempted_at`, and `geocode_retry_after` columns.

- [ ] **Step 1: Write failing configuration and schema tests**

```python
def test_settings_reads_naver_map_credentials_from_environment(monkeypatch):
    monkeypatch.setenv("NAVER_MAP_CLIENT_ID", "public-key")
    monkeypatch.setenv("NAVER_MAP_CLIENT_SECRET", "server-secret")
    settings = Settings(_env_file=None)
    assert settings.naver_map_client_id == "public-key"
    assert settings.naver_map_client_secret == "server-secret"

def test_complex_current_declares_nullable_verified_coordinate_columns():
    columns = ComplexCurrent.__table__.columns
    assert columns["latitude"].nullable is True
    assert columns["longitude"].nullable is True
    assert columns["geocode_status"].nullable is False

def test_complex_address_change_resets_cached_coordinates_to_pending(session):
    ListingBatchWriter(session).write([changed_address_row], job_id=1)
    complex_row = session.get(ComplexCurrent, changed_address_row.complex_id)
    assert (complex_row.latitude, complex_row.longitude, complex_row.geocode_status) == (None, None, 0)
```

- [ ] **Step 2: Run focused tests and verify they fail because the settings and columns do not exist**

Run: `python -m pytest tests/unit/test_config.py tests/unit/test_v2_schema.py -q`

- [ ] **Step 3: Add the minimal settings, SQLAlchemy columns, Alembic migration, and environment documentation**

```python
naver_map_client_id: str | None = Field(default=None, validation_alias="NAVER_MAP_CLIENT_ID")
naver_map_client_secret: str | None = Field(default=None, validation_alias="NAVER_MAP_CLIENT_SECRET")
```

```python
latitude = Column(mysql.DECIMAL(10, 7), nullable=True)
longitude = Column(mysql.DECIMAL(10, 7), nullable=True)
geocode_status = Column(UnsignedTinyInt, nullable=False, server_default=text("0"))
```

```python
"latitude": case(
    (ComplexCurrent.address != excluded_complex.address, None),
    else_=ComplexCurrent.latitude,
)
```

- [ ] **Step 4: Run focused tests and verify they pass**

Run: `python -m pytest tests/unit/test_config.py tests/unit/test_v2_schema.py -q`

### Task 2: Server-side geocoder and explicit backfill command

**Files:**
- Create: `src/realty_radar/enrichment/naver_maps/geocoder.py`
- Create: `src/realty_radar/enrichment/naver_maps/backfill.py`
- Create: `scripts/backfill_complex_geocodes.py`
- Test: `tests/unit/test_naver_geocoder.py`

**Interfaces:**
- Produces `NaverGeocoder.geocode(address: str) -> GeocodeResult`.
- Produces `ComplexGeocodeBackfill.run(batch_size: int) -> GeocodeBackfillStats`.
- A `GeocodeResult` is either an `OK` latitude/longitude pair or a non-OK status with no coordinates.

- [ ] **Step 1: Write failing tests for a successful response, an empty response, and missing credentials**

```python
def test_geocode_returns_verified_coordinates_from_naver_response():
    result = geocoder.geocode("서울특별시 강서구 테스트로 1")
    assert result.status is GeocodeStatus.OK
    assert result.latitude == Decimal("37.5500000")
    assert result.longitude == Decimal("126.8500000")

def test_geocode_without_credentials_returns_not_configured_without_http_call():
    assert geocoder.geocode("서울특별시 강서구 테스트로 1").status is GeocodeStatus.NOT_CONFIGURED
```

- [ ] **Step 2: Run the focused tests and verify the module import fails**

Run: `python -m pytest tests/unit/test_naver_geocoder.py -q`

- [ ] **Step 3: Implement the synchronous HTTP client boundary and idempotent backfill selection**

```python
headers = {
    "x-ncp-apigw-api-key-id": self.client_id,
    "x-ncp-apigw-api-key": self.client_secret,
}
```

```python
candidate = (
    select(ComplexCurrent)
    .where((ComplexCurrent.geocode_status == 0) | (ComplexCurrent.geocode_retry_after <= now))
    .order_by(ComplexCurrent.complex_id)
    .limit(batch_size)
)
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -m pytest tests/unit/test_naver_geocoder.py -q`

### Task 3: Marker payload service and search-result integration

**Files:**
- Create: `src/realty_radar/application/listing_map_service.py`
- Modify: `src/realty_radar/web/routes/home.py`
- Test: `tests/unit/test_listing_map_service.py`
- Test: `tests/integration/test_listing_search_v2.py`

**Interfaces:**
- Produces `ListingMapMarker(complex_id, complex_name, address, latitude, longitude, listing_count, min_price, max_price)`.
- Produces `ListingMapService.build_markers(result: SearchResult) -> list[ListingMapMarker]`.
- The service executes one `complex_current WHERE complex_id IN (...)` query and returns no marker for an unverified coordinate.

- [ ] **Step 1: Write failing SQLite tests for normal results, grouped results, and missing coordinates**

```python
def test_grouped_result_uses_one_verified_marker_per_complex(session):
    markers = ListingMapService(session).build_markers(grouped_result)
    assert [(marker.complex_id, marker.listing_count) for marker in markers] == [(1001, 3)]

def test_marker_payload_excludes_missing_coordinate_instead_of_inventing_one(session):
    assert ListingMapService(session).build_markers(normal_result) == []
```

- [ ] **Step 2: Run focused tests and verify the missing service causes failure**

Run: `python -m pytest tests/unit/test_listing_map_service.py -q`

- [ ] **Step 3: Implement the one-query marker service and add `map_markers` and `naver_map_client_id` to result contexts**

```python
coordinates = session.execute(
    select(ComplexCurrent).where(ComplexCurrent.complex_id.in_(complex_ids))
).scalars().all()
```

- [ ] **Step 4: Run focused unit and integration tests and verify they pass**

Run: `python -m pytest tests/unit/test_listing_map_service.py tests/integration/test_listing_search_v2.py -q`

### Task 4: Map fragment and HTMX-safe NAVER Maps controller

**Files:**
- Modify: `src/realty_radar/web/templates/listings/list_partial.html`
- Modify: `src/realty_radar/web/templates/listings/index.html`
- Create: `src/realty_radar/web/static/listing-map.js`
- Test: `tests/integration/test_listing_search_v2.py`
- Test: `tests/web/test_listing_map_controller.mjs`

**Interfaces:**
- The result fragment contains `#listings-map`, `#listing-map-payload`, and a no-location state.
- `window.RealtyRadarListingMap.mount(root)` creates markers from the JSON payload.
- `window.RealtyRadarListingMap.unmount(root)` removes markers and listeners before HTMX removes the fragment.

- [ ] **Step 1: Write failing template and controller behavior tests**

```python
def test_result_fragment_exposes_public_key_and_verified_marker_payload_only(client):
    response = client.get("/")
    assert "server-secret" not in response.text
    assert 'id="listing-map-payload"' in response.text
```

```javascript
test('unmount disposes markers before a replacement fragment mounts', () => {
  const controller = createListingMapController(fakeWindow);
  controller.mount(firstRoot);
  controller.unmount(firstRoot);
  controller.mount(secondRoot);
  assert.equal(fakeNaver.createdMarkers, 2);
  assert.equal(fakeNaver.disposedMarkers, 1);
});
```

- [ ] **Step 2: Run the focused tests and verify the map fragment and controller are missing**

Run: `python -m pytest tests/integration/test_listing_search_v2.py -q`

Run: `node --test tests/web/test_listing_map_controller.mjs`

- [ ] **Step 3: Implement the fragment and module**

```html
<script
  src="https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId={{ naver_map_client_id }}"
  defer
></script>
```

```javascript
document.body.addEventListener('htmx:beforeCleanupElement', (event) => {
  window.RealtyRadarListingMap.unmount(event.detail.elt);
});
document.body.addEventListener('htmx:afterSwap', (event) => {
  window.RealtyRadarListingMap.mount(event.detail.target);
});
```

- [ ] **Step 4: Run focused tests and verify they pass**

Run: `python -m pytest tests/integration/test_listing_search_v2.py -q`

Run: `node --test tests/web/test_listing_map_controller.mjs`

### Task 5: Full verification and operator handoff

**Files:**
- Modify: `README.md`
- Test: `tests/unit/test_benchmark_listing_search.py`

- [ ] **Step 1: Document required console configuration and safe backfill invocation**

```text
NAVER_MAP_CLIENT_ID must be registered for Dynamic Map and the deployed Web Service URL.
NAVER_MAP_CLIENT_SECRET is required only by the server-side geocode command.
python scripts/backfill_complex_geocodes.py --batch-size 100
```

- [ ] **Step 2: Run the complete automated suite**

Run: `python -m pytest -q`

- [ ] **Step 3: Run the listing-search benchmark contract**

Run: `python scripts/benchmark_listing_search.py`

- [ ] **Step 4: Perform a private browser smoke test after setting a valid NAVER_MAP_CLIENT_ID**

Expected: normal, grouped, sort, and pagination views retain the appropriate verified marker count; a missing key renders the setup state without breaking results.
