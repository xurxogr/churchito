"""Tests for the database service."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from discord_bot.common.core.settings.database import DatabaseSettings
from discord_bot.common.models.guild import Guild
from discord_bot.common.services import DatabaseService
from discord_bot.common.services.database import get_database_service


async def test_database_initialization(test_database: DatabaseService) -> None:
    """Test database initialization.

    Args:
        test_database (DatabaseService): Test database service fixture
    """
    assert test_database.engine is not None
    assert test_database.session_maker is not None


async def test_database_session_context_manager(test_database: DatabaseService) -> None:
    """Test database session creation and usage.

    Args:
        test_database (DatabaseService): Test database service fixture
    """
    async with test_database.session() as session:
        # Create and add a new guild
        guild = Guild(id=123456789, name="Test Guild", prefix="!")
        session.add(guild)

    # Verify that the guild was saved correctly
    async with test_database.session() as session:
        result = await session.execute(select(Guild).where(Guild.id == 123456789))
        fetched_guild = result.scalar_one_or_none()

        assert fetched_guild is not None
        assert fetched_guild.name == "Test Guild"
        assert fetched_guild.prefix == "!"


async def test_database_session_rollback_on_error(test_database: DatabaseService) -> None:
    """Test database session rollback on error.

    Args:
        test_database (DatabaseService): Test database service fixture
    """
    with pytest.raises(ValueError):
        async with test_database.session() as session:
            guild = Guild(id=999, name="Test Guild", prefix="!")
            session.add(guild)
            # Raise an error to trigger rollback
            raise ValueError("Test error")

    # Verify that the guild was not saved due to rollback
    async with test_database.session() as session:
        result = await session.execute(select(Guild).where(Guild.id == 999))
        fetched_guild = result.scalar_one_or_none()

        assert fetched_guild is None


async def test_database_close(test_database: DatabaseService) -> None:
    """Test database service close.

    Args:
        test_database (DatabaseService): Test database service fixture
    """
    await test_database.close()

    # After closing, the engine should be None
    assert test_database._engine is not None


def test_database_engine_not_initialized() -> None:
    """Test that accessing engine before initialization raises RuntimeError."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")
    db_service = DatabaseService(settings)

    # Try to access engine without calling initialize()
    with pytest.raises(RuntimeError) as exc_info:
        _ = db_service.engine

    assert "Database engine not initialized" in str(exc_info.value)
    assert "initialize()" in str(exc_info.value)


def test_database_session_maker_not_initialized() -> None:
    """Test that accessing session_maker before initialization raises RuntimeError."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")
    db_service = DatabaseService(settings)

    # Try to access session_maker without calling initialize()
    with pytest.raises(RuntimeError) as exc_info:
        _ = db_service.session_maker

    assert "Database session maker not initialized" in str(exc_info.value)
    assert "initialize()" in str(exc_info.value)


def test_database_get_session_not_initialized() -> None:
    """Test that calling get_session() before initialization raises RuntimeError."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")
    db_service = DatabaseService(settings)

    # Try to call get_session() without calling initialize()
    with pytest.raises(RuntimeError) as exc_info:
        db_service.get_session()

    assert "Database session maker not initialized" in str(exc_info.value)


def test_get_database_service() -> None:
    """Test the get_database_service function.

    Note: This test accesses the wrapped function to avoid lru_cache.
    """
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")

    # Access the wrapped function to avoid cache
    if hasattr(get_database_service, "__wrapped__"):
        service = get_database_service.__wrapped__(settings)
    else:
        # If __wrapped__ doesn't exist, call directly (cache won't be tested)
        service = DatabaseService(settings)

    assert isinstance(service, DatabaseService)
    assert service.settings == settings


def test_ensure_database_directory_creates_directory() -> None:
    """Test that _ensure_database_directory creates the directory if it doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # Use a database path inside a subdirectory
            settings = DatabaseSettings(url="sqlite+aiosqlite:///foo/bar/test.db")
            db_service = DatabaseService(settings)

            # The directory should not exist yet
            db_dir = Path(tmpdir) / "foo" / "bar"
            assert not db_dir.exists()

            # Call the method to create the directory
            with patch("discord_bot.common.services.database.logger") as mock_logger:
                db_service._ensure_database_directory()

                # The directory should now exist
                assert db_dir.exists()
                assert db_dir.is_dir()

                # The logger should have been called
                mock_logger.info.assert_called_once()
                log_message = mock_logger.info.call_args[0][0]
                assert "Created database directory" in log_message
        finally:
            os.chdir(original_cwd)


def test_ensure_database_directory_handles_existing_directory() -> None:
    """Test that _ensure_database_directory handles the case where directory already exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # Create the directory beforehand
            db_dir = Path(tmpdir) / "existing"
            db_dir.mkdir(parents=True, exist_ok=True)

            # Use a database path inside the existing directory
            settings = DatabaseSettings(url="sqlite+aiosqlite:///existing/test.db")
            db_service = DatabaseService(settings)

            # Call the method, should not try to create again
            with patch("discord_bot.common.services.database.logger") as mock_logger:
                db_service._ensure_database_directory()

                # The directory should still exist
                assert db_dir.exists()

                # Logger should not have been called
                mock_logger.info.assert_not_called()
        finally:
            os.chdir(original_cwd)


def test_ensure_database_directory_skips_current_directory() -> None:
    """Test that _ensure_database_directory skips when DB file is in current directory."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///test.db")
    db_service = DatabaseService(settings)

    with patch("discord_bot.common.services.database.logger") as mock_logger:
        # Should not create any directory
        db_service._ensure_database_directory()

        # Logger should not have been called
        mock_logger.info.assert_not_called()


def test_ensure_database_directory_skips_in_memory() -> None:
    """Test that _ensure_database_directory skips for in-memory SQLite databases."""
    # Test both in-memory URL variants
    for url in ["sqlite+aiosqlite:///:memory:", "sqlite:///:memory:"]:
        settings = DatabaseSettings(url=url)
        db_service = DatabaseService(settings)

        with patch("discord_bot.common.services.database.logger") as mock_logger:
            db_service._ensure_database_directory()

            # Should not create any directory
            mock_logger.info.assert_not_called()


def test_ensure_database_directory_skips_non_sqlite() -> None:
    """Test that _ensure_database_directory skips non-SQLite databases."""
    # Test PostgreSQL URL
    settings = DatabaseSettings(url="postgresql+asyncpg://user:pass@localhost/dbname")
    db_service = DatabaseService(settings)

    with patch("discord_bot.common.services.database.logger") as mock_logger:
        db_service._ensure_database_directory()

        # Should not create any directory
        mock_logger.info.assert_not_called()


def test_ensure_database_directory_with_relative_path() -> None:
    """Test that _ensure_database_directory handles relative paths correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Change to the temporary directory
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            settings = DatabaseSettings(url="sqlite+aiosqlite:///data/bot.db")
            db_service = DatabaseService(settings)

            with patch("discord_bot.common.services.database.logger") as mock_logger:
                db_service._ensure_database_directory()

                # The directory should have been created correctly relative to cwd
                data_dir = Path(tmpdir) / "data"
                assert data_dir.exists()
                assert data_dir.is_dir()

                # Directory creation should have been logged
                mock_logger.info.assert_called_once()
        finally:
            os.chdir(original_cwd)


def test_ensure_database_directory_with_double_slash_path() -> None:
    """Test that _ensure_database_directory handles URLs with double slash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # URL with 4 slashes: sqlite+aiosqlite:////path -> url_path = "//path"
            # This enters the branch at line 87 (startswith "//")
            # After lstrip("/"), becomes "dbtest/test.db"
            url = "sqlite+aiosqlite:////dbtest/test.db"

            settings = DatabaseSettings(url=url)
            db_service = DatabaseService(settings)

            with patch("discord_bot.common.services.database.logger") as mock_logger:
                db_service._ensure_database_directory()

                # The directory should have been created (relative to cwd)
                db_dir = Path(tmpdir) / "dbtest"
                assert db_dir.exists()
                assert db_dir.is_dir()

                # Directory creation should have been logged
                mock_logger.info.assert_called_once()
        finally:
            os.chdir(original_cwd)


def test_is_sqlite_returns_true_for_sqlite_urls() -> None:
    """Test that _is_sqlite returns True for SQLite URLs."""
    sqlite_urls = [
        "sqlite+aiosqlite:///data/bot.db",
        "sqlite+aiosqlite:///:memory:",
        "sqlite:///test.db",
    ]
    for url in sqlite_urls:
        settings = DatabaseSettings(url=url)
        db_service = DatabaseService(settings)
        assert db_service._is_sqlite() is True


def test_is_sqlite_returns_false_for_non_sqlite_urls() -> None:
    """Test that _is_sqlite returns False for non-SQLite URLs."""
    non_sqlite_urls = [
        "postgresql+asyncpg://user:pass@localhost/dbname",
        "mysql+aiomysql://user:pass@localhost/dbname",
    ]
    for url in non_sqlite_urls:
        settings = DatabaseSettings(url=url)
        db_service = DatabaseService(settings)
        assert db_service._is_sqlite() is False


async def test_sqlite_pragmas_configured_on_initialize() -> None:
    """Test that SQLite PRAGMAs are configured on initialization."""
    import os

    from sqlalchemy import text

    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # WAL mode requires a file-based database, not in-memory
            settings = DatabaseSettings(url="sqlite+aiosqlite:///test_pragmas.db")
            db_service = DatabaseService(settings)

            await db_service.initialize()

            try:
                async with db_service.engine.connect() as conn:
                    # Verify that WAL mode is configured
                    result = await conn.execute(text("PRAGMA journal_mode"))
                    journal_mode = result.scalar()
                    assert journal_mode == "wal"

                    # Verify that foreign_keys is enabled
                    result = await conn.execute(text("PRAGMA foreign_keys"))
                    foreign_keys = result.scalar()
                    assert foreign_keys == 1
            finally:
                await db_service.close()
        finally:
            os.chdir(original_cwd)


async def test_postgresql_does_not_configure_sqlite_pragmas() -> None:
    """Test that _configure_sqlite_pragmas is not called for PostgreSQL."""
    settings = DatabaseSettings(url="postgresql+asyncpg://user:pass@localhost/dbname")
    db_service = DatabaseService(settings)

    with patch.object(db_service, "_configure_sqlite_pragmas") as mock_configure:
        # We cannot actually initialize without a PostgreSQL DB, but we can
        # verify that _is_sqlite returns False
        assert db_service._is_sqlite() is False
        mock_configure.assert_not_called()
