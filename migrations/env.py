"""Alembic environment configuration for async SQLAlchemy."""

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from discord_bot.common.core import AppSettings

# Import all models so Alembic detects them
from discord_bot.common.models import Guild, GuildCogEnabled, GuildConfig  # noqa: F401
from discord_bot.common.models.base import Base
from discord_bot.purge.models import PurgeRecord  # noqa: F401
from discord_bot.verification.models import VerificationRequest  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# NOTE: We intentionally skip fileConfig() here to avoid overriding
# the application's logging configuration. When running from CLI,
# basic logging will still work. When running from the bot, it
# preserves the bot's logging setup.

# Use our models metadata for autogenerate
target_metadata = Base.metadata


def get_database_url() -> str:
    """Get database URL from configuration."""
    settings = AppSettings()
    # Alembic offline needs sync URL
    url = settings.database.url
    if "+aiosqlite" in url:
        url = url.replace("+aiosqlite", "")
    elif "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg")
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the provided connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # Required for SQLite
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    settings = AppSettings()

    connectable = async_engine_from_config(
        {"sqlalchemy.url": settings.database.url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
