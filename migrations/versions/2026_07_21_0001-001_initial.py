"""initial schema

Revision ID: 001_initial
Revises: 
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. crawl_source
    op.create_table(
        "crawl_source",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("login_required", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("session_status", sa.String(length=30), server_default="UNKNOWN", nullable=False),
        sa.Column("minimum_interval_ms", sa.Integer(), server_default="3000", nullable=False),
        sa.Column("maximum_concurrency", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("adapter_name", sa.String(length=150), nullable=False),
        sa.Column("settings_json", sa.JSON(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uk_crawl_source_code"),
    )

    # 2. crawl_schedule
    op.create_table(
        "crawl_schedule",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("cron_expression", sa.String(length=100), nullable=False),
        sa.Column("search_condition", sa.JSON(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["crawl_source.id"], name="fk_schedule_source"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_schedule_next_run", "crawl_schedule", ["enabled", "next_run_at"])

    # 3. crawl_job
    op.create_table(
        "crawl_job",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("schedule_id", sa.BigInteger(), nullable=True),
        sa.Column("job_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="PENDING", nullable=False),
        sa.Column("priority", sa.SmallInteger(), server_default="100", nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("attempt_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("maximum_attempts", sa.SmallInteger(), server_default="3", nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["schedule_id"], ["crawl_schedule.id"], name="fk_job_schedule"),
        sa.ForeignKeyConstraint(["source_id"], ["crawl_source.id"], name="fk_job_source"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_job_polling", "crawl_job", ["status", "next_retry_at", "priority", "queued_at"])
    op.create_index("idx_job_source_status", "crawl_job", ["source_id", "status"])

    # 4. apartment_complex
    op.create_table(
        "apartment_complex",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("official_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("sido_code", sa.String(length=10), nullable=True),
        sa.Column("sigungu_code", sa.String(length=10), nullable=True),
        sa.Column("legal_dong_code", sa.String(length=20), nullable=True),
        sa.Column("sido_name", sa.String(length=50), nullable=True),
        sa.Column("sigungu_name", sa.String(length=100), nullable=True),
        sa.Column("legal_dong_name", sa.String(length=100), nullable=True),
        sa.Column("road_address", sa.String(length=500), nullable=True),
        sa.Column("lot_address", sa.String(length=500), nullable=True),
        sa.Column("approval_date", sa.Date(), nullable=True),
        sa.Column("construction_year", sa.SmallInteger(), nullable=True),
        sa.Column("household_count", sa.Integer(), nullable=True),
        sa.Column("building_count", sa.SmallInteger(), nullable=True),
        sa.Column("highest_floor", sa.SmallInteger(), nullable=True),
        sa.Column("parking_count", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_complex_region", "apartment_complex", ["sido_code", "sigungu_code", "legal_dong_code"])
    op.create_index("idx_complex_name", "apartment_complex", ["normalized_name"])
    op.create_index("idx_complex_build_household", "apartment_complex", ["construction_year", "household_count"])

    # 5. complex_alias
    op.create_table(
        "complex_alias",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("complex_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("alias_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("match_method", sa.String(length=30), nullable=False),
        sa.Column("match_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("manually_verified", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["complex_id"], ["apartment_complex.id"], name="fk_alias_complex"),
        sa.ForeignKeyConstraint(["source_id"], ["crawl_source.id"], name="fk_alias_source"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "normalized_alias", name="uk_alias_source_name"),
    )
    op.create_index("idx_alias_normalized", "complex_alias", ["normalized_alias"])

    # 6. listing
    op.create_table(
        "listing",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("external_listing_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("complex_id", sa.BigInteger(), nullable=True),
        sa.Column("complex_name_raw", sa.String(length=255), nullable=True),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("sale_price", sa.BigInteger(), nullable=True),
        sa.Column("deposit", sa.BigInteger(), nullable=True),
        sa.Column("monthly_rent", sa.BigInteger(), nullable=True),
        sa.Column("exclusive_area", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("supply_area", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("floor_number", sa.SmallInteger(), nullable=True),
        sa.Column("floor_group", sa.String(length=20), nullable=True),
        sa.Column("total_floor", sa.SmallInteger(), nullable=True),
        sa.Column("direction", sa.String(length=30), nullable=True),
        sa.Column("address_raw", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mortgage_status", sa.String(length=30), server_default="UNKNOWN", nullable=False),
        sa.Column("mortgage_amount", sa.BigInteger(), nullable=True),
        sa.Column("mortgage_raw_text", sa.String(length=1000), nullable=True),
        sa.Column("mortgage_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("listing_status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("source_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("missing_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["complex_id"], ["apartment_complex.id"], name="fk_listing_complex"),
        sa.ForeignKeyConstraint(["source_id"], ["crawl_source.id"], name="fk_listing_source"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_listing_id", name="uk_listing_source_external"),
    )
    op.create_index("idx_listing_search_sale", "listing", ["transaction_type", "listing_status", "sale_price"])
    op.create_index("idx_listing_search_rent", "listing", ["transaction_type", "listing_status", "deposit", "monthly_rent"])
    op.create_index("idx_listing_complex_status", "listing", ["complex_id", "listing_status", "last_seen_at"])
    op.create_index("idx_listing_mortgage", "listing", ["mortgage_status", "listing_status"])
    op.create_index("idx_listing_recent", "listing", ["listing_status", "first_seen_at"])

    # 7. listing_snapshot
    op.create_table(
        "listing_snapshot",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("sale_price", sa.BigInteger(), nullable=True),
        sa.Column("deposit", sa.BigInteger(), nullable=True),
        sa.Column("monthly_rent", sa.BigInteger(), nullable=True),
        sa.Column("mortgage_status", sa.String(length=30), nullable=False),
        sa.Column("description_hash", sa.String(length=64), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listing.id"], name="fk_snapshot_listing"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_snapshot_listing_time", "listing_snapshot", ["listing_id", "captured_at"])


def downgrade() -> None:
    op.drop_index("idx_snapshot_listing_time", table_name="listing_snapshot")
    op.drop_table("listing_snapshot")

    op.drop_index("idx_listing_recent", table_name="listing")
    op.drop_index("idx_listing_mortgage", table_name="listing")
    op.drop_index("idx_listing_complex_status", table_name="listing")
    op.drop_index("idx_listing_search_rent", table_name="listing")
    op.drop_index("idx_listing_search_sale", table_name="listing")
    op.drop_table("listing")

    op.drop_index("idx_alias_normalized", table_name="complex_alias")
    op.drop_table("complex_alias")

    op.drop_index("idx_complex_build_household", table_name="apartment_complex")
    op.drop_index("idx_complex_name", table_name="apartment_complex")
    op.drop_index("idx_complex_region", table_name="apartment_complex")
    op.drop_table("apartment_complex")

    op.drop_index("idx_job_source_status", table_name="crawl_job")
    op.drop_index("idx_job_polling", table_name="crawl_job")
    op.drop_table("crawl_job")

    op.drop_index("idx_schedule_next_run", table_name="crawl_schedule")
    op.drop_table("crawl_schedule")

    op.drop_table("crawl_source")
