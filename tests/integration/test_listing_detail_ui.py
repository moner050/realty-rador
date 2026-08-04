from datetime import date, datetime, timezone
from html import unescape
import re

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.infrastructure.database.models import Base, ComplexCurrent, ListingCurrent
from realty_radar.infrastructure.database.session import get_db
from realty_radar.web.auth import SESSION_COOKIE_NAME
from realty_radar.web.main import app
from realty_radar.web.routes import home as home_routes


def test_listing_card_distinguishes_detail_states_before_and_after_collection():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    seen_at = datetime(2026, 8, 4, tzinfo=timezone.utc)
    with factory() as session:
        for article_id, checked_at in ((71, None), (72, seen_at)):
            session.add(
                ListingCurrent(
                    article_id=article_id,
                    complex_id=article_id,
                    region_code=1150010200,
                    complex_name=f"detail-state-{article_id}",
                    address="Seoul test street 1",
                    trade_type=1,
                    primary_price=500_000_000,
                    detail_checked_at=checked_at,
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
        response = TestClient(app).get("/?group_by_complex=false")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    unchecked_html, checked_html = response.text.split('data-article-id="72"')
    assert unchecked_html.count("\uc8fc\ucc28 \ud655\uc778 \ub300\uae30") == 2
    assert unchecked_html.count("\uad00\ub9ac\ube44 \ud655\uc778 \ub300\uae30") == 2
    assert unchecked_html.count("\uc5ed \ub3c4\ubcf4 \ud655\uc778 \ub300\uae30") == 2
    assert checked_html.count("\uc8fc\ucc28 \uc6d0\ubcf8 \ubbf8\uc81c\uacf5") == 2
    assert checked_html.count("\uad00\ub9ac\ube44 \uc6d0\ubcf8 \ubbf8\uc81c\uacf5") == 2
    assert checked_html.count("\uc5ed \ub3c4\ubcf4 \uc6d0\ubcf8 \ubbf8\uc81c\uacf5") == 2


def test_grouped_search_lazy_loads_twenty_complex_listings_without_initial_cards():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    seen_at = datetime(2026, 7, 26, tzinfo=timezone.utc)
    with factory() as session:
        session.add(
            ComplexCurrent(
                complex_id=51,
                region_code=1150010200,
                name="모달 단지",
                normalized_name="모달단지",
                address="서울 테스트로 1",
                state_hash=b"m" * 16,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                updated_at=seen_at,
            )
        )
        for offset in range(41):
            session.add(
                ListingCurrent(
                    article_id=52 + offset,
                    complex_id=51,
                    region_code=1150010200,
                    complex_name="모달 단지",
                    address="서울 테스트로 1",
                    trade_type=1,
                    primary_price=500_000_000 + offset,
                    exclusive_area_x100=8400,
                    room_count=3,
                    bathroom_count=2,
                    parking_possible=True,
                    parking_per_household_x100=125,
                    monthly_management_cost=180000,
                    move_in_available_on=date(2026, 8, 1),
                    nearest_subway_walk_minutes=7,
                    state_hash=bytes([offset]) * 16,
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
        response = client.get("/?group_by_complex=true&min_price=500000001")
        first_url_match = re.search(r'hx-get="([^"]*/listings/complex/51[^"]*)"', response.text)
        assert first_url_match is not None
        first = client.get(unescape(first_url_match.group(1)), headers={"HX-Request": "true"})
        next_url_match = re.search(r'data-complex-more[^>]*hx-get="([^"]+)"', first.text)
        assert next_url_match is not None
        second = client.get(unescape(next_url_match.group(1)), headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(response.content) < 1_000_000
    assert '<details class="complex-group' in response.text
    assert '<details class="complex-group open' not in response.text
    assert 'hx-trigger="toggle once"' in response.text
    assert 'id="listing-detail-' not in response.text
    assert "fin.land.naver.com/articles/" not in response.text
    assert first.status_code == 200
    assert first.text.count('id="listing-detail-') == 20
    assert 'href="https://fin.land.naver.com/articles/53"' in first.text
    assert 'href="https://fin.land.naver.com/articles/52"' not in first.text
    assert "디딤돌" in first.text
    assert 'data-complex-more' in first.text
    assert 'hx-target="this"' in first.text
    assert 'hx-swap="outerHTML"' in first.text
    assert second.status_code == 200
    assert second.text.count('id="listing-detail-') == 20
    assert 'href="https://fin.land.naver.com/articles/73"' in second.text
    assert 'href="https://fin.land.naver.com/articles/53"' not in second.text
    assert "개인 자격 및 정책대출 조건 설정" in response.text
    assert 'text-sky-300' in response.text
    assert 'text-amber-300' in response.text


def test_saved_group_filters_are_encoded_into_bare_home_lazy_urls(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    seen_at = datetime(2026, 7, 26, tzinfo=timezone.utc)
    with factory() as session:
        session.add(
            ComplexCurrent(
                complex_id=61,
                region_code=1150010200,
                name="저장 필터 단지",
                normalized_name="저장필터단지",
                address="서울 테스트로 1",
                state_hash=b"s" * 16,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                updated_at=seen_at,
            )
        )
        for article_id, price in ((62, 300_000_000), (63, 7_000_000_000)):
            session.add(
                ListingCurrent(
                    article_id=article_id,
                    complex_id=61,
                    region_code=1150010200,
                    complex_name="저장 필터 단지",
                    address="서울 테스트로 1",
                    trade_type=1,
                    primary_price=price,
                    exclusive_area_x100=8400,
                    state_hash=bytes([article_id]) * 16,
                    last_seen_job_id=1,
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    last_changed_at=seen_at,
                )
            )
        session.commit()

    saved_filters = ListingSearchFilter(
        group_by_complex=True,
        only_eligible_loans=True,
        min_price=250_000_000,
    )
    monkeypatch.setattr(home_routes, "verify_session_token", lambda _token: "saved-user")
    monkeypatch.setattr(home_routes, "load_user_search_filter", lambda _username: saved_filters)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app, cookies={SESSION_COOKIE_NAME: "signed-session"})
        response = client.get("/")
        url_match = re.search(r'hx-get="([^"]*/listings/complex/61[^"]*)"', response.text)
        assert url_match is not None
        lazy_url = unescape(url_match.group(1))
        partial = client.get(lazy_url, headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.clear()

    assert "only_eligible_loans=true" in lazy_url
    assert "min_price=250000000" in lazy_url
    assert partial.status_code == 200
    assert 'articles/62"' in partial.text
    assert 'articles/63"' not in partial.text


def test_inline_profile_save_sets_guest_profile_cookie_for_search_refresh():
    response = TestClient(app).post(
        "/settings/inline",
        data={
            "is_homeless": "true",
            "annual_income": "40000000",
            "net_assets": "200000000",
            "child_count": "1",
        },
    )

    assert response.status_code == 204
    assert "realty_guest_profile=" in response.headers["set-cookie"]
    assert response.headers["HX-Refresh"] == "true"


def test_search_page_renders_promissory_note_entries_for_inline_profile_modal():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app, raise_server_exceptions=False)
        saved = client.post(
            "/settings/inline",
            data={
                "is_homeless": "true",
                "use_promissory_note": "true",
                "promissory_note_names": "Family note",
                "promissory_note_amounts": "1000000",
            },
        )
        response = client.get("/")
    finally:
        app.dependency_overrides.clear()

    assert saved.status_code == 204
    assert response.status_code == 200
    assert '"name": "Family note"' in response.text


def test_inline_settings_modal_is_teleported_out_of_the_sticky_sidebar():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert '<template x-teleport="body">' in response.text


def test_search_layout_widens_the_results_pane_and_colours_property_facts():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'class="mx-auto grid w-full max-w-7xl gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]"' in response.text


def test_search_results_render_a_fixed_filter_and_pagination_control_bar():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'data-result-controls' in response.text
    assert 'sticky top-20 z-30' in response.text
    assert '>필터 변경</a>' in response.text
    assert '페이지당 20개' in response.text
