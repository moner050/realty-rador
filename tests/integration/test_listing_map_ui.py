from datetime import datetime, timezone
import json
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


def test_search_result_embeds_only_public_key_and_verified_marker_payload(monkeypatch):
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
    assert 'id="listings-map"' in response.text
    assert 'id="listing-map-payload"' in response.text
    assert "ncpKeyId=public-key" in response.text
    assert "지도 테스트 아파트" in response.text
    assert "126.85" in response.text
    assert "server-secret" not in response.text
    assert response.text.index('src="https://oapi.map.naver.com/openapi/v3/maps.js') < response.text.index("<body")
    assert response.text.index('src="/static/listing-map.js"') < response.text.index("<body")
    payload_match = re.search(
        r'<script id="listing-map-payload"[^>]*>(.*?)</script>', response.text, re.DOTALL
    )
    assert payload_match is not None
    assert json.loads(payload_match.group(1))[0]["complex_id"] == 1


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


def test_search_result_starts_a_map_sidebar_refresh_without_a_verified_coordinate(monkeypatch):
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
    assert 'id="listings-map"' not in response.text
    assert "지도 좌표를 준비하고 있습니다." in response.text
    assert 'hx-get="http://testserver/listings/map?' in response.text


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


def test_search_response_has_a_map_sidebar_loader_but_no_alternate_view_controls(monkeypatch):
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
    assert 'hx-get="http://testserver/listings/map?' in response.text
    assert 'data-view-mode=' not in response.text


def test_map_bound_search_places_the_map_before_matching_cards_without_persisting_bounds(monkeypatch):
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
    assert response.text.index("data-listing-map-root") < response.text.index('id="listing-cards"')
    assert 'data-map-search-url="http://testserver/listings/search?' in response.text
    map_search_url = re.search(r'data-map-search-url="([^"]+)"', response.text).group(1)
    assert "map_west" not in map_search_url
    assert "map_south" not in map_search_url
    assert "h-[56vh]" in response.text


def test_map_loading_overlay_starts_with_a_tailwind_hidden_class(monkeypatch):
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

    assert 'data-map-loading hidden class="hidden ' in response.text


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
