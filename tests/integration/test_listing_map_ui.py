from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.config import settings
from realty_radar.infrastructure.database.models import Base, ComplexCurrent, ListingCurrent
from realty_radar.infrastructure.database.models.v2 import GEOCODE_STATUS_OK
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.main import app


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


def test_search_result_shows_location_pending_without_a_verified_coordinate(monkeypatch):
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
    assert "위치 확인 중" in response.text
