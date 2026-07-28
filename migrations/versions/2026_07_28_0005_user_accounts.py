"""Create user account and preference tables.

Revision ID: 005_user_accounts
Revises: 004_listing_group_cover
Create Date: 2026-07-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "005_user_accounts"
down_revision: Union[str, None] = "004_listing_group_cover"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UINT = sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql")
DATETIME6 = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name if bind else ""
    ts_expr = sa.text("CURRENT_TIMESTAMP(6)") if dialect_name == "mysql" else sa.text("CURRENT_TIMESTAMP")

    op.create_table(
        "user_account",
        sa.Column("id", UINT, autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", DATETIME6, server_default=ts_expr, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ux_user_username", "user_account", ["username"], unique=True)

    op.create_table(
        "user_preference",
        sa.Column("user_id", UINT, nullable=False),
        sa.Column("favorites_json", sa.JSON(), nullable=True),
        sa.Column("filters_json", sa.JSON(), nullable=True),
        sa.Column("loan_profile_json", sa.JSON(), nullable=True),
        sa.Column("updated_at", DATETIME6, server_default=ts_expr, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user_account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    op.drop_table("user_preference")
    op.drop_index("ux_user_username", table_name="user_account")
    op.drop_table("user_account")
