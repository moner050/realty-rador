import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.domain.listing.filters import ListingSearchFilter, ListingSearchValidationError
from realty_radar.domain.loan.entities import ApplicantProfile
from realty_radar.infrastructure.database.models import Base, ComplexCurrent, ListingCurrent
from realty_radar.infrastructure.database.models.v2 import GEOCODE_STATUS_OK


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(session):
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    for complex_id, name, households in ((1001, "래미안 테스트", 1200), (1002, "푸르지오 테스트", 800)):
        session.add(
            ComplexCurrent(
                complex_id=complex_id,
                region_code=1150010200,
                name=name,
                normalized_name=name.replace(" ", ""),
                address="서울특별시 강서구 테스트로 1",
                household_count=households,
                state_hash=bytes([complex_id % 256]) * 16,
                first_seen_at=now,
                last_seen_at=now,
                updated_at=now,
            )
        )
    prices = (500_000_000, 550_000_000, 600_000_000, 650_000_000)
    for offset, price in enumerate(prices):
        session.add(
            ListingCurrent(
                article_id=2001 + offset,
                complex_id=1001 if offset < 2 else 1002,
                region_code=1150010200,
                complex_name="래미안 테스트" if offset < 2 else "푸르지오 테스트",
                address="서울특별시 강서구 테스트로 1",
                household_count=1200 if offset < 2 else 800,
                trade_type=1,
                primary_price=price,
                exclusive_area_x100=8497,
                state_hash=bytes([offset]) * 16,
                last_seen_job_id=1,
                first_seen_at=now + timedelta(seconds=offset),
                last_seen_at=now,
                last_changed_at=now,
            )
        )
    session.commit()


def test_mysql_boolean_filters_compile_as_indexable_equalities():
    session = _session()
    statement = ListingSearchService(session)._filtered_rows(
        ListingSearchFilter(
            direct_trade_only=True,
            safe_lessor_hug_only=True,
            parking_possible_only=True,
        )
    )

    sql = str(
        statement.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "listing_current.is_short_term = false" in sql
    assert "listing_current.is_direct_trade = true" in sql
    assert "listing_current.is_safe_lessor_hug = true" in sql
    assert "listing_current.parking_possible = true" in sql
    assert " is false" not in sql
    assert " is true" not in sql


def test_price_keyset_cursor_has_no_duplicates_or_count_query():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")
    filters = ListingSearchFilter(sigungu_code=11500, sort_by="price_asc", page_size=2)

    first = service.search_listings(filters)
    second = service.search_listings(ListingSearchFilter(sigungu_code=11500, sort_by="price_asc", page_size=2, cursor=first.next_cursor))

    assert [item.article_id for item in first.items + second.items] == [2001, 2002, 2003, 2004]
    assert first.has_more is True
    assert second.has_more is False
    assert not hasattr(first, "total_count")


def test_normal_search_result_reports_query_diagnostics():
    session = _session()
    _seed(session)

    result = ListingSearchService(session, cursor_secret="test-secret").search_listings(
        ListingSearchFilter(sort_by="price_asc", page_size=2)
    )

    assert result.diagnostics.mode == "normal"
    assert result.diagnostics.sql_count == 1
    assert result.diagnostics.candidate_count == 0
    assert result.diagnostics.db_time_ms > 0
    assert result.diagnostics.loan_evaluation_time_ms == 0
    assert result.diagnostics.total_time_ms >= result.diagnostics.db_time_ms


def test_keyset_page_can_return_to_the_immediately_previous_page():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")
    filters = ListingSearchFilter(sort_by="price_asc", page_size=1)

    first = service.search_listings(filters)
    second = service.search_listings(ListingSearchFilter(sort_by="price_asc", page_size=1, cursor=first.next_cursor))
    third = service.search_listings(ListingSearchFilter(sort_by="price_asc", page_size=1, cursor=second.next_cursor))

    assert third.has_previous is True
    assert third.previous_cursor is not None
    previous = service.search_listings(
        ListingSearchFilter(sort_by="price_asc", page_size=1, cursor=third.previous_cursor)
    )
    assert [item.article_id for item in previous.items] == [2002]


def test_cursor_cannot_be_reused_with_different_filters():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")
    first = service.search_listings(ListingSearchFilter(sort_by="price_asc", page_size=1))

    with pytest.raises(ValueError, match="cursor"):
        service.search_listings(
            ListingSearchFilter(trade_type=2, sort_by="price_asc", page_size=1, cursor=first.next_cursor)
        )


def test_map_bounds_include_edges_but_exclude_unverified_and_outside_listings():
    session = _session()
    _seed(session)
    complexes = {row.complex_id: row for row in session.query(ComplexCurrent).all()}
    complexes[1001].latitude = Decimal("37.5000000")
    complexes[1001].longitude = Decimal("126.8000000")
    complexes[1001].geocode_status = GEOCODE_STATUS_OK
    complexes[1002].latitude = Decimal("37.5000000")
    complexes[1002].longitude = Decimal("126.8000000")
    complexes[1002].geocode_status = 0
    session.add(
        ComplexCurrent(
            complex_id=1003,
            region_code=1150010200,
            name="지도 밖 테스트",
            normalized_name="지도밖테스트",
            address="서울특별시 강서구 테스트로 3",
            latitude=Decimal("37.6000000"),
            longitude=Decimal("126.9000000"),
            geocode_status=GEOCODE_STATUS_OK,
            state_hash=b"o" * 16,
            first_seen_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            last_seen_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            updated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )
    )
    session.add(
        ListingCurrent(
            article_id=2005,
            complex_id=1003,
            region_code=1150010200,
            complex_name="지도 밖 테스트",
            address="서울특별시 강서구 테스트로 3",
            trade_type=1,
            primary_price=700_000_000,
            state_hash=b"o" * 16,
            last_seen_job_id=1,
            first_seen_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            last_seen_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            last_changed_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )
    )
    session.commit()

    result = ListingSearchService(session, cursor_secret="test-secret").search_listings(
        ListingSearchFilter(
            map_west=Decimal("126.8000000"),
            map_south=Decimal("37.5000000"),
            map_east=Decimal("126.8500000"),
            map_north=Decimal("37.5500000"),
        )
    )

    assert [row.article_id for row in result.items] == [2001, 2002]


def test_map_bounds_change_the_cursor_fingerprint_but_are_not_persisted():
    session = _session()
    _seed(session)
    for complex in session.query(ComplexCurrent).all():
        complex.latitude = Decimal("37.5000000")
        complex.longitude = Decimal("126.8000000")
        complex.geocode_status = GEOCODE_STATUS_OK
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")
    first = service.search_listings(
        ListingSearchFilter(
            map_west=Decimal("126.7900000"),
            map_south=Decimal("37.4900000"),
            map_east=Decimal("126.8500000"),
            map_north=Decimal("37.5500000"),
            page_size=1,
        )
    )

    assert first.next_cursor is not None
    assert "map_west" not in ListingSearchFilter(
        map_west=Decimal("126.7900000"),
        map_south=Decimal("37.4900000"),
        map_east=Decimal("126.8500000"),
        map_north=Decimal("37.5500000"),
    ).to_dict()
    with pytest.raises(ValueError, match="cursor"):
        service.search_listings(
            ListingSearchFilter(
                map_west=Decimal("126.7900000"),
                map_south=Decimal("37.4900000"),
                map_east=Decimal("126.8600000"),
                map_north=Decimal("37.5500000"),
                page_size=1,
                cursor=first.next_cursor,
            )
        )


def test_cursor_has_a_version_and_rejects_legacy_payloads():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")
    filters = ListingSearchFilter(sort_by="price_asc", page_size=1)
    first = service.search_listings(filters)
    raw_encoded, _signature = first.next_cursor.split(".", 1)
    payload = json.loads(service._unb64(raw_encoded))

    assert payload["v"] == 2

    payload.pop("v")
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(b"test-secret", raw, hashlib.sha256).digest()
    legacy_cursor = f"{service._b64(raw)}.{service._b64(signature)}"

    with pytest.raises(ValueError, match="version"):
        service.search_listings(
            ListingSearchFilter(sort_by="price_asc", page_size=1, cursor=legacy_cursor)
        )


def test_signed_cursor_with_non_object_payload_is_rejected_as_invalid():
    session = _session()
    service = ListingSearchService(session, cursor_secret="test-secret")
    raw = b"[]"
    signature = hmac.new(b"test-secret", raw, hashlib.sha256).digest()
    cursor = f"{service._b64(raw)}.{service._b64(signature)}"

    with pytest.raises(ValueError, match="invalid cursor"):
        service.search_listings(ListingSearchFilter(cursor=cursor))


def test_multi_sigungu_filter_returns_each_selected_district_without_keyset_gaps():
    session = _session()
    _seed(session)
    rows = {row.article_id: row for row in session.query(ListingCurrent).all()}
    rows[2001].region_code = 4111100000  # 수원시 영통구
    rows[2002].region_code = 4111300000  # 수원시 장안구
    rows[2003].region_code = 4111500000  # 수원시 팔달구
    rows[2004].region_code = 4119000000  # 부천시
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")

    first = service.search_listings(
        ListingSearchFilter(sigungu_codes=[41115, 41111, 41113], sort_by="price_asc", page_size=2)
    )
    second = service.search_listings(
        ListingSearchFilter(
            sigungu_codes=[41111, 41113, 41115],
            sort_by="price_asc",
            page_size=2,
            cursor=first.next_cursor,
        )
    )

    assert [item.article_id for item in first.items + second.items] == [2001, 2002, 2003]
    assert first.has_more is True
    assert second.has_more is False


@pytest.mark.parametrize(
    ("filter_name", "filter_value", "matching_value", "nonmatching_value"),
    [
        ("direct_trade_only", True, True, False),
        ("safe_lessor_hug_only", True, True, False),
        ("min_room_count", 3, 3, 2),
        ("min_bathroom_count", 2, 2, 1),
        ("parking_possible_only", True, True, False),
        ("min_parking_per_household", Decimal("1.2"), 125, 80),
        ("max_monthly_management_cost", 200000, 150000, 250000),
        ("move_in_by", datetime(2026, 9, 1).date(), datetime(2026, 8, 1).date(), datetime(2026, 10, 1).date()),
        ("max_subway_walk_minutes", 7, 5, 12),
    ],
)
def test_each_extended_hot_table_filter_excludes_nonmatching_and_null_values(
    filter_name, filter_value, matching_value, nonmatching_value
):
    session = _session()
    _seed(session)
    rows = {row.article_id: row for row in session.query(ListingCurrent).all()}
    column_name = {
        "direct_trade_only": "is_direct_trade",
        "safe_lessor_hug_only": "is_safe_lessor_hug",
        "min_room_count": "room_count",
        "min_bathroom_count": "bathroom_count",
        "parking_possible_only": "parking_possible",
        "min_parking_per_household": "parking_per_household_x100",
        "max_monthly_management_cost": "monthly_management_cost",
        "move_in_by": "move_in_available_on",
        "max_subway_walk_minutes": "nearest_subway_walk_minutes",
    }[filter_name]
    setattr(rows[2001], column_name, matching_value)
    setattr(rows[2002], column_name, nonmatching_value)
    setattr(rows[2003], column_name, None)
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")
    result = service.search_listings(ListingSearchFilter(**{filter_name: filter_value}))
    assert [item.article_id for item in result.items] == [2001]


def test_detail_filter_cursor_rejects_a_change_to_one_extended_filter():
    session = _session()
    _seed(session)
    rows = {row.article_id: row for row in session.query(ListingCurrent).all()}
    rows[2001].room_count = 3
    rows[2002].room_count = 3
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")
    first = service.search_listings(ListingSearchFilter(min_room_count=3, page_size=1))
    assert first.next_cursor is not None

    with pytest.raises(ValueError, match="cursor"):
        service.search_listings(
            ListingSearchFilter(
                min_room_count=3,
                max_subway_walk_minutes=10,
                page_size=1,
                cursor=first.next_cursor,
            )
        )


def test_detail_filter_keyset_has_no_duplicate_or_gap():
    session = _session()
    _seed(session)
    for row in session.query(ListingCurrent).all():
        row.room_count = 3
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")
    first = service.search_listings(ListingSearchFilter(min_room_count=3, page_size=2))
    second = service.search_listings(
        ListingSearchFilter(min_room_count=3, page_size=2, cursor=first.next_cursor)
    )
    assert [row.article_id for row in first.items + second.items] == [2001, 2002, 2003, 2004]


def test_complex_grouping_returns_summaries_and_queries_only_complex_metadata():
    session = _session()
    _seed(session)
    listings = session.query(ListingCurrent).filter(ListingCurrent.complex_id == 1001).all()
    for listing in listings:
        listing.complex_name = "stale listing name"
        listing.address = "stale listing address"
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")
    statements: list[str] = []

    def capture_selects(_connection, _cursor, statement, _parameters, _context, _many):
        if "listing_current" in statement or "complex_current" in statement:
            statements.append(statement.lower())

    event.listen(session.bind, "before_cursor_execute", capture_selects)
    try:
        result = service.search_listings(
            ListingSearchFilter(group_by_complex=True, sort_by="price_asc", page_size=1)
        )
    finally:
        event.remove(session.bind, "before_cursor_execute", capture_selects)

    assert result.is_grouped is True
    assert result.items == []
    assert len(result.grouped_items) == 1
    assert result.grouped_items[0].complex_id == 1001
    assert result.grouped_items[0].complex_name == "래미안 테스트"
    assert result.grouped_items[0].address == "서울특별시 강서구 테스트로 1"
    assert result.grouped_items[0].listings == []
    assert result.has_more is True
    assert len(statements) == 2
    assert "listing_current.description" not in statements[0]
    assert "listing_current.complex_name" not in statements[0]
    assert "listing_current.address" not in statements[0]
    assert "from complex_current" in statements[1]


def test_complex_grouping_caps_each_summary_page_at_twenty_complexes():
    session = _session()
    _seed(session)
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    for offset in range(19):
        complex_id = 4000 + offset
        session.add(
            ComplexCurrent(
                complex_id=complex_id,
                region_code=1150010200,
                name=f"단지 {complex_id}",
                normalized_name=f"단지{complex_id}",
                address="서울특별시 강서구 테스트로 1",
                household_count=100,
                state_hash=bytes([offset]) * 16,
                first_seen_at=now,
                last_seen_at=now,
                updated_at=now,
            )
        )
        session.add(
            ListingCurrent(
                article_id=40_000 + offset,
                complex_id=complex_id,
                region_code=1150010200,
                complex_name=f"단지 {complex_id}",
                address="서울특별시 강서구 테스트로 1",
                trade_type=1,
                primary_price=700_000_000 + offset,
                exclusive_area_x100=8400,
                state_hash=bytes([offset]) * 16,
                last_seen_job_id=1,
                first_seen_at=now,
                last_seen_at=now,
                last_changed_at=now,
            )
        )
    session.commit()

    result = ListingSearchService(session, cursor_secret="test-secret").search_listings(
        ListingSearchFilter(group_by_complex=True, page_size=100)
    )

    assert len(result.grouped_items) == 20
    assert result.has_more is True


def test_complex_listing_search_pages_twenty_price_sorted_rows_and_preserves_filters():
    session = _session()
    _seed(session)
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    for offset in range(43):
        session.add(
            ListingCurrent(
                article_id=50_000 + offset,
                complex_id=1001,
                region_code=1150010200,
                complex_name="래미안 테스트",
                address="서울특별시 강서구 테스트로 1",
                trade_type=1,
                primary_price=700_000_000 + offset,
                exclusive_area_x100=8400,
                state_hash=bytes([offset]) * 16,
                last_seen_job_id=1,
                first_seen_at=now,
                last_seen_at=now,
                last_changed_at=now,
            )
        )
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")
    filters = ListingSearchFilter(
        sigungu_code=11500,
        min_price=550_000_000,
        group_by_complex=True,
        sort_by="recent",
        page_size=100,
    )

    first = service.search_complex_listings(filters, 1001)
    select_count = 0

    def count_listing_selects(_connection, _cursor, statement, _parameters, _context, _many):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT") and "listing_current" in statement:
            select_count += 1

    event.listen(session.bind, "before_cursor_execute", count_listing_selects)
    try:
        second = service.search_complex_listings(
            ListingSearchFilter(
                sigungu_code=11500,
                min_price=550_000_000,
                group_by_complex=True,
                sort_by="recent",
                page_size=100,
                cursor=first.next_cursor,
            ),
            1001,
        )
    finally:
        event.remove(session.bind, "before_cursor_execute", count_listing_selects)

    assert len(first.items) == 20
    assert len(second.items) == 20
    assert select_count == 1
    assert second.previous_cursor is None
    assert second.has_previous is False
    assert all(item.complex_id == 1001 and item.primary_price >= 550_000_000 for item in first.items + second.items)
    assert [item.primary_price for item in first.items + second.items] == sorted(
        item.primary_price for item in first.items + second.items
    )


def test_complex_listing_cursor_cannot_be_reused_for_another_complex():
    session = _session()
    _seed(session)
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    for offset in range(19):
        session.add(
            ListingCurrent(
                article_id=60_000 + offset,
                complex_id=1001,
                region_code=1150010200,
                complex_name="래미안 테스트",
                address="서울특별시 강서구 테스트로 1",
                trade_type=1,
                primary_price=700_000_000 + offset,
                exclusive_area_x100=8400,
                state_hash=bytes([offset]) * 16,
                last_seen_job_id=1,
                first_seen_at=now,
                last_seen_at=now,
                last_changed_at=now,
            )
        )
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")
    first = service.search_complex_listings(ListingSearchFilter(), 1001)
    assert first.next_cursor is not None

    with pytest.raises(ValueError, match="cursor"):
        service.search_complex_listings(
            ListingSearchFilter(cursor=first.next_cursor),
            1002,
        )


def test_complex_listing_search_applies_exact_policy_eligibility():
    session = _session()
    _seed(session)
    listings = {row.article_id: row for row in session.query(ListingCurrent).all()}
    listings[2001].primary_price = 300_000_000
    listings[2002].primary_price = 7_000_000_000
    session.commit()

    result = ListingSearchService(session, cursor_secret="test-secret").search_complex_listings(
        ListingSearchFilter(only_eligible_loans=True),
        1001,
        ApplicantProfile(),
    )

    assert [item.article_id for item in result.items] == [2001]


def test_all_backend_filters_and_legacy_values_are_applied_to_hot_rows():
    session = _session()
    _seed(session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = {row.article_id: row for row in session.query(ListingCurrent).all()}
    rows[2001].trade_type = 2
    rows[2001].primary_price = 400_000_000
    rows[2001].monthly_rent = 0
    rows[2001].exclusive_area_x100 = 8497
    rows[2001].construction_year = 2010
    rows[2001].household_count = 1200
    rows[2001].direction_code = 2
    rows[2001].floor_band = 3
    rows[2001].floor_no = 8
    rows[2001].mortgage_code = 1
    rows[2001].mortgage_checked_at = now
    rows[2001].first_seen_at = now
    rows[2002].primary_price = 700_000_000
    rows[2002].direction_code = 1
    rows[2002].floor_no = 1
    rows[2002].mortgage_code = 0
    rows[2002].mortgage_checked_at = now
    rows[2002].first_seen_at = now - timedelta(days=31)
    rows[2003].is_short_term = True
    rows[2003].trade_type = 4
    rows[2003].mortgage_code = 2
    rows[2003].mortgage_checked_at = now
    session.commit()

    filters = ListingSearchFilter.from_dict(
        {
            "region_code": 1150010200,
            "trade_types": ["JEONSE", "SHORT_TERM"],
            "min_deposit": 300_000_000,
            "max_deposit": 500_000_000,
            "max_monthly_rent": 1,
            "min_exclusive_area": "84",
            "max_exclusive_area": "85",
            "min_construction_year": 2000,
            "min_households": 1000,
            "recent_days": 3,
            "directions": ["남동향"],
            "floor_types": ["고층"],
            "exclude_first_floor": True,
            "exclude_short_term": True,
            "mortgage_codes": [1],
            "exclude_unknown_mortgage": True,
            "source_code": "SITE_B",
        }
    )

    result = ListingSearchService(session, cursor_secret="test-secret").search_listings(filters)

    assert [item.article_id for item in result.items] == [2001]
    assert filters.trade_types == [2, 4]
    assert filters.direction_codes == [2]
    assert filters.floor_bands == [3]


def test_saved_legacy_transaction_name_is_migrated_to_numeric_codes():
    filters = ListingSearchFilter.from_dict({"trade_type": "JEONSE", "source": "SITE_B"})

    assert filters.trade_type is None
    assert filters.trade_types == [2]


def test_saved_v1_filter_names_migrate_transaction_mortgage_direction_floor_and_region():
    filters = ListingSearchFilter.from_dict(
        {
            "transaction_type": "JEONSE",
            "mortgage_status": "EXPLICIT_NONE",
            "direction": "남동향",
            "floor": "고층",
            "sido": "서울특별시",
            "district": "강서구",
            "source": "SITE_B",
        }
    )

    assert filters.trade_types == [2]
    assert filters.mortgage_codes == [1]
    assert filters.direction_codes == [2]
    assert filters.floor_bands == [3]
    assert filters.sido_code == 11
    assert filters.sigungu_code == 11500


def test_eligible_cursor_rejects_a_different_applicant_profile():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")
    filters = ListingSearchFilter(only_eligible_loans=True, page_size=1)
    first = service.search_listings(filters, applicant=ApplicantProfile(annual_income=40_000_000))

    with pytest.raises(ValueError, match="cursor"):
        service.search_listings(
            ListingSearchFilter(only_eligible_loans=True, page_size=1, cursor=first.next_cursor),
            applicant=ApplicantProfile(annual_income=80_000_000),
        )


def test_eligible_loan_filter_scans_past_ineligible_rows_without_cursor_duplicates():
    session = _session()
    _seed(session)
    rows = {row.article_id: row for row in session.query(ListingCurrent).all()}
    rows[2001].primary_price = 300_000_000
    rows[2002].primary_price = 7_000_000_000
    rows[2003].primary_price = 450_000_000
    rows[2004].primary_price = 8_000_000_000
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")

    first = service.search_listings(ListingSearchFilter(only_eligible_loans=True, page_size=1, sort_by="price_asc"))
    second = service.search_listings(
        ListingSearchFilter(only_eligible_loans=True, page_size=1, sort_by="price_asc", cursor=first.next_cursor)
    )

    assert [item.article_id for item in first.items + second.items] == [2001, 2003]
    assert first.has_more is True
    assert second.has_more is False


def test_eligible_loan_filter_skips_irrelevant_transaction_streams_in_sql():
    session = _session()
    _seed(session)
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    for offset in range(220):
        session.add(
            ListingCurrent(
                article_id=30_000 + offset,
                complex_id=1001,
                region_code=1150010200,
                complex_name="Rental stream",
                address="서울특별시 강서구 테스트로 1",
                trade_type=2,
                primary_price=1_000_000 + offset,
                exclusive_area_x100=8400,
                state_hash=bytes([offset % 256]) * 16,
                last_seen_job_id=1,
                first_seen_at=now,
                last_seen_at=now,
                last_changed_at=now,
            )
        )
    session.commit()
    select_count = 0

    def count_listing_selects(_connection, _cursor, statement, _parameters, _context, _many):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT") and "listing_current" in statement:
            select_count += 1

    event.listen(session.bind, "before_cursor_execute", count_listing_selects)
    try:
        result = ListingSearchService(session, cursor_secret="test-secret").search_listings(
            ListingSearchFilter(only_eligible_loans=True, page_size=1),
            applicant=ApplicantProfile(annual_income=60_000_000),
        )
    finally:
        event.remove(session.bind, "before_cursor_execute", count_listing_selects)

    assert [item.article_id for item in result.items] == [2001]
    assert result.has_more is True
    assert select_count == 1
    assert result.items[0].loan_evaluations


def test_eligible_loan_filter_returns_without_query_when_applicant_has_no_possible_product():
    session = _session()
    _seed(session)
    select_count = 0

    def count_listing_selects(_connection, _cursor, statement, _parameters, _context, _many):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT") and "listing_current" in statement:
            select_count += 1

    event.listen(session.bind, "before_cursor_execute", count_listing_selects)
    try:
        result = ListingSearchService(session, cursor_secret="test-secret").search_listings(
            ListingSearchFilter(only_eligible_loans=True),
            applicant=ApplicantProfile(
                is_homeless=False,
                annual_income=250_000_000,
                has_newborn=False,
            ),
        )
    finally:
        event.remove(session.bind, "before_cursor_execute", count_listing_selects)

    assert result.items == []
    assert select_count == 0


def test_grouped_empty_loan_plan_still_rejects_an_invalid_cursor():
    session = _session()
    _seed(session)

    with pytest.raises(ValueError, match="cursor"):
        ListingSearchService(session, cursor_secret="test-secret").search_listings(
            ListingSearchFilter(
                only_eligible_loans=True,
                group_by_complex=True,
                cursor="tampered",
            ),
            applicant=ApplicantProfile(
                is_homeless=False,
                annual_income=250_000_000,
                has_newborn=False,
            ),
        )


def test_eligible_loan_candidates_use_separate_transaction_streams():
    session = _session()
    _seed(session)
    statements: list[str] = []

    def capture_listing_selects(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT") and "listing_current" in statement:
            statements.append(statement.lower())

    event.listen(session.bind, "before_cursor_execute", capture_listing_selects)
    try:
        result = ListingSearchService(session, cursor_secret="test-secret").search_listings(
            ListingSearchFilter(only_eligible_loans=True, page_size=1),
            applicant=ApplicantProfile(annual_income=40_000_000),
        )
    finally:
        event.remove(session.bind, "before_cursor_execute", capture_listing_selects)

    assert result.items
    assert len(statements) == 4
    assert all("listing_current.trade_type = ?" in statement for statement in statements)
    assert all("listing_current.trade_type in" not in statement for statement in statements)


def test_mysql_price_candidate_stream_prefers_the_transaction_sort_index():
    session = _session()
    service = ListingSearchService(session, cursor_secret="test-secret")
    filters = ListingSearchFilter(only_eligible_loans=True, sort_by="price_asc")
    stream = service._eligible_candidate_streams(
        filters,
        ApplicantProfile(annual_income=60_000_000),
    )[0]

    hinted = service._with_candidate_index_hint(stream, filters, service._sort(filters))
    sql = str(hinted.compile(dialect=mysql.dialect())).lower()

    assert "use index (ix_listing_price_tx)" in sql


def test_complex_candidate_stream_keeps_the_complex_index_available():
    session = _session()
    service = ListingSearchService(session, cursor_secret="test-secret")
    filters = ListingSearchFilter(
        complex_id=1001,
        only_eligible_loans=True,
        sort_by="price_asc",
    )
    stream = service._eligible_candidate_streams(
        filters,
        ApplicantProfile(annual_income=60_000_000),
    )[0]

    hinted = service._with_candidate_index_hint(stream, filters, service._sort(filters))
    sql = str(hinted.compile(dialect=mysql.dialect())).lower()

    assert "use index" not in sql


def test_grouped_eligible_loan_filter_exposes_only_eligible_listings():
    session = _session()
    _seed(session)
    rows = {row.article_id: row for row in session.query(ListingCurrent).all()}
    rows[2001].primary_price = 300_000_000
    rows[2002].primary_price = 7_000_000_000
    rows[2003].primary_price = 8_000_000_000
    rows[2004].primary_price = 9_000_000_000
    session.commit()

    result = ListingSearchService(session, cursor_secret="test-secret").search_listings(
        ListingSearchFilter(only_eligible_loans=True, group_by_complex=True, page_size=10)
    )

    assert [group.complex_id for group in result.grouped_items] == [1001]
    assert result.items == []
    assert result.grouped_items[0].listing_count == 1
    assert result.grouped_items[0].min_price == 300_000_000
    assert result.grouped_items[0].max_price == 300_000_000
    assert result.grouped_items[0].listings == []


def test_eligible_grouped_aggregate_cte_projects_only_group_sort_columns():
    session = _session()
    _seed(session)
    statements: list[str] = []

    def capture_selects(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("WITH ELIGIBLE_GROUP_CANDIDATES"):
            statements.append(statement.lower())

    event.listen(session.bind, "before_cursor_execute", capture_selects)
    try:
        ListingSearchService(session, cursor_secret="test-secret").search_listings(
            ListingSearchFilter(only_eligible_loans=True, group_by_complex=True),
            ApplicantProfile(),
        )
    finally:
        event.remove(session.bind, "before_cursor_execute", capture_selects)

    projection = statements[0].split("from listing_current", 1)[0]
    assert "listing_current.complex_id as complex_id" in projection
    assert "listing_current.primary_price as primary_price" in projection
    assert "listing_current.description as description" not in projection
    assert "listing_current.complex_name as complex_name" not in projection
    assert "listing_current.address as address" not in projection


def test_grouped_eligible_loan_filter_advances_by_group_keyset_cursor():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")
    evaluated_article_ids: list[int] = []
    original_is_eligible = service._is_loan_eligible

    def record_evaluation(listing, applicant):
        evaluated_article_ids.append(listing.article_id)
        return original_is_eligible(listing, applicant)

    service._is_loan_eligible = record_evaluation

    first = service.search_listings(ListingSearchFilter(only_eligible_loans=True, group_by_complex=True, page_size=1))
    evaluated_article_ids.clear()
    second = service.search_listings(
        ListingSearchFilter(
            only_eligible_loans=True, group_by_complex=True, page_size=1, cursor=first.next_cursor
        )
    )

    assert [group.complex_id for group in first.grouped_items + second.grouped_items] == [1001, 1002]
    assert first.has_more is True
    assert second.has_more is False
    assert set(evaluated_article_ids) == {2003, 2004}


@pytest.mark.parametrize(
    ("sort_by", "expected_complexes"),
    [
        ("price_asc", [1002, 1001]),
        ("recent", [1002, 1001]),
        ("area_asc", [1002, 1001]),
        ("households_asc", [1001, 1002]),
    ],
)
def test_grouped_eligible_sort_and_cursor_use_only_eligible_listing_values(sort_by, expected_complexes):
    session = _session()
    _seed(session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = {row.article_id: row for row in session.query(ListingCurrent).all()}
    # Complex 1001 has one eligible listing and one cheaper/newer/smaller
    # ineligible listing. Its display and cursor must ignore the latter.
    rows[2001].primary_price = 500_000_000
    rows[2001].exclusive_area_x100 = 8000
    rows[2001].household_count = 100
    rows[2001].first_seen_at = now - timedelta(days=10)
    rows[2002].primary_price = 100_000_000 if sort_by == "price_asc" else 7_000_000_000
    rows[2002].exclusive_area_x100 = 10000 if sort_by == "price_asc" else 10
    rows[2002].household_count = 1200
    rows[2002].first_seen_at = now
    rows[2002].trade_type = 99
    rows[2003].primary_price = 400_000_000
    rows[2003].exclusive_area_x100 = 7000
    rows[2003].household_count = 800
    rows[2003].first_seen_at = now - timedelta(days=1)
    rows[2004].primary_price = 900_000_000
    rows[2004].exclusive_area_x100 = 10000
    rows[2004].household_count = 800
    rows[2004].first_seen_at = now - timedelta(days=2)
    rows[2004].trade_type = 99
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")

    first = service.search_listings(
        ListingSearchFilter(only_eligible_loans=True, group_by_complex=True, page_size=1, sort_by=sort_by)
    )
    second = service.search_listings(
        ListingSearchFilter(
            only_eligible_loans=True,
            group_by_complex=True,
            page_size=1,
            sort_by=sort_by,
            cursor=first.next_cursor,
        )
    )

    assert [group.complex_id for group in first.grouped_items + second.grouped_items] == expected_complexes
    assert first.grouped_items[0].listing_count == 1


def test_grouped_eligible_price_cursor_scans_past_raw_batch_until_global_order_is_safe():
    session = _session()
    _seed(session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for listing in session.query(ListingCurrent).all():
        listing.trade_type = 99
    for offset in range(51):
        complex_id = 3000 + offset
        session.add(
            ComplexCurrent(
                complex_id=complex_id,
                region_code=1150010200,
                name=f"테스트 {complex_id}",
                normalized_name=f"테스트{complex_id}",
                address="서울특별시 강서구 테스트로 1",
                household_count=1000,
                state_hash=bytes([offset]) * 16,
                first_seen_at=now,
                last_seen_at=now,
                updated_at=now,
            )
        )
        # The raw minimum is ineligible and appears in the first 50-group
        # SQL batch. The final group has the best eligible price.
        session.add_all(
            [
                ListingCurrent(
                    article_id=10_000 + offset * 2,
                    complex_id=complex_id,
                    region_code=1150010200,
                    complex_name=f"테스트 {complex_id}",
                    address="서울특별시 강서구 테스트로 1",
                    household_count=1000,
                    trade_type=99,
                    primary_price=offset + 1,
                    exclusive_area_x100=8000,
                    state_hash=bytes([offset]) * 16,
                    last_seen_job_id=1,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_changed_at=now,
                ),
                ListingCurrent(
                    article_id=10_001 + offset * 2,
                    complex_id=complex_id,
                    region_code=1150010200,
                    complex_name=f"테스트 {complex_id}",
                    address="서울특별시 강서구 테스트로 1",
                    household_count=1000,
                    trade_type=1,
                    primary_price=400_000_000 if offset == 50 else 500_000_000,
                    exclusive_area_x100=8000,
                    state_hash=bytes([offset + 1]) * 16,
                    last_seen_job_id=1,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_changed_at=now,
                ),
            ]
        )
    session.commit()
    service = ListingSearchService(session, cursor_secret="test-secret")
    cursor = None
    seen: list[int] = []
    while True:
        result = service.search_listings(
            ListingSearchFilter(
                only_eligible_loans=True,
                group_by_complex=True,
                page_size=10,
                sort_by="price_asc",
                cursor=cursor,
            )
        )
        seen.extend(group.complex_id for group in result.grouped_items)
        if not result.has_more:
            break
        cursor = result.next_cursor

    assert seen[0] == 3050
    assert len(seen) == 51
    assert len(set(seen)) == 51


def test_purchase_affordable_filter_scans_keyset_pages_without_duplicates():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")
    applicant = ApplicantProfile(available_cash=300_000_000, max_monthly_housing_cost=2_000_000)
    filters = ListingSearchFilter(only_purchase_affordable=True, page_size=1, sort_by="price_asc")

    first = service.search_listings(filters, applicant)
    second = service.search_listings(
        ListingSearchFilter(
            only_purchase_affordable=True,
            page_size=1,
            sort_by="price_asc",
            cursor=first.next_cursor,
        ),
        applicant,
    )
    third = service.search_listings(
        ListingSearchFilter(
            only_purchase_affordable=True,
            page_size=1,
            sort_by="price_asc",
            cursor=second.next_cursor,
        ),
        applicant,
    )

    assert [row.article_id for row in first.items + second.items + third.items] == [2001, 2002, 2003]
    assert third.has_more is False


def test_purchase_affordable_filter_rejects_incomplete_profile_before_select(monkeypatch):
    service = ListingSearchService(_session(), cursor_secret="test-secret")
    monkeypatch.setattr(service, "_scalars", lambda _statement: pytest.fail("must not query listings"))

    with pytest.raises(ListingSearchValidationError, match="profile incomplete"):
        service.search_listings(
            ListingSearchFilter(only_purchase_affordable=True), ApplicantProfile(available_cash=300_000_000)
        )


def test_grouped_purchase_filter_returns_only_complexes_with_a_qualifying_sale():
    session = _session()
    _seed(session)

    result = ListingSearchService(session, cursor_secret="test-secret").search_listings(
        ListingSearchFilter(group_by_complex=True, only_purchase_affordable=True, page_size=10),
        ApplicantProfile(available_cash=230_000_000, max_monthly_housing_cost=2_000_000),
    )

    assert [group.complex_id for group in result.grouped_items] == [1001]


def test_purchase_filter_combines_with_policy_loan_filter():
    session = _session()
    _seed(session)

    result = ListingSearchService(session, cursor_secret="test-secret").search_listings(
        ListingSearchFilter(only_purchase_affordable=True, only_eligible_loans=True),
        ApplicantProfile(available_cash=300_000_000, max_monthly_housing_cost=2_000_000),
    )

    assert result.items
    assert all(any(loan.is_eligible for loan in row.loan_evaluations) for row in result.items)
