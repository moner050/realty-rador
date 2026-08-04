"""Add durable claims for listing detail enrichment.

Revision ID: 0010_detail_enrichment_claim
Revises: 0009_complex_geocode
Create Date: 2026-08-04 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "0010_detail_enrichment_claim"
down_revision: Union[str, None] = "0009_complex_geocode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listing_current", sa.Column("detail_claim_token", sa.String(32), nullable=True))
    op.add_column("listing_current", sa.Column("detail_claimed_at", mysql.DATETIME(fsp=6), nullable=True))
    op.create_index(
        "ix_listing_detail_claim",
        "listing_current",
        ["lifecycle", "detail_checked_at", "detail_claimed_at", "article_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_listing_detail_claim", table_name="listing_current")
    op.drop_column("listing_current", "detail_claimed_at")
    op.drop_column("listing_current", "detail_claim_token")
