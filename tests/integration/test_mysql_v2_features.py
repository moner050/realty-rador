"""명시적 MySQL v2 test DB에서만 실행하는 schema capability checks."""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from realty_radar.application.listing_batch_writer import IncomingListing, ListingBatchWriter
from realty_radar.infrastructure.database.models import CrawlJob, ListingCurrent


pytestmark = pytest.mark.mysql


def _mysql_v2_url() -> str:
    url = os.getenv("MYSQL_V2_TEST_URL")
    if not url:
        pytest.skip("set MYSQL_V2_TEST_URL to an explicitly provisioned v2 test database")
    if "test" not in url.lower():
        pytest.skip("MYSQL_V2_TEST_URL must point at a test database")
    return url


def test_mysql_v2_schema_supports_generated_fulltext_temp_and_skip_locked():
    engine = create_engine(_mysql_v2_url(), pool_pre_ping=True)
    with engine.begin() as connection:
        version = connection.scalar(text("SELECT VERSION()"))
        assert str(version).startswith("8.")
        tables = {
            row[0]
            for row in connection.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()")
            )
        }
        assert {"complex_current", "listing_current", "listing_history", "crawl_job", "crawl_scope"}.issubset(tables)
        generated = connection.scalar(
            text(
                """
                SELECT extra FROM information_schema.columns
                WHERE table_schema = DATABASE() AND table_name = 'listing_current' AND column_name = 'sigungu_code'
                """
            )
        )
        assert "GENERATED" in str(generated).upper()
        mortgage_column = connection.scalar(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = DATABASE() AND table_name = 'listing_current'
                  AND column_name = 'mortgage_checked_at'
                """
            )
        )
        assert mortgage_column == "mortgage_checked_at"
        mortgage_index = connection.scalar(
            text("SHOW INDEX FROM listing_current WHERE Key_name = 'ix_listing_mortgage_pending'")
        )
        assert mortgage_index is not None
        expected_columns = {
            "is_direct_trade": ("tinyint", "YES", None, "tinyint(1)"),
            "is_safe_lessor_hug": ("tinyint", "YES", None, "tinyint(1)"),
            "parking_possible": ("tinyint", "YES", None, "tinyint(1)"),
            "room_count": ("tinyint", "YES", None, "tinyint unsigned"),
            "bathroom_count": ("tinyint", "YES", None, "tinyint unsigned"),
            "parking_per_household_x100": ("int", "YES", None, "int unsigned"),
            "monthly_management_cost": ("int", "YES", None, "int unsigned"),
            "move_in_available_on": ("date", "YES", None, "date"),
            "nearest_subway_walk_minutes": ("smallint", "YES", None, "smallint unsigned"),
            "detail_checked_at": ("datetime", "YES", 6, "datetime(6)"),
        }
        columns = {
            row[0]: (row[1], row[2], row[3], row[4])
            for row in connection.execute(
                text(
                    """
                    SELECT column_name, data_type, is_nullable, datetime_precision, column_type
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE() AND table_name = 'listing_current'
                    """
                )
            )
        }
        assert {name: columns[name] for name in expected_columns} == expected_columns
        expected_indexes = {
            "ix_listing_group_cover": (
                "lifecycle",
                "is_short_term",
                "complex_id",
                "primary_price",
                "article_id",
                "first_seen_at",
                "exclusive_area_x100",
                "household_count",
                "region_code",
                "sido_code",
                "sigungu_code",
                "trade_type",
                "construction_year",
                "monthly_rent",
            ),
            "ix_listing_complex": (
                "complex_id",
                "lifecycle",
                "is_short_term",
                "primary_price",
                "article_id",
            ),
            "ix_listing_move_in": ("lifecycle", "is_short_term", "move_in_available_on", "article_id"),
            "ix_listing_subway_walk": ("lifecycle", "is_short_term", "nearest_subway_walk_minutes", "article_id"),
            "ix_listing_management_cost": ("lifecycle", "is_short_term", "monthly_management_cost", "article_id"),
            "ix_listing_detail_pending": ("detail_checked_at", "article_id"),
        }
        indexes = {}
        for row in connection.execute(
            text(
                """
                SELECT index_name, seq_in_index, column_name
                FROM information_schema.statistics
                WHERE table_schema = DATABASE() AND table_name = 'listing_current'
                ORDER BY index_name, seq_in_index
                """
            )
        ):
            indexes.setdefault(row[0], []).append(row[2])
        assert {name: tuple(indexes[name]) for name in expected_indexes} == expected_indexes
        fulltext = connection.scalar(text("SHOW INDEX FROM complex_current WHERE Key_name = 'ft_complex_name'"))
        assert fulltext is not None
        connection.execute(text("CREATE TEMPORARY TABLE incoming_listing_probe (article_id BIGINT UNSIGNED PRIMARY KEY)"))
        connection.execute(text("INSERT INTO incoming_listing_probe VALUES (1)"))
        connection.execute(text("SELECT job_id FROM crawl_job FOR UPDATE SKIP LOCKED"))


def test_mysql_listing_batch_writer_upserts_list_flags_without_overwriting_detail_fields():
    engine = create_engine(_mysql_v2_url(), pool_pre_ping=True)
    session = sessionmaker(bind=engine)()
    marker = int(uuid4().int % 1_000_000_000) + 8_000_000_000
    article_id = marker
    complex_id = marker + 1
    job_ids = (marker + 2, marker + 3)
    now = datetime(2026, 7, 26, tzinfo=timezone.utc).replace(tzinfo=None)

    def incoming(*, direct_trade: bool | None, safe_lessor_hug: bool | None) -> IncomingListing:
        return IncomingListing(
            article_id=article_id,
            complex_id=complex_id,
            region_code=1150010200,
            complex_name="MySQL 테스트 아파트",
            normalized_complex_name="mysql테스트아파트",
            address="서울특별시 테스트로 1",
            trade_type=1,
            primary_price=500_000_000,
            is_direct_trade=direct_trade,
            is_safe_lessor_hug=safe_lessor_hug,
        )

    try:
        session.add_all(
            [
                CrawlJob(
                    job_id=job_ids[0],
                    dedupe_key=f"mysql-test:{marker}:1",
                    status=1,
                    scope_level=3,
                    scope_code=1150010200,
                    available_at=now,
                    created_at=now,
                    updated_at=now,
                ),
                CrawlJob(
                    job_id=job_ids[1],
                    dedupe_key=f"mysql-test:{marker}:2",
                    status=1,
                    scope_level=3,
                    scope_code=1150010200,
                    available_at=now,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.commit()
        writer = ListingBatchWriter(session)
        writer.commit_batch(job_ids[0], [incoming(direct_trade=False, safe_lessor_hug=None)], observed_at=now)
        row = session.get(ListingCurrent, article_id)
        assert row is not None
        row.room_count = 3
        row.detail_checked_at = now
        session.commit()

        writer.commit_batch(job_ids[1], [incoming(direct_trade=True, safe_lessor_hug=True)], observed_at=now)

        refreshed = session.get(ListingCurrent, article_id)
        assert refreshed is not None
        assert refreshed.is_direct_trade is True
        assert refreshed.is_safe_lessor_hug is True
        assert refreshed.room_count == 3
        assert refreshed.detail_checked_at == now
    finally:
        session.execute(text("DELETE FROM listing_history WHERE article_id = :article_id"), {"article_id": article_id})
        session.execute(text("DELETE FROM listing_current WHERE article_id = :article_id"), {"article_id": article_id})
        session.execute(text("DELETE FROM complex_current WHERE complex_id = :complex_id"), {"complex_id": complex_id})
        session.execute(text("DELETE FROM crawl_job WHERE job_id IN (:job_one, :job_two)"), dict(job_one=job_ids[0], job_two=job_ids[1]))
        session.commit()
        session.close()
