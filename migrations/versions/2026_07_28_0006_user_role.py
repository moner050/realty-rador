"""Add role column to user_account table.

Revision ID: 006_user_role
Revises: 005_user_accounts
Create Date: 2026-07-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_user_role"
down_revision: Union[str, None] = "005_user_accounts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_account",
        sa.Column("role", sa.String(length=20), server_default="USER", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("user_account", "role")
