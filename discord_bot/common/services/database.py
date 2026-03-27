"""Database service for managing SQLAlchemy connections."""

import logging
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from discord_bot.common.core.settings.database import DatabaseSettings

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for managing database connections."""

    def __init__(self, settings: DatabaseSettings) -> None:
        """Initialize the database service.

        Args:
            settings (DatabaseSettings): Database configuration
        """
        self.settings = settings
        self._engine: AsyncEngine | None = None
        self._session_maker: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Get the database engine.

        Returns:
            AsyncEngine: SQLAlchemy async engine

        Raises:
            RuntimeError: If the engine is not initialized
        """
        if self._engine is None:
            raise RuntimeError("Database engine not initialized. Call initialize() first.")
        return self._engine

    @property
    def session_maker(self) -> async_sessionmaker[AsyncSession]:
        """Get the session maker.

        Returns:
            async_sessionmaker[AsyncSession]: SQLAlchemy async session maker

        Raises:
            RuntimeError: If the session maker is not initialized
        """
        if self._session_maker is None:
            raise RuntimeError("Database session maker not initialized. Call initialize() first.")
        return self._session_maker

    def _ensure_database_directory(self) -> None:
        """Ensure the database directory exists (SQLite only)."""
        # Parse URL to check if it's SQLite
        if not self.settings.url.startswith("sqlite"):
            return

        # Extract file path from SQLite URL
        # Format: sqlite+aiosqlite:///data/bot.db or sqlite:///data/bot.db
        # After split: /data/bot.db (single slash for relative, // for absolute)
        url_path = self.settings.url.split("://", 1)[-1]

        # Skip if in-memory database
        if url_path == ":memory:" or url_path.endswith(":memory:"):
            return

        # Handle absolute vs relative paths
        # sqlite://localhost//absolute/path -> //absolute/path (absolute)
        # sqlite:///relative/path -> /relative/path (relative on Unix, need to strip /)
        if url_path.startswith("//"):
            # Absolute path with host
            db_path = Path(url_path.lstrip("/"))
        else:
            # Relative path - strip single leading slash
            db_path = Path(url_path.lstrip("/"))

        # Create parent directory if it doesn't exist
        db_dir = db_path.parent
        if db_dir and str(db_dir) != "." and not db_dir.exists():
            db_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")

    def _redact_url(self, url: str) -> str:
        """Redact credentials from a database URL.

        Args:
            url (str): Connection URL

        Returns:
            str: URL with redacted credentials
        """
        # Redact password in URLs like: postgresql+asyncpg://user:password@host:port/db
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)

    def _is_sqlite(self) -> bool:
        """Check if the database is SQLite.

        Returns:
            bool: True if SQLite
        """
        return self.settings.url.startswith("sqlite")

    def _configure_sqlite_pragmas(self, engine: AsyncEngine) -> None:
        """Configure SQLite PRAGMAs for better performance and consistency.

        Args:
            engine: SQLAlchemy engine
        """

        def set_sqlite_pragma(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            # WAL mode: better performance for concurrent reads/writes
            cursor.execute("PRAGMA journal_mode=WAL")
            # Enable foreign keys (disabled by default in SQLite)
            cursor.execute("PRAGMA foreign_keys=ON")
            # Timeout for waiting when DB is locked (5 seconds)
            cursor.execute("PRAGMA busy_timeout=5000")
            # NORMAL synchronous mode is safe with WAL and faster
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        # The event is registered on the underlying sync_engine
        event.listen(engine.sync_engine, "connect", set_sqlite_pragma)

    async def initialize(self) -> None:
        """Initialize the database engine and session maker."""
        logger.info(f"Initializing database: {self._redact_url(self.settings.url)}")

        # Ensure database directory exists (for SQLite)
        self._ensure_database_directory()

        self._engine = create_async_engine(
            self.settings.url,
            echo=self.settings.echo,
            pool_recycle=self.settings.pool_recycle,
        )

        # Configure PRAGMAs for SQLite
        if self._is_sqlite():
            self._configure_sqlite_pragmas(self._engine)

        self._session_maker = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Verify connection works
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database initialized successfully")
        except Exception as e:
            await self._engine.dispose()
            self._engine = None
            self._session_maker = None
            raise RuntimeError(f"Could not connect to database: {e}") from e

    async def close(self) -> None:
        """Close database connections."""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database connections closed")

    def get_session(self) -> AsyncSession:
        """Get a new database session.

        Returns:
            AsyncSession: SQLAlchemy async session

        Note:
            The caller is responsible for committing/rolling back and closing the session.
        """
        return self.session_maker()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session context manager.

        Yields:
            AsyncSession: SQLAlchemy async session
        """
        async with self.session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


@lru_cache
def get_database_service(settings: DatabaseSettings) -> DatabaseService:
    """Get the database service singleton.

    Args:
        settings (DatabaseSettings): Database configuration

    Returns:
        DatabaseService: Database service instance
    """
    return DatabaseService(settings)
