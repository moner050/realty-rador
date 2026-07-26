"""SITE_A 전용 v2 canonical schema.

Revision ID: 001_site_a_v2
Revises:
Create Date: 2026-07-26 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "001_site_a_v2"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UBIGINT = mysql.BIGINT(unsigned=True)
UINT = mysql.INTEGER(unsigned=True)
UMEDIUMINT = mysql.MEDIUMINT(unsigned=True)
USMALLINT = mysql.SMALLINT(unsigned=True)
UTINYINT = mysql.TINYINT(unsigned=True)
DATETIME6 = mysql.DATETIME(fsp=6)
HASH16 = mysql.BINARY(16)


def upgrade() -> None:
    op.create_table(
        "complex_current",
        sa.Column("complex_id", UBIGINT, autoincrement=False, nullable=False),
        sa.Column("region_code", UBIGINT, nullable=False),
        sa.Column("sido_code", USMALLINT, sa.Computed("region_code DIV 100000000", persisted=True), nullable=False),
        sa.Column("sigungu_code", UINT, sa.Computed("region_code DIV 100000", persisted=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("address", sa.String(length=240), nullable=False),
        sa.Column("construction_year", USMALLINT, server_default=sa.text("0"), nullable=False),
        sa.Column("household_count", UMEDIUMINT, server_default=sa.text("0"), nullable=False),
        sa.Column("state_hash", HASH16, nullable=False),
        sa.Column("first_seen_at", DATETIME6, nullable=False),
        sa.Column("last_seen_at", DATETIME6, nullable=False),
        sa.Column("updated_at", DATETIME6, nullable=False),
        sa.PrimaryKeyConstraint("complex_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_complex_region_name", "complex_current", ["sigungu_code", "normalized_name", "complex_id"])
    op.create_index("ix_complex_build", "complex_current", ["sigungu_code", "construction_year", "household_count", "complex_id"])
    op.create_index(
        "ft_complex_name",
        "complex_current",
        ["name", "normalized_name", "address"],
        mysql_prefix="FULLTEXT",
        mysql_with_parser="ngram",
    )

    op.create_table(
        "listing_current",
        sa.Column("article_id", UBIGINT, autoincrement=False, nullable=False),
        sa.Column("complex_id", UBIGINT, nullable=False),
        sa.Column("region_code", UBIGINT, nullable=False),
        sa.Column("sido_code", USMALLINT, sa.Computed("region_code DIV 100000000", persisted=True), nullable=False),
        sa.Column("sigungu_code", UINT, sa.Computed("region_code DIV 100000", persisted=True), nullable=False),
        sa.Column("complex_name", sa.String(length=120), nullable=False),
        sa.Column("address", sa.String(length=240), nullable=False),
        sa.Column("construction_year", USMALLINT, server_default=sa.text("0"), nullable=False),
        sa.Column("household_count", UMEDIUMINT, server_default=sa.text("0"), nullable=False),
        sa.Column("trade_type", UTINYINT, nullable=False),
        sa.Column("primary_price", UBIGINT, nullable=False),
        sa.Column("monthly_rent", UBIGINT, server_default=sa.text("0"), nullable=False),
        sa.Column("exclusive_area_x100", UINT, server_default=sa.text("0"), nullable=False),
        sa.Column("supply_area_x100", UINT, server_default=sa.text("0"), nullable=False),
        sa.Column("floor_no", mysql.SMALLINT(), nullable=True),
        sa.Column("total_floor", USMALLINT, nullable=True),
        sa.Column("floor_band", UTINYINT, server_default=sa.text("0"), nullable=False),
        sa.Column("direction_code", UTINYINT, server_default=sa.text("0"), nullable=False),
        sa.Column("mortgage_code", UTINYINT, server_default=sa.text("0"), nullable=False),
        sa.Column("is_top_floor", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_short_term", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("building_name", sa.String(length=40), nullable=True),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("lifecycle", UTINYINT, server_default=sa.text("1"), nullable=False),
        sa.Column("miss_count", UTINYINT, server_default=sa.text("0"), nullable=False),
        sa.Column("state_hash", HASH16, nullable=False),
        sa.Column("last_seen_job_id", UBIGINT, nullable=False),
        sa.Column("first_seen_at", DATETIME6, nullable=False),
        sa.Column("last_seen_at", DATETIME6, nullable=False),
        sa.Column("last_changed_at", DATETIME6, nullable=False),
        sa.Column("removed_at", DATETIME6, nullable=True),
        sa.ForeignKeyConstraint(["complex_id"], ["complex_current.complex_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("article_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_listing_price_all", "listing_current", ["lifecycle", "is_short_term", "primary_price", "article_id"])
    op.create_index("ix_listing_price_tx", "listing_current", ["lifecycle", "is_short_term", "trade_type", "primary_price", "article_id"])
    op.create_index("ix_listing_price_sido", "listing_current", ["lifecycle", "is_short_term", "sido_code", "primary_price", "article_id"])
    op.create_index("ix_listing_price_sigungu", "listing_current", ["lifecycle", "is_short_term", "sigungu_code", "primary_price", "article_id"])
    op.create_index(
        "ix_listing_price_sigungu_tx",
        "listing_current",
        ["lifecycle", "is_short_term", "sigungu_code", "trade_type", "primary_price", "article_id"],
    )
    op.create_index(
        "ix_listing_recent",
        "listing_current",
        ["lifecycle", "is_short_term", sa.text("first_seen_at DESC"), sa.text("article_id DESC")],
    )
    op.create_index("ix_listing_area", "listing_current", ["lifecycle", "is_short_term", "exclusive_area_x100", "article_id"])
    op.create_index("ix_listing_households", "listing_current", ["lifecycle", "is_short_term", "household_count", "article_id"])
    op.create_index("ix_listing_complex", "listing_current", ["complex_id", "lifecycle", "is_short_term", "primary_price", "article_id"])
    op.create_index("ix_listing_presence", "listing_current", ["region_code", "last_seen_job_id", "lifecycle", "article_id"])

    op.create_table(
        "listing_history",
        sa.Column("event_id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("article_id", UBIGINT, nullable=False),
        sa.Column("complex_id", UBIGINT, nullable=False),
        sa.Column("job_id", UBIGINT, nullable=False),
        sa.Column("event_type", UTINYINT, nullable=False),
        sa.Column("change_mask", UINT, server_default=sa.text("0"), nullable=False),
        sa.Column("primary_price", UBIGINT, nullable=True),
        sa.Column("monthly_rent", UBIGINT, nullable=True),
        sa.Column("lifecycle", UTINYINT, nullable=True),
        sa.Column("mortgage_code", UTINYINT, nullable=True),
        sa.Column("floor_no", mysql.SMALLINT(), nullable=True),
        sa.Column("total_floor", USMALLINT, nullable=True),
        sa.Column("direction_code", UTINYINT, nullable=True),
        sa.Column("state_hash", HASH16, nullable=False),
        sa.Column("occurred_at", DATETIME6, nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("job_id", "article_id", "event_type", name="uk_history_idempotency"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_history_timeline", "listing_history", ["article_id", sa.text("occurred_at DESC"), sa.text("event_id DESC")])
    op.create_index("ix_history_retention", "listing_history", ["occurred_at", "event_id"])

    op.create_table(
        "crawl_job",
        sa.Column("job_id", UBIGINT, autoincrement=True, nullable=False),
        sa.Column("dedupe_key", sa.String(length=160), nullable=False),
        sa.Column("status", UTINYINT, server_default=sa.text("1"), nullable=False),
        sa.Column("priority", USMALLINT, server_default=sa.text("100"), nullable=False),
        sa.Column("available_at", DATETIME6, nullable=False),
        sa.Column("attempt", UTINYINT, server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", UTINYINT, server_default=sa.text("3"), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", DATETIME6, nullable=True),
        sa.Column("heartbeat_at", DATETIME6, nullable=True),
        sa.Column("scope_level", UTINYINT, nullable=False),
        sa.Column("scope_code", UBIGINT, nullable=False),
        sa.Column("fetched_count", UINT, server_default=sa.text("0"), nullable=False),
        sa.Column("committed_count", UINT, server_default=sa.text("0"), nullable=False),
        sa.Column("created_count", UINT, server_default=sa.text("0"), nullable=False),
        sa.Column("updated_count", UINT, server_default=sa.text("0"), nullable=False),
        sa.Column("rejected_count", UINT, server_default=sa.text("0"), nullable=False),
        sa.Column("removed_count", UINT, server_default=sa.text("0"), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("created_at", DATETIME6, server_default=sa.text("CURRENT_TIMESTAMP(6)"), nullable=False),
        sa.Column("started_at", DATETIME6, nullable=True),
        sa.Column("finished_at", DATETIME6, nullable=True),
        sa.Column("updated_at", DATETIME6, server_default=sa.text("CURRENT_TIMESTAMP(6)"), nullable=False),
        sa.PrimaryKeyConstraint("job_id"),
        sa.UniqueConstraint("dedupe_key", name="uk_job_dedupe"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_job_claim", "crawl_job", ["status", "available_at", "priority", "job_id"])
    op.create_index("ix_job_reap", "crawl_job", ["status", "lease_expires_at", "job_id"])
    op.create_index("ix_job_recent", "crawl_job", [sa.text("created_at DESC"), sa.text("job_id DESC")])

    op.create_table(
        "crawl_scope",
        sa.Column("job_id", UBIGINT, nullable=False),
        sa.Column("region_code", UBIGINT, nullable=False),
        sa.Column("status", UTINYINT, server_default=sa.text("1"), nullable=False),
        sa.Column("total_pages", USMALLINT, server_default=sa.text("0"), nullable=False),
        sa.Column("done_pages", USMALLINT, server_default=sa.text("0"), nullable=False),
        sa.Column("failed_pages", USMALLINT, server_default=sa.text("0"), nullable=False),
        sa.Column("fetched_count", UINT, server_default=sa.text("0"), nullable=False),
        sa.Column("committed_count", UINT, server_default=sa.text("0"), nullable=False),
        sa.Column("rejected_count", UINT, server_default=sa.text("0"), nullable=False),
        sa.Column("is_truncated", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column("started_at", DATETIME6, nullable=True),
        sa.Column("finished_at", DATETIME6, nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["crawl_job.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id", "region_code"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    op.drop_table("crawl_scope")
    op.drop_table("crawl_job")
    op.drop_table("listing_history")
    op.drop_table("listing_current")
    op.drop_table("complex_current")
