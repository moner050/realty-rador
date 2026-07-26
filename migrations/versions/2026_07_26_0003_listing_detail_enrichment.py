"""Add materialized SITE_A listing detail fields.

Revision ID: 003_listing_detail_enrichment
Revises: 002_listing_mortgage_enrichment
Create Date: 2026-07-26 03:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "003_listing_detail_enrichment"
down_revision = "002_listing_mortgage_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listing_current", sa.Column("is_direct_trade", sa.Boolean(), nullable=True))
    op.add_column("listing_current", sa.Column("is_safe_lessor_hug", sa.Boolean(), nullable=True))
    op.add_column("listing_current", sa.Column("room_count", mysql.TINYINT(unsigned=True), nullable=True))
    op.add_column("listing_current", sa.Column("bathroom_count", mysql.TINYINT(unsigned=True), nullable=True))
    op.add_column("listing_current", sa.Column("parking_possible", sa.Boolean(), nullable=True))
    op.add_column("listing_current", sa.Column("parking_per_household_x100", mysql.INTEGER(unsigned=True), nullable=True))
    op.add_column("listing_current", sa.Column("monthly_management_cost", mysql.INTEGER(unsigned=True), nullable=True))
    op.add_column("listing_current", sa.Column("move_in_available_on", sa.Date(), nullable=True))
    op.add_column("listing_current", sa.Column("nearest_subway_walk_minutes", mysql.SMALLINT(unsigned=True), nullable=True))
    op.add_column("listing_current", sa.Column("detail_checked_at", mysql.DATETIME(fsp=6), nullable=True))
    op.create_index(
        "ix_listing_move_in",
        "listing_current",
        ["lifecycle", "is_short_term", "move_in_available_on", "article_id"],
    )
    op.create_index(
        "ix_listing_subway_walk",
        "listing_current",
        ["lifecycle", "is_short_term", "nearest_subway_walk_minutes", "article_id"],
    )
    op.create_index(
        "ix_listing_management_cost",
        "listing_current",
        ["lifecycle", "is_short_term", "monthly_management_cost", "article_id"],
    )
    op.create_index("ix_listing_detail_pending", "listing_current", ["detail_checked_at", "article_id"])


def downgrade() -> None:
    for index_name in (
        "ix_listing_detail_pending",
        "ix_listing_management_cost",
        "ix_listing_subway_walk",
        "ix_listing_move_in",
    ):
        op.drop_index(index_name, table_name="listing_current")
    for column_name in (
        "detail_checked_at",
        "nearest_subway_walk_minutes",
        "move_in_available_on",
        "monthly_management_cost",
        "parking_per_household_x100",
        "parking_possible",
        "bathroom_count",
        "room_count",
        "is_safe_lessor_hug",
        "is_direct_trade",
    ):
        op.drop_column("listing_current", column_name)
