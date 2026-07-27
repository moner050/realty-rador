"""Add a group-search covering index while retaining the foreign-key index.

Revision ID: 004_listing_group_cover
Revises: 003_listing_detail_enrichment
Create Date: 2026-07-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "004_listing_group_cover"
down_revision = "003_listing_detail_enrichment"
branch_labels = None
depends_on = None


GROUP_COVER_COLUMNS = (
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
)


def _is_mysql() -> bool:
    return op.get_context().dialect.name == "mysql"


def _analyze_listing_current() -> None:
    if _is_mysql():
        op.execute(sa.text("ANALYZE TABLE listing_current"))


def _set_safe_lock_wait_timeout() -> None:
    if _is_mysql():
        op.execute(sa.text("SET SESSION lock_wait_timeout = 60"))


def _mysql_index_exists() -> bool | None:
    context = op.get_context()
    if context.as_sql:
        return None
    row = op.get_bind().execute(
        sa.text(
            "SELECT 1 "
            "FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'listing_current' "
            "AND index_name = 'ix_listing_group_cover' "
            "LIMIT 1"
        )
    ).first()
    return row is not None


def upgrade() -> None:
    if not _is_mysql():
        op.create_index(
            "ix_listing_group_cover",
            "listing_current",
            list(GROUP_COVER_COLUMNS),
        )
        return

    column_sql = ", ".join(GROUP_COVER_COLUMNS)
    _set_safe_lock_wait_timeout()
    if _mysql_index_exists() is not True:
        op.execute(
            sa.text(
                f"ALTER TABLE listing_current "
                f"ADD INDEX ix_listing_group_cover ({column_sql}), "
                "ALGORITHM=INPLACE, LOCK=NONE"
            )
        )
    _analyze_listing_current()


def downgrade() -> None:
    if _is_mysql():
        _set_safe_lock_wait_timeout()
        if _mysql_index_exists() is not False:
            op.execute(
                sa.text(
                    "ALTER TABLE listing_current "
                    "DROP INDEX ix_listing_group_cover, "
                    "ALGORITHM=INPLACE, LOCK=NONE"
                )
            )
        _analyze_listing_current()
        return

    op.drop_index("ix_listing_group_cover", table_name="listing_current")
