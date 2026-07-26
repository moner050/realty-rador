from datetime import datetime, timezone
from html import unescape
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models import Base, ComplexCurrent, ListingCurrent
from realty_radar.infrastructure.database.session import get_db
from realty_radar.application.listing_search_service import ListingSearchService
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
        recent_days="",
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


def test_recent_preset_wins_when_a_no_javascript_form_submits_both_values():
    filters = parse_search_filter(recent_days="7", recent_days_custom="12")

    assert filters.recent_days == 7


def test_short_term_trade_selection_includes_short_term_rows_despite_default_exclusion():
    filters = parse_search_filter(trade_types=["SHORT_TERM"], exclude_short_term=True)

    assert filters.exclude_short_term is False

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    seen_at = datetime(2026, 7, 26, tzinfo=timezone.utc)
    session.add(
        ComplexCurrent(
            complex_id=30,
            region_code=1150010200,
            name="단기 단지",
            normalized_name="단기단지",
            address="서울시 테스트로 1",
            state_hash=b"c" * 16,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            updated_at=seen_at,
        )
    )
    session.add(
        ListingCurrent(
            article_id=31,
            complex_id=30,
            region_code=1150010200,
            complex_name="단기 단지",
            address="서울시 테스트로 1",
            trade_type=4,
            primary_price=100_000_000,
            is_short_term=True,
            state_hash=b"l" * 16,
            last_seen_job_id=1,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            last_changed_at=seen_at,
        )
    )
    session.commit()

    result = ListingSearchService(session).search_listings(filters)

    assert [item.article_id for item in result.items] == [31]


def test_active_filter_chips_describe_every_applied_search_condition():
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
        response = TestClient(app).get(
            "/?trade_types=SALE&trade_types=MONTHLY_RENT&min_price=500&max_monthly_rent=100&"
            "min_exclusive_area=59&max_exclusive_area=84&min_construction_year=2010&min_households=500&"
            "recent_days=7&mortgage_codes=1&direction_codes=1&floor_bands=3&exclude_first_floor=true&"
            "exclude_short_term=false&group_by_complex=true&only_eligible_loans=true&sort_by=area_desc"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    for label in (
        "거래 매매·월세",
        "가격 500 ~ 전체",
        "월세 상한 100",
        "전용 59㎡ ~ 84㎡",
        "준공 2010년 이후",
        "500세대 이상",
        "최근 7일",
        "융자 없음",
        "방향 남",
        "층 고층",
        "1층 제외",
        "단기임대 포함",
        "단지별 묶기",
        "대출 적격",
        "전용면적 넓은순",
    ):
        assert label in response.text


@pytest.mark.parametrize("query", ("cursor=x", "sort_by=not-a-sort", "complex_keyword=가"))
def test_invalid_search_queries_render_a_client_error_instead_of_a_server_error(query):
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
        response = TestClient(app).get(f"/?{query}")
        htmx_response = TestClient(app).get(f"/listings/search?{query}", headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert htmx_response.status_code == 400
    assert "검색 조건을 확인" in response.text
    assert 'id="search-results"' in htmx_response.text


def test_active_region_chips_use_human_readable_sido_and_sigungu_names():
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
        response = TestClient(app).get("/?sido_code=11&sigungu_code=11680")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "시도 서울특별시" in response.text
    assert "시군구 강남구" in response.text


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
