from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.application.listing_search_service import ListingSearchService
from realty_radar.domain.listing.filters import ListingSearchFilter
from realty_radar.domain.loan.entities import ApplicantProfile
from realty_radar.infrastructure.database.models import Base, ComplexCurrent, ListingCurrent


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


def test_cursor_cannot_be_reused_with_different_filters():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")
    first = service.search_listings(ListingSearchFilter(sort_by="price_asc", page_size=1))

    with pytest.raises(ValueError, match="cursor"):
        service.search_listings(
            ListingSearchFilter(trade_type=2, sort_by="price_asc", page_size=1, cursor=first.next_cursor)
        )


def test_complex_grouping_uses_group_rows_and_second_listing_query():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")

    result = service.search_listings(ListingSearchFilter(group_by_complex=True, sort_by="price_asc", page_size=1))

    assert result.is_grouped is True
    assert len(result.grouped_items) == 1
    assert result.grouped_items[0].complex_id == 1001
    assert [item.article_id for item in result.grouped_items[0].listings] == [2001, 2002]
    assert result.has_more is True


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
    assert [item.article_id for item in result.grouped_items[0].listings] == [2001]


def test_grouped_eligible_loan_filter_advances_by_group_keyset_cursor():
    session = _session()
    _seed(session)
    service = ListingSearchService(session, cursor_secret="test-secret")

    first = service.search_listings(ListingSearchFilter(only_eligible_loans=True, group_by_complex=True, page_size=1))
    second = service.search_listings(
        ListingSearchFilter(
            only_eligible_loans=True, group_by_complex=True, page_size=1, cursor=first.next_cursor
        )
    )

    assert [group.complex_id for group in first.grouped_items + second.grouped_items] == [1001, 1002]
    assert first.has_more is True
    assert second.has_more is False


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
