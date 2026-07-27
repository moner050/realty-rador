"""Listing group covering-index model and migration contracts."""
from io import StringIO
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, MetaData, Table, create_engine, inspect

from realty_radar.infrastructure.database.models import ListingCurrent


ROOT = Path(__file__).resolve().parents[2]
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
LEGACY_COMPLEX_COLUMNS = (
    "complex_id",
    "lifecycle",
    "is_short_term",
    "primary_price",
    "article_id",
)


def _group_cover_revision():
    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    try:
        revision = scripts.get_revision("004_listing_group_cover")
    except CommandError:
        pytest.fail("004_listing_group_cover migration is missing", pytrace=False)
    assert revision is not None
    return revision.module


def _legacy_listing_table(metadata: MetaData) -> Table:
    table = Table(
        "listing_current",
        metadata,
        Column("article_id", Integer, primary_key=True),
        Column("complex_id", Integer, nullable=False),
        Column("region_code", Integer, nullable=False),
        Column("sido_code", Integer, nullable=False),
        Column("sigungu_code", Integer, nullable=False),
        Column("construction_year", Integer, nullable=False),
        Column("household_count", Integer, nullable=False),
        Column("trade_type", Integer, nullable=False),
        Column("primary_price", Integer, nullable=False),
        Column("monthly_rent", Integer, nullable=False),
        Column("exclusive_area_x100", Integer, nullable=False),
        Column("lifecycle", Integer, nullable=False),
        Column("is_short_term", Boolean, nullable=False),
        Column("first_seen_at", DateTime, nullable=False),
    )
    Index("ix_listing_complex", *[table.c[name] for name in LEGACY_COMPLEX_COLUMNS])
    return table


def _index_columns(bind) -> dict[str, tuple[str, ...]]:
    return {
        index["name"]: tuple(index["column_names"])
        for index in inspect(bind).get_indexes("listing_current")
    }


def test_listing_current_metadata_keeps_fk_index_and_adds_group_cover():
    indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in ListingCurrent.__table__.indexes
    }

    assert indexes["ix_listing_complex"] == LEGACY_COMPLEX_COLUMNS
    assert indexes["ix_listing_group_cover"] == GROUP_COVER_COLUMNS


def test_listing_group_cover_migration_upgrades_and_downgrades_sqlite():
    revision = _group_cover_revision()
    engine = create_engine("sqlite://")
    metadata = MetaData()
    _legacy_listing_table(metadata)

    with engine.begin() as connection:
        metadata.create_all(connection)
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()

        upgraded_indexes = _index_columns(connection)
        assert upgraded_indexes["ix_listing_complex"] == LEGACY_COMPLEX_COLUMNS
        assert upgraded_indexes["ix_listing_group_cover"] == GROUP_COVER_COLUMNS

        with Operations.context(context):
            revision.downgrade()

        downgraded_indexes = _index_columns(connection)
        assert "ix_listing_group_cover" not in downgraded_indexes
        assert downgraded_indexes["ix_listing_complex"] == LEGACY_COMPLEX_COLUMNS


def _mysql_migration_sql(operation: str) -> str:
    revision = _group_cover_revision()
    output = StringIO()
    context = MigrationContext.configure(
        url="mysql+pymysql://",
        opts={"as_sql": True, "output_buffer": output},
    )

    with Operations.context(context):
        getattr(revision, operation)()

    return " ".join(output.getvalue().lower().split())


def test_listing_group_cover_upgrade_emits_online_mysql_add_and_analyze():
    sql = _mysql_migration_sql("upgrade")
    expected_columns = ", ".join(GROUP_COVER_COLUMNS)
    assert "set session lock_wait_timeout = 60" in sql
    assert f"add index ix_listing_group_cover ({expected_columns})" in sql
    assert "ix_listing_complex" not in sql
    assert "algorithm=inplace" in sql
    assert "lock=none" in sql
    assert "analyze table listing_current" in sql


def test_listing_group_cover_downgrade_emits_online_mysql_drop_and_analyze():
    sql = _mysql_migration_sql("downgrade")
    assert "set session lock_wait_timeout = 60" in sql
    assert "drop index ix_listing_group_cover" in sql
    assert "ix_listing_complex" not in sql
    assert "algorithm=inplace" in sql
    assert "lock=none" in sql
    assert "analyze table listing_current" in sql


def test_mysql_upgrade_retry_skips_an_already_created_cover_index(monkeypatch):
    revision = _group_cover_revision()
    statements: list[str] = []
    monkeypatch.setattr(revision, "_is_mysql", lambda: True)
    monkeypatch.setattr(revision, "_mysql_index_exists", lambda: True)
    monkeypatch.setattr(revision.op, "execute", lambda statement: statements.append(str(statement)))

    revision.upgrade()

    sql = " ".join(statements).lower()
    assert "add index ix_listing_group_cover" not in sql
    assert "analyze table listing_current" in sql


def test_mysql_downgrade_retry_skips_an_already_removed_cover_index(monkeypatch):
    revision = _group_cover_revision()
    statements: list[str] = []
    monkeypatch.setattr(revision, "_is_mysql", lambda: True)
    monkeypatch.setattr(revision, "_mysql_index_exists", lambda: False)
    monkeypatch.setattr(revision.op, "execute", lambda statement: statements.append(str(statement)))

    revision.downgrade()

    sql = " ".join(statements).lower()
    assert "drop index ix_listing_group_cover" not in sql
    assert "analyze table listing_current" in sql
