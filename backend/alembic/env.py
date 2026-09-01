"""Alembic migrations environment — async SQLAlchemy 2.x edition.

DATABASE_URL is read from app.config.settings, which in turn reads it from the
environment or the repository-root .env file.  Credentials are never hardcoded.
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.db import models  # noqa: F401 — register all ORM models before metadata is read
from app.db.base import Base

# ---------------------------------------------------------------------------
# Alembic Config object (alembic.ini values)
# ---------------------------------------------------------------------------
config = context.config

# Inject the runtime DATABASE_URL so credentials are never in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata Alembic will compare against the live database schema.
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline migrations (generate SQL script without a live connection)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations (run against a live async engine)
# ---------------------------------------------------------------------------
def _do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
