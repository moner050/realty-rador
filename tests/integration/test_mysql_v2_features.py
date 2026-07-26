"""명시적 MySQL v2 test DB에서만 실행하는 schema capability checks."""
import os

import pytest
from sqlalchemy import create_engine, text


pytestmark = pytest.mark.mysql


def test_mysql_v2_schema_supports_generated_fulltext_temp_and_skip_locked():
    url = os.getenv("MYSQL_V2_TEST_URL")
    if not url:
        pytest.skip("set MYSQL_V2_TEST_URL to an explicitly provisioned v2 test database")
    if "test" not in url.lower():
        pytest.skip("MYSQL_V2_TEST_URL must point at a test database")

    engine = create_engine(url, pool_pre_ping=True)
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
        fulltext = connection.scalar(text("SHOW INDEX FROM complex_current WHERE Key_name = 'ft_complex_name'"))
        assert fulltext is not None
        connection.execute(text("CREATE TEMPORARY TABLE incoming_listing_probe (article_id BIGINT UNSIGNED PRIMARY KEY)"))
        connection.execute(text("INSERT INTO incoming_listing_probe VALUES (1)"))
        connection.execute(text("SELECT job_id FROM crawl_job FOR UPDATE SKIP LOCKED"))
