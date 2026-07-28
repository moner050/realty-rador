"""User account schema migration contracts."""
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect


ROOT = Path(__file__).resolve().parents[2]


def _get_revision(revision_id: str):
    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision(revision_id)
    assert revision is not None
    return revision.module


def test_user_accounts_migration_creates_and_removes_account_tables():
    revision = _get_revision("005_user_accounts")
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            revision.upgrade()

        inspector = inspect(connection)
        assert {"user_account", "user_preference"}.issubset(inspector.get_table_names())

        account_columns = {column["name"] for column in inspector.get_columns("user_account")}
        assert account_columns == {"id", "username", "password_hash", "created_at"}
        assert any(
            index["name"] == "ux_user_username" and index["unique"]
            for index in inspector.get_indexes("user_account")
        )

        preference_columns = {column["name"] for column in inspector.get_columns("user_preference")}
        assert preference_columns == {
            "user_id",
            "favorites_json",
            "filters_json",
            "loan_profile_json",
            "updated_at",
        }
        foreign_keys = inspector.get_foreign_keys("user_preference")
        assert foreign_keys == [
            {
                "name": None,
                "constrained_columns": ["user_id"],
                "referred_schema": None,
                "referred_table": "user_account",
                "referred_columns": ["id"],
                "options": {"ondelete": "CASCADE"},
            }
        ]

        with Operations.context(context):
            revision.downgrade()

        remaining_tables = set(inspect(connection).get_table_names())
        assert "user_account" not in remaining_tables
        assert "user_preference" not in remaining_tables


def test_user_role_migration_adds_and_drops_role_column():
    rev_005 = _get_revision("005_user_accounts")
    rev_006 = _get_revision("006_user_role")
    engine = create_engine("sqlite://")

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            rev_005.upgrade()
            rev_006.upgrade()

        inspector = inspect(connection)
        columns = {column["name"]: column for column in inspector.get_columns("user_account")}
        assert "role" in columns
        assert columns["role"]["default"] == "'USER'" or columns["role"]["default"] == "USER"

        with Operations.context(context):
            rev_006.downgrade()

        columns_after = {column["name"] for column in inspect(connection).get_columns("user_account")}
        assert "role" not in columns_after
