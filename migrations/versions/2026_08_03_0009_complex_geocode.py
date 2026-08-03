"""단지별 검증 좌표와 지오코딩 상태 추가.

Revision ID: 0009_complex_geocode
Revises: 0008_scheduler_log
Create Date: 2026-08-03 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "0009_complex_geocode"
down_revision: Union[str, None] = "0008_scheduler_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("complex_current", sa.Column("latitude", sa.Numeric(10, 7), nullable=True))
    op.add_column("complex_current", sa.Column("longitude", sa.Numeric(10, 7), nullable=True))
    op.add_column(
        "complex_current",
        sa.Column("geocode_status", mysql.TINYINT(unsigned=True), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("complex_current", sa.Column("geocoded_address_hash", mysql.BINARY(16), nullable=True))
    op.add_column("complex_current", sa.Column("geocoded_at", mysql.DATETIME(fsp=6), nullable=True))
    op.add_column("complex_current", sa.Column("geocode_attempted_at", mysql.DATETIME(fsp=6), nullable=True))
    op.add_column("complex_current", sa.Column("geocode_retry_after", mysql.DATETIME(fsp=6), nullable=True))


def downgrade() -> None:
    op.drop_column("complex_current", "geocode_retry_after")
    op.drop_column("complex_current", "geocode_attempted_at")
    op.drop_column("complex_current", "geocoded_at")
    op.drop_column("complex_current", "geocoded_address_hash")
    op.drop_column("complex_current", "geocode_status")
    op.drop_column("complex_current", "longitude")
    op.drop_column("complex_current", "latitude")
