from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
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
from realty_radar.web.routes.home import _filter_query_items, _region_options, parse_search_filter


def _render_home_with_memory_db(query: str):
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
        return TestClient(app).get(query)
    finally:
        app.dependency_overrides.clear()


def test_detailed_filter_groups_budget_and_progressive_housing_controls():
    response = _render_home_with_memory_db(
        "/?trade_types=SALE&min_price_eok=2&max_price_eok=6&min_households=500"
    )

    assert response.status_code == 200
    assert 'data-filter-scope="housing-budget"' in response.text
    assert 'data-filter-scope="housing-core"' in response.text
    assert 'data-filter-scope="housing-detail"' in response.text
    assert 'data-slider-name="min_price_eok"' in response.text
    assert 'data-slider-name="max_price_eok"' in response.text
    assert 'data-slider-name="min_exclusive_area"' in response.text
    assert 'data-slider-name="max_exclusive_area"' in response.text
    assert 'name="min_construction_year"' in response.text
    assert 'name="max_subway_walk_minutes"' in response.text
    assert 'data-slider-variant="embedded"' in response.text


def test_listing_cards_link_to_fin_land_article_pages():
    template = Path("src/realty_radar/web/templates/listings/_listing_cards.html").read_text(encoding="utf-8")

    assert 'href="https://fin.land.naver.com/articles/{{ item.article_id }}"' in template


def test_favorite_buttons_keep_listing_payloads_without_complex_favorites():
    cards = Path("src/realty_radar/web/templates/listings/_listing_cards.html").read_text(encoding="utf-8")
    partial = Path("src/realty_radar/web/templates/listings/list_partial.html").read_text(encoding="utf-8")
    index = Path("src/realty_radar/web/templates/listings/index.html").read_text(encoding="utf-8")

    assert "favorite_payload | tojson" in cards
    assert "toggleComplexFavorite" not in cards
    assert "favorite_complex_payloads" not in partial
    assert "STORAGE_KEY_COMPLEXES" not in index
    assert "{{ item | tojson }}" not in cards


def test_settings_url_redirects_to_search_and_header_has_no_settings_link():
    response = TestClient(app).get("/settings", follow_redirects=False)
    base = Path("src/realty_radar/web/templates/base.html").read_text(encoding="utf-8")

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert 'href="/settings"' not in base


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


def test_search_filter_parses_extended_listing_controls_and_saved_settings_values():
    filters = parse_search_filter(
        direct_trade_only=True,
        safe_lessor_hug_only=True,
        min_room_count="3",
        min_bathroom_count="2",
        parking_possible_only=True,
        min_parking_per_household="1.25",
        max_monthly_management_cost="180000",
        move_in_by="2026-08-31",
        max_subway_walk_minutes="8",
    )
    assert filters.direct_trade_only is True
    assert filters.safe_lessor_hug_only is True
    assert filters.min_room_count == 3
    assert filters.min_bathroom_count == 2
    assert filters.parking_possible_only is True
    assert str(filters.min_parking_per_household) == "1.25"
    assert filters.max_monthly_management_cost == 180000
    assert str(filters.move_in_by) == "2026-08-31"
    assert filters.max_subway_walk_minutes == 8

    restored = type(filters).from_dict(filters.to_dict())
    assert restored == filters


def test_search_filter_parses_purchase_affordability_control_and_round_trips():
    filters = parse_search_filter(only_purchase_affordable=True)

    assert filters.only_purchase_affordable is True
    assert type(filters).from_dict(filters.to_dict()) == filters


def test_purchase_affordability_control_survives_pagination_query_building():
    query_items = _filter_query_items(parse_search_filter(only_purchase_affordable=True))

    assert ("only_purchase_affordable", "true") in query_items


def test_recent_preset_wins_when_a_no_javascript_form_submits_both_values():
    filters = parse_search_filter(recent_days="7", recent_days_custom="12")

    assert filters.recent_days == 7


def test_municipality_query_expands_suwon_to_all_child_districts_and_round_trips_saved_filter():
    filters = parse_search_filter(sido_code="41", municipality="수원시")

    assert filters.sido_code == 41
    assert filters.sigungu_code is None
    assert filters.sigungu_codes == [41111, 41113, 41115, 41117]
    assert type(filters).from_dict(filters.to_dict()) == filters


def test_region_options_split_gyeonggi_municipalities_from_child_districts():
    gyeonggi = next(region for region in _region_options() if region["code"] == 41)
    suwon = next(item for item in gyeonggi["municipalities"] if item["name"] == "수원시")
    bucheon = next(item for item in gyeonggi["municipalities"] if item["name"] == "부천시")

    assert [district["name"] for district in suwon["districts"]] == ["영통구", "장안구", "팔달구", "권선구"]
    assert [district["code"] for district in suwon["districts"]] == [41111, 41113, 41115, 41117]
    assert [district["name"] for district in bucheon["districts"]] == ["원미구", "소사구", "오정구"]
    assert bucheon["codes"] == [41192, 41194, 41196]


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
        "가격 500원 ~ 전체",
        "월세 상한 100원",
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
        "가능 대출 있는 매물만",
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
    assert htmx_response.status_code == 200
    assert "검색 조건을 확인" in response.text
    assert 'id="listing-search-form"' in response.text
    assert 'id="search-results"' in htmx_response.text
    assert htmx_response.headers["HX-Retarget"] == "#search-results"
    assert htmx_response.headers["HX-Reswap"] == "outerHTML"


def test_unrelated_value_errors_are_not_converted_to_client_filter_errors(monkeypatch):
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

    def raise_unrelated_value_error(*args, **kwargs):
        raise ValueError("unexpected application failure")

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(ListingSearchService, "search_listings", raise_unrelated_value_error)
    try:
        with pytest.raises(ValueError, match="unexpected application failure"):
            TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()


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


def test_city_wide_region_chip_and_unknown_municipality_error_are_human_readable():
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
        city_response = TestClient(app).get("/?sido_code=41&municipality=수원시")
        invalid_response = TestClient(app).get("/?sido_code=41&municipality=없는시")
    finally:
        app.dependency_overrides.clear()

    assert city_response.status_code == 200
    assert "시군구 수원시 전체" in city_response.text
    assert invalid_response.status_code == 400


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
    assert "id=\"sido-select\"" in response.text
    assert "id=\"district-select\"" in response.text
    assert "hx-sync=\"this:replace\"" in response.text
    assert "delay:400ms" in response.text
    assert append_response.status_code == 200
    assert "hx-swap-oob=\"true\"" in append_response.text


def test_home_uses_three_level_region_selectors_and_drag_only_numeric_filters():
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
        response = TestClient(app).get("/?min_price=600000000&max_monthly_rent=1200000&min_households=1200")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'id="municipality-select"' in response.text
    assert 'id="district-select"' in response.text
    assert 'data-range-slider="price"' in response.text
    assert 'data-range-slider="exclusive-area"' in response.text
    assert response.text.count('type="range"') >= 12
    for name in (
        "min_price_eok",
        "max_price_eok",
        "max_monthly_rent",
        "min_exclusive_area",
        "max_exclusive_area",
        "min_room_count",
        "min_bathroom_count",
        "min_parking_per_household",
        "max_monthly_management_cost",
        "max_subway_walk_minutes",
        "min_construction_year",
        "min_households",
        "recent_days",
    ):
        assert f'type="hidden" name="{name}"' in response.text
        assert f'data-slider-name="{name}"' in response.text
    assert 'name="min_room_count" inputmode=' not in response.text


def test_home_slider_script_handles_an_unselected_municipality_without_stopping_initialization():
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
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'JSON.parse(district.dataset.selectedCodes || "[]") || []' in response.text
    assert 'document.querySelectorAll("[data-single-slider]")' in response.text


def test_trade_specific_filters_are_collapsible_and_marked_for_dynamic_visibility():
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
        response = TestClient(app).get("/?trade_types=SALE")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'id="transaction-advanced-filters"' in response.text
    assert 'data-price-label' in response.text
    assert 'data-monthly-rent-filter' in response.text
    assert 'data-trade-filter' in response.text
    assert 'updateTradeFilters' in response.text
    assert 'addEventListener("change", updateTradeFilters, true)' in response.text


def test_price_slider_is_capped_at_thirty_eok_while_other_bounds_expand():
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
        response = TestClient(app).get("/?min_price=60000000000&min_exclusive_area=620&recent_days=500")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'id="min-price-eok" type="range" min="0" max="30"' in response.text
    assert 'id="min-exclusive-area" type="range" min="0" max="620"' in response.text
    assert 'id="recent-days" type="range" min="1" max="500"' in response.text


def test_htmx_page_navigation_replaces_the_search_results():
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
        next_url = unescape(
            re.search(r'<a[^>]+hx-get="([^"]+)"[^>]*>다음 페이지</a>', first.text).group(1)
        )
        second_page = client.get(next_url, headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert "첫번째 단지" in first.text
    assert "append=1" not in next_url
    assert 'hx-target="#search-results" hx-swap="outerHTML" hx-push-url="true">다음 페이지' in first.text
    assert second_page.status_code == 200
    assert "두번째 단지" in second_page.text
    assert "첫번째 단지" not in second_page.text
    assert 'id="search-results"' in second_page.text


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


def test_http_search_logs_timing_diagnostics(caplog):
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
    caplog.set_level(20, logger="realty_radar.web.routes.home")
    try:
        response = TestClient(app).get("/listings/search", headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.clear()

    telemetry = [
        record.getMessage()
        for record in caplog.records
        if record.name == "realty_radar.web.routes.home"
        and record.getMessage().startswith("listing_search ")
    ]
    assert response.status_code == 200
    assert len(telemetry) == 1
    assert re.search(
        r"^listing_search mode=normal sql_count=1 candidate_count=0 "
        r"db_ms=\d+\.\d{3} loan_ms=\d+\.\d{3} total_ms=\d+\.\d{3}$",
        telemetry[0],
    )


def test_search_filter_converts_eok_price_inputs_without_overriding_canonical_prices():
    eok_filters = parse_search_filter(min_price_eok="5.25", max_price_eok="12")
    canonical_filters = parse_search_filter(
        min_price="610000000",
        max_price="990000000",
        min_price_eok="5.25",
        max_price_eok="12",
    )
    empty_canonical_filters = parse_search_filter(min_price="", max_price="not-a-number", min_price_eok="5.25", max_price_eok="12")
    invalid_filters = parse_search_filter(min_price_eok="five", max_price_eok="")

    assert eok_filters.min_price == 525_000_000
    assert eok_filters.max_price == 1_200_000_000
    assert canonical_filters.min_price == 610_000_000
    assert canonical_filters.max_price == 990_000_000
    assert empty_canonical_filters.min_price is None
    assert empty_canonical_filters.max_price is None
    assert invalid_filters.min_price is None
    assert invalid_filters.max_price is None


def test_home_renders_mobile_filter_groups_and_dynamic_region_controls():
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
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    for text in ("기본 검색", "주거 조건", "고급 조건", "아파트 매물 검색"):
        assert text in response.text
    for field in (
        "min_price_eok",
        "max_price_eok",
        "min_exclusive_area",
        "max_exclusive_area",
        "direct_trade_only",
        "safe_lessor_hug_only",
        "min_room_count",
        "min_bathroom_count",
        "parking_possible_only",
        "min_parking_per_household",
        "max_monthly_management_cost",
        "move_in_by",
        "max_subway_walk_minutes",
    ):
        assert f'name="{field}"' in response.text
    assert 'id="sido-select"' in response.text
    assert 'id="municipality-select"' in response.text
    assert 'id="district-select"' in response.text
    assert "min-h-11" in response.text
    assert "overflow-x-auto" in response.text
    assert "59㎡" in response.text
    assert "84㎡" in response.text
    assert 'data-price-range=";6"' in response.text
    assert 'data-price-range="6;9"' in response.text
    assert 'data-price-range="9;"' in response.text
    assert 'data-range-pyeong="min"' in response.text
    assert 'data-range-pyeong="max"' in response.text
    assert "formatPyeong" in response.text
    assert "region?.municipalities" in response.text
    assert "district.replaceChildren" in response.text
    assert "populateDistricts" in response.text
    assert '<option value="11680"' not in response.text
    assert 'hx-trigger="submit, change delay:400ms, keyup changed delay:400ms"' in response.text


def test_result_header_owns_sort_control_and_advanced_conditions_contain_housing_controls():
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
        response = TestClient(app).get("/?sort_by=area_desc&min_room_count=3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'data-result-sort form="listing-search-form" name="sort_by"' in response.text
    assert 'id="advanced-housing-conditions"' in response.text
    assert re.search(r'<details[^>]*>.*id="advanced-housing-conditions".*</details>', response.text, re.DOTALL)
    assert 'addEventListener("change", (event) => {' in response.text


def test_listing_card_shows_populated_detail_fields_without_absent_detail_placeholders():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    seen_at = datetime(2026, 7, 26, tzinfo=timezone.utc)
    with factory() as session:
        session.add(
            ComplexCurrent(
                complex_id=40,
                region_code=1150010200,
                name="상세 단지",
                normalized_name="상세단지",
                address="서울 테스트로 1",
                state_hash=b"c" * 16,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                updated_at=seen_at,
            )
        )
        session.add_all(
            [
                ListingCurrent(
                    article_id=41,
                    complex_id=40,
                    region_code=1150010200,
                    complex_name="상세 단지",
                    address="서울 테스트로 1",
                    trade_type=1,
                    primary_price=500_000_000,
                    exclusive_area_x100=8400,
                    room_count=3,
                    bathroom_count=2,
                    parking_possible=False,
                    parking_per_household_x100=125,
                    monthly_management_cost=180000,
                    move_in_available_on=date(2026, 8, 1),
                    nearest_subway_walk_minutes=7,
                    is_direct_trade=True,
                    is_safe_lessor_hug=True,
                    state_hash=b"a" * 16,
                    last_seen_job_id=1,
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    last_changed_at=seen_at,
                ),
                ListingCurrent(
                    article_id=42,
                    complex_id=40,
                    region_code=1150010200,
                    complex_name="상세 없는 단지",
                    address="서울 테스트로 2",
                    trade_type=1,
                    primary_price=600_000_000,
                    state_hash=b"b" * 16,
                    last_seen_job_id=1,
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    last_changed_at=seen_at,
                ),
            ]
        )
        session.commit()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    for text in ("방 3", "욕실 2", "주차 불가", "1.25대/세대", "관리비 180,000원", "입주 2026-08-01", "역 도보 7분"):
        assert text in response.text
    assert response.text.index("5억 원") < response.text.index("상세 단지")
    assert "방 -" not in response.text
