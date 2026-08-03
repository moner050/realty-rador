from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models import Base, ComplexCurrent, ListingCurrent
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    now = datetime(2026, 8, 3, tzinfo=timezone.utc)
    with factory() as session:
        session.add(
            ComplexCurrent(
                complex_id=1001,
                region_code=1150010200,
                name="테스트 단지",
                normalized_name="테스트단지",
                address="서울특별시 강서구 테스트로 1",
                household_count=500,
                state_hash=b"c" * 16,
                first_seen_at=now,
                last_seen_at=now,
                updated_at=now,
            )
        )
        session.add(
            ListingCurrent(
                article_id=2001,
                complex_id=1001,
                region_code=1150010200,
                complex_name="테스트 단지",
                address="서울특별시 강서구 테스트로 1",
                household_count=500,
                trade_type=1,
                primary_price=500_000_000,
                exclusive_area_x100=8400,
                monthly_management_cost=180_000,
                state_hash=b"l" * 16,
                last_seen_job_id=1,
                first_seen_at=now,
                last_seen_at=now,
                last_changed_at=now,
            )
        )
        session.commit()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_sale_card_shows_purchase_affordability_breakdown_and_disclaimer(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "예상 필요 현금" in response.text
    assert "선택 정책대출" in response.text
    assert "부대비용 예비비" in response.text
    assert "월 총주거비" in response.text
    assert "정책대출 기준 예상치" in response.text


def test_htmx_purchase_filter_without_limits_returns_settings_error(client):
    response = client.get("/listings/search?only_purchase_affordable=true", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "#search-results"
    assert "구매 투입 가능 현금과 월 총주거비를 먼저 설정" in response.text
