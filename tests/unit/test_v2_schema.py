from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from realty_radar.infrastructure.database.models.base import Base
from realty_radar.infrastructure.database.models.v2 import (
    ComplexCurrent,
    CrawlJob,
    CrawlScope,
    ListingCurrent,
    ListingHistory,
)


def test_v2_schema_contains_expected_domain_tables():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    table_names = set(inspect(engine).get_table_names())
    assert table_names == {
        "complex_current",
        "listing_current",
        "listing_history",
        "crawl_job",
        "crawl_scope",
        "user_account",
        "user_preference",
        "scheduler_log",
    }



def test_current_rows_use_authoritative_ids_and_generated_region_codes():
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
            complex_id=1001,
            region_code=1150010200,
            name="테스트 아파트",
            normalized_name="테스트아파트",
            address="서울특별시 강서구 테스트로 1",
            state_hash=b"c" * 16,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            updated_at=seen_at,
        )
    )
    session.add(
        ListingCurrent(
            article_id=2001,
            complex_id=1001,
            region_code=1150010200,
            complex_name="테스트 아파트",
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
    session.add(
        CrawlJob(
            dedupe_key="dong:1150010200",
            scope_level=3,
            scope_code=1150010200,
            status=1,
            available_at=seen_at,
        )
    )
    session.add(
        CrawlScope(
            job_id=1,
            region_code=1150010200,
            status=1,
        )
    )
    session.add(
        ListingHistory(
            article_id=2001,
            complex_id=1001,
            job_id=1,
            event_type=1,
            state_hash=b"l" * 16,
            occurred_at=seen_at,
        )
    )
    session.commit()

    listing = session.scalar(select(ListingCurrent).where(ListingCurrent.article_id == 2001))
    assert listing is not None
    assert listing.sido_code == 11
    assert listing.sigungu_code == 11500
    assert listing.complex_id == 1001


def test_listing_current_declares_detail_columns_and_only_the_planned_range_indexes():
    column_names = set(ListingCurrent.__table__.columns.keys())
    assert {
        "is_direct_trade",
        "is_safe_lessor_hug",
        "parking_possible",
        "room_count",
        "bathroom_count",
        "parking_per_household_x100",
        "monthly_management_cost",
        "move_in_available_on",
        "nearest_subway_walk_minutes",
        "detail_checked_at",
    }.issubset(column_names)
    indexes = {index.name: tuple(column.name for column in index.columns) for index in ListingCurrent.__table__.indexes}
    assert indexes["ix_listing_move_in"] == ("lifecycle", "is_short_term", "move_in_available_on", "article_id")
    assert indexes["ix_listing_subway_walk"] == (
        "lifecycle",
        "is_short_term",
        "nearest_subway_walk_minutes",
        "article_id",
    )
    assert indexes["ix_listing_management_cost"] == (
        "lifecycle",
        "is_short_term",
        "monthly_management_cost",
        "article_id",
    )
    assert indexes["ix_listing_detail_pending"] == ("detail_checked_at", "article_id")


def test_complex_current_declares_nullable_verified_coordinate_columns():
    columns = ComplexCurrent.__table__.columns

    assert {
        "latitude",
        "longitude",
        "geocode_status",
        "geocoded_address_hash",
        "geocoded_at",
        "geocode_attempted_at",
        "geocode_retry_after",
    }.issubset(columns.keys())
    assert columns["latitude"].nullable is True
    assert columns["longitude"].nullable is True
    assert columns["geocode_status"].nullable is False
