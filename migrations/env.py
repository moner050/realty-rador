from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from realty_radar.config import settings
from realty_radar.infrastructure.database.models import Base

# Alembic 설정 객체
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 동적 DB URL 설정
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """오프라인 마이그레이션 실행."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """온라인 마이그레이션 실행."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
