"""Add resumable mortgage-enrichment state to the v2 hot table.

Revision ID: 002_listing_mortgage_enrichment
Revises: 001_site_a_v2
Create Date: 2026-07-26 00:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "002_listing_mortgage_enrichment"
down_revision = "001_site_a_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listing_current", sa.Column("mortgage_checked_at", mysql.DATETIME(fsp=6), nullable=True))
    op.create_index("ix_listing_mortgage_pending", "listing_current", ["mortgage_checked_at", "article_id"])


def downgrade() -> None:
    op.drop_index("ix_listing_mortgage_pending", table_name="listing_current")
    op.drop_column("listing_current", "mortgage_checked_at")
