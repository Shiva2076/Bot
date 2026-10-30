from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from config import settings
from database import Base
from models import journal, signal, stock, trade  # noqa: F401
from models import market_snapshot, prediction_log, premarket_report, strategy_signal  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_database_url() -> str:
    """Build a psycopg2 URL for Alembic without altering credential encoding."""
    url = settings.database_url
    async_prefix = "postgresql+asyncpg://"
    plain_prefix = "postgresql://"
    sync_prefix = "postgresql+psycopg2://"
    if url.startswith(async_prefix):
        return sync_prefix + url[len(async_prefix):]
    if url.startswith(sync_prefix):
        return url
    if url.startswith(plain_prefix):
        return sync_prefix + url[len(plain_prefix):]
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _sync_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
