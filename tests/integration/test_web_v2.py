from datetime import datetime, timezone
from html import unescape
import re

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models import Base, ComplexCurrent, ListingCurrent
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.main import app
from realty_radar.web.routes.home import parse_search_filter


def test_search_filter_parses_all_apartment_search_controls_and_legacy_deposit_aliases():
    filters = parse_search_filter(
        region_code="1168000010",
        sido_code="11",
        sigungu_code="11680",
        complex_keyword="래미안",
        trade_types=["SALE", "JEONSE", "MONTHLY_RENT", "SHORT_TERM"],
        min_deposit="500000000",
        max_deposit="900000000",
        max_monthly_rent="1500000",
        min_exclusive_area="59.84",
        max_exclusive_area="84.99",
        min_construction_year="2010",
        min_households="500",
        recent_days="7",
        recent_days_custom="12",
        mortgage_codes=["0", "1", "2"],
        exclude_unknown_mortgage=True,
        direction_codes=["1", "2", "8"],
        floor_bands=["1", "4", "5"],
        exclude_first_floor=True,
        exclude_short_term=False,
        group_by_complex=True,
        only_eligible_loans=True,
        sort_by="households_asc",
        page_size=40,
    )

    assert filters.region_code == 1168000010
    assert filters.sido_code == 11
    assert filters.sigungu_code == 11680
    assert filters.complex_keyword == "래미안"
    assert filters.trade_types == [1, 2, 3, 4]
    assert filters.min_price == 500000000
    assert filters.max_price == 900000000
    assert filters.max_monthly_rent == 1500000
    assert str(filters.min_exclusive_area) == "59.84"
    assert str(filters.max_exclusive_area) == "84.99"
    assert filters.min_construction_year == 2010
    assert filters.min_households == 500
    assert filters.recent_days == 12
    assert filters.mortgage_codes == [0, 1, 2]
    assert filters.exclude_unknown_mortgage is True
    assert filters.direction_codes == [1, 2, 8]
    assert filters.floor_bands == [1, 4, 5]
    assert filters.exclude_first_floor is True
    assert filters.exclude_short_term is False
    assert filters.group_by_complex is True
    assert filters.only_eligible_loans is True
    assert filters.sort_by == "households_asc"
    assert filters.page_size == 40


def test_search_filter_prefers_primary_price_and_accepts_singular_legacy_trade():
    filters = parse_search_filter(
        transaction_type="SALE",
        min_price="600000000",
        min_deposit="500000000",
        max_deposit="900000000",
    )

    assert filters.trade_types == [1]
    assert filters.min_price == 600000000
    assert filters.max_price == 900000000


def test_home_exposes_hierarchical_auto_search_and_append_pager_contract():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/")
        append_response = TestClient(app).get("/listings/search?append=1", headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "아파트 매물 검색" in response.text
    assert "name=\"sido_code\"" in response.text
    assert "name=\"sigungu_code\"" in response.text
    assert "hx-sync=\"this:replace\"" in response.text
    assert "delay:400ms" in response.text
    assert append_response.status_code == 200
    assert "hx-swap-oob=\"true\"" in append_response.text


def test_htmx_load_more_appends_cards_and_replaces_only_the_pager():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    seen_at = datetime(2026, 7, 26, tzinfo=timezone.utc)
    with factory() as session:
        for complex_id, article_id, name in ((1, 11, "첫번째 단지"), (2, 12, "두번째 단지")):
            session.add(
                ComplexCurrent(
                    complex_id=complex_id,
                    region_code=1150010200,
                    name=name,
                    normalized_name=name.replace(" ", ""),
                    address="서울시 테스트로 1",
                    state_hash=bytes([complex_id]) * 16,
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    updated_at=seen_at,
                )
            )
            session.add(
                ListingCurrent(
                    article_id=article_id,
                    complex_id=complex_id,
                    region_code=1150010200,
                    complex_name=name,
                    address="서울시 테스트로 1",
                    trade_type=1,
                    primary_price=500_000_000 + article_id,
                    state_hash=bytes([article_id]) * 16,
                    last_seen_job_id=1,
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    last_changed_at=seen_at,
                )
            )
        session.commit()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        first = client.get("/listings/search?page_size=1", headers={"HX-Request": "true"})
        next_url = unescape(re.search(r'hx-get="([^"]+)"', first.text).group(1))
        appended = client.get(next_url, headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert "첫번째 단지" in first.text
    assert "append=1" in next_url
    assert appended.status_code == 200
    assert "두번째 단지" in appended.text
    assert 'id="search-results"' not in appended.text
    assert 'id="listing-pager" hx-swap-oob="true"' in appended.text


def test_home_renders_v2_cursor_search_without_a_database_count_query():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/?sigungu_code=11500&sort_by=price_asc")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "cursor 조회" in response.text
