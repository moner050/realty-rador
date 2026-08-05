from datetime import datetime, timezone
import re
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from realty_radar.config import settings
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.infrastructure.database.models import Base, ComplexCurrent, ListingCurrent
from realty_radar.infrastructure.database.models.v2 import GEOCODE_STATUS_OK, GEOCODE_STATUS_PENDING
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.main import app
from realty_radar.web.routes import home


def _factory(*, verified_coordinate: bool):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    seen_at = datetime(2026, 8, 3, tzinfo=timezone.utc)
    with factory() as session:
        session.add(
            ComplexCurrent(
                complex_id=1,
                region_code=1150010200,
                name="지도 테스트 아파트",
                normalized_name="지도테스트아파트",
                address="서울특별시 강서구 테스트로 1",
                latitude="37.5500000" if verified_coordinate else None,
                longitude="126.8500000" if verified_coordinate else None,
                geocode_status=GEOCODE_STATUS_OK if verified_coordinate else 0,
                state_hash=b"c" * 16,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                updated_at=seen_at,
            )
        )
        session.add(
            ListingCurrent(
                article_id=2,
                complex_id=1,
                region_code=1150010200,
                complex_name="지도 테스트 아파트",
                address="서울특별시 강서구 테스트로 1",
                trade_type=1,
                primary_price=500_000_000,
                state_hash=b"l" * 16,
                last_seen_job_id=1,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                last_changed_at=seen_at,
            )
        )
        session.commit()
    return factory


def _factory_with_three_complexes(*, two_verified: bool):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    seen_at = datetime(2026, 8, 3, tzinfo=timezone.utc)
    coordinates = (("37.5500000", "126.8500000"), ("37.5600000", "127.8500000"), (None, None))
    with factory() as session:
        for complex_id, (latitude, longitude) in enumerate(coordinates, start=1):
            verified = two_verified and latitude is not None
            session.add(
                ComplexCurrent(
                    complex_id=complex_id,
                    region_code=1150010200,
                    name=f"Complex {complex_id}",
                    normalized_name=f"Complex {complex_id}",
                    address=f"Address {complex_id}",
                    latitude=latitude if verified else None,
                    longitude=longitude if verified else None,
                    geocode_status=GEOCODE_STATUS_OK if verified else GEOCODE_STATUS_PENDING,
                    state_hash=bytes([complex_id]) * 16,
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    updated_at=seen_at,
                )
            )
            session.add(
                ListingCurrent(
                    article_id=complex_id,
                    complex_id=complex_id,
                    region_code=1150010200,
                    complex_name=f"Complex {complex_id}",
                    address=f"Address {complex_id}",
                    trade_type=1,
                    primary_price=500_000_000,
                    state_hash=bytes([complex_id + 10]) * 16,
                    last_seen_job_id=1,
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    last_changed_at=seen_at,
                )
            )
        session.commit()
    return factory


def _override(factory):
    def override_db():
        with factory() as session:
            yield session

    return override_db


def test_search_result_exposes_public_map_urls_without_marker_payload(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    monkeypatch.setattr(settings, "naver_map_client_secret", "server-secret")

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "data-listing-map-root" in response.text
    assert "data-map-data-url=" in response.text
    assert "data-map-cards-url=" in response.text
    assert "data-map-matching-count" in response.text
    assert "data-map-mapped-count" in response.text
    assert "data-map-unmapped-count" in response.text
    assert "data-map-summary-count" in response.text
    assert "data-map-complex-url-template=" in response.text
    assert "data-map-complex-modal" in response.text
    assert 'id="listing-map-payload"' not in response.text
    assert "ncpKeyId=public-key" in response.text
    assert "지도 테스트 아파트" in response.text
    assert "server-secret" not in response.text
    assert response.text.index('src="https://oapi.map.naver.com/openapi/v3/maps.js') < response.text.index("<body")
    assert response.text.index('src="/static/listing-map.js"') < response.text.index("<body")


def test_search_result_renders_one_map_first_workspace(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.text.count('id="listing-search-form"') == 1
    assert "data-search-workspace" in response.text
    assert "data-search-toolbar" in response.text
    assert "data-applied-filter-summary" in response.text
    assert "data-map-filter-trigger" in response.text
    assert response.text.index("data-search-toolbar") < response.text.index("data-listing-map-root")
    assert response.text.index("data-listing-map-root") < response.text.index('id="listing-collection"')
    assert "data-map-data-url=" in response.text
    assert "data-map-cards-url=" in response.text
    assert "data-map-complex-url-template=" in response.text


def test_map_workspace_keeps_controls_and_result_summary_in_one_panel(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert 'data-search-control-panel' in response.text
    assert 'id="listing-search-form"' in response.text
    assert 'id="search-result-summary"' in response.text
    assert response.text.index('id="listing-search-form"') < response.text.index('id="search-result-summary"')
    assert response.text.index('id="search-result-summary"') < response.text.index('data-listing-map-root')


def test_htmx_search_returns_collection_and_oob_search_updates(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get(
            "/listings/search?trade_types=SALE",
            headers={"HX-Request": "true"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'id="listing-collection"' in response.text
    assert 'id="search-result-summary" hx-swap-oob="outerHTML"' in response.text
    assert 'id="map-search-config" hx-swap-oob="outerHTML"' in response.text
    assert "trade_types=SALE" in response.text
    assert "data-listing-map-root" not in response.text


def test_search_result_exposes_clearable_compact_filter_chips(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/?complex_keyword=%ED%85%8C%EC%8A%A4%ED%8A%B8&trade_types=SALE")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'data-applied-filter-clear data-filter-clear-names="complex_keyword"' in response.text
    assert 'data-applied-filter-clear data-filter-clear-names="trade_types"' in response.text


def test_map_first_workspace_exposes_accessible_filter_drawer(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'id="detailed-filter-modal"' in response.text
    assert "data-filter-panel" in response.text
    assert "left-auto" in response.text
    assert "data-filter-panel-body" in response.text
    assert "data-filter-panel-footer" in response.text
    assert "data-filter-panel-apply" in response.text
    assert 'aria-controls="detailed-filter-modal"' in response.text
    assert 'aria-expanded="false"' in response.text
    assert "data-map-results-toolbar" in response.text
    assert "data-map-loading hidden" in response.text
    assert "data-card-loading hidden" in response.text


def test_map_first_workspace_collapses_applicant_summary_by_default(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "<details data-applicant-summary" in response.text
    assert "<summary" in response.text
    assert response.text.index("data-applicant-summary") < response.text.index('id="listing-search-form"')


def test_map_data_endpoint_returns_labelled_sido_circle_without_geocoding(monkeypatch):
    factory = _factory_with_three_complexes(two_verified=True)
    monkeypatch.setattr(
        home,
        "NaverGeocoder",
        lambda: (_ for _ in ()).throw(AssertionError("read-only endpoint")),
        raising=False,
    )
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/api/listings/map-data?map_zoom=7")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "sido"
    assert payload["matching_complex_count"] == 3
    assert payload["mapped_complex_count"] == 2
    assert payload["unmapped_complex_count"] == 1
    assert payload["mapped_listing_count"] == 2
    assert payload["markers"] == []
    assert [(cluster["label"], cluster["complex_count"], cluster["listing_count"]) for cluster in payload["clusters"]] == [
        ("서울특별시", 2, 2)
    ]


def test_initial_map_data_clears_viewport_bounds_before_aggregating():
    factory = _factory_with_three_complexes(two_verified=True)
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get(
            "/api/listings/map-data?map_zoom=7&map_initial=true"
            "&map_west=126.80&map_south=37.50&map_east=126.90&map_north=37.60"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["matching_complex_count"] == 3


def test_map_cards_endpoint_returns_collection_without_a_second_map_root(monkeypatch):
    factory = _factory_with_three_complexes(two_verified=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get(
            "/listings/map-cards?map_west=126.80&map_south=37.50&map_east=126.90&map_north=37.60",
            headers={"HX-Request": "true"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.text.count('id="listing-collection"') == 1
    assert re.match(r'\s*<section\s+id="listing-collection"(?:\s|>)', response.text)
    assert "data-listing-map-root" not in response.text
    assert 'data-map-focus-latitude="37.55"' in response.text
    assert 'data-map-focus-longitude="126.85"' in response.text
    assert "data-listing-detail-button" in response.text


def test_grouped_map_cards_include_a_coordinate_for_map_focus():
    factory = _factory_with_three_complexes(two_verified=True)
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get(
            "/listings/map-cards?group_by_complex=true",
            headers={"HX-Request": "true"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'data-complex-group' in response.text
    assert 'data-map-focus-latitude="37.55"' in response.text
    assert 'data-map-focus-longitude="126.85"' in response.text


def test_authenticated_map_cards_do_not_persist_transient_search_bounds(monkeypatch):
    factory = _factory_with_three_complexes(two_verified=True)
    saved_filters = []
    monkeypatch.setattr(home, "verify_session_token", lambda _token: "map-user")
    monkeypatch.setattr(
        home,
        "save_user_search_filter",
        lambda filters, username: saved_filters.append((filters, username)),
    )
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app, cookies={home.SESSION_COOKIE_NAME: "signed-session"}).get(
            "/listings/map-cards?map_west=126.80&map_south=37.50&map_east=126.90&map_north=37.60",
            headers={"HX-Request": "true"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert saved_filters == []


def test_map_cards_pager_targets_only_the_listing_collection():
    factory = _factory_with_three_complexes(two_verified=True)
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/listings/map-cards?page_size=1", headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'hx-target="#listing-collection"' in response.text
    assert 'hx-target="#search-results"' not in response.text


def test_map_cards_validation_error_replaces_the_listing_collection():
    factory = _factory_with_three_complexes(two_verified=True)
    app.dependency_overrides[get_db] = _override(factory)
    try:
        response = TestClient(app).get("/listings/map-cards?map_west=126.80", headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "#listing-collection"
    assert 'id="listing-collection"' in response.text


def test_search_result_has_a_hidden_until_two_selected_comparison_tray(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'id="favorite-compare-tray"' in response.text
    assert "data-favorite-compare-count" in response.text
    assert "data-favorite-compare-button" in response.text


def test_search_result_exposes_map_data_endpoints_without_a_verified_coordinate(monkeypatch):
    factory = _factory(verified_coordinate=False)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "data-listing-map-root" in response.text
    assert "data-listings-map" in response.text
    assert 'data-map-data-url="http://testserver/api/listings/map-data?' in response.text
    assert 'data-map-cards-url="http://testserver/listings/map-cards?' in response.text
    assert 'id="listing-map-payload"' not in response.text


def test_map_sidebar_does_not_geocode_or_commit_pending_coordinates(monkeypatch):
    factory = _factory(verified_coordinate=False)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")

    class GeocoderConstructed(BaseException):
        pass

    monkeypatch.setattr(
        home,
        "NaverGeocoder",
        lambda: (_ for _ in ()).throw(GeocoderConstructed("must not construct geocoder")),
        raising=False,
    )

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/listings/map")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'id="listing-map-payload"' not in response.text
    with factory() as session:
        refreshed = session.get(ComplexCurrent, 1)
        assert refreshed.geocode_status == GEOCODE_STATUS_PENDING
        assert refreshed.latitude is None
        assert refreshed.longitude is None


def test_search_response_has_map_root_but_no_alternate_view_controls(monkeypatch):
    factory = _factory(verified_coordinate=False)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'data-listing-map-root' in response.text
    assert 'hx-get="http://testserver/listings/map?' not in response.text
    assert 'data-view-mode=' not in response.text


def test_map_bound_search_returns_configuration_without_persisting_bounds(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get(
            "/listings/search?map_west=126.80&map_south=37.50&map_east=126.90&map_north=37.60",
            headers={"HX-Request": "true"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "data-listing-map-root" not in response.text
    assert 'id="map-search-config" hx-swap-oob="outerHTML"' in response.text
    map_data_url = re.search(r'data-map-data-url="([^"]+)"', response.text).group(1)
    map_cards_url = re.search(r'data-map-cards-url="([^"]+)"', response.text).group(1)
    map_complex_url = re.search(r'data-map-complex-url-template="([^"]+)"', response.text).group(1)
    assert "map_west" not in map_data_url
    assert "map_south" not in map_data_url
    assert "map_west" not in map_cards_url
    assert "map_south" not in map_cards_url
    assert "map_west" not in map_complex_url
    assert "map_south" not in map_complex_url
    assert "__complex_id__" in map_complex_url


def test_map_loading_indicators_start_hidden_without_a_full_map_overlay(monkeypatch):
    factory = _factory(verified_coordinate=True)
    monkeypatch.setattr(settings, "naver_map_client_id", "public-key")

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert 'data-map-loading hidden' in response.text
    assert 'data-map-loading hidden class="hidden absolute inset-0' not in response.text
    assert 'data-card-loading hidden' in response.text


def test_map_sidebar_url_preserves_the_current_result_page_cursor():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": "/listings/search",
            "raw_path": b"/listings/search",
            "query_string": b"",
            "headers": [(b"host", b"testserver")],
            "router": app.router,
        }
    )

    map_url = home._map_sidebar_url(request, ListingSearchFilter(cursor="second-page-cursor"))

    assert parse_qs(urlparse(map_url).query)["cursor"] == ["second-page-cursor"]
