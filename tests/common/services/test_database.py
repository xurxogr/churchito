"""Tests for database service."""

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
        test_database: Test database service fixture
    """
    assert test_database.engine is not None
    assert test_database.session_maker is not None


async def test_database_session_context_manager(test_database: DatabaseService) -> None:
    """Test database session context manager.

    Args:
        test_database: Test database service fixture
    """
    async with test_database.session() as session:
        # Create a test guild
        guild = Guild(id=123456789, name="Test Guild", prefix="!")
        session.add(guild)

    # Query the guild in a new session
    async with test_database.session() as session:
        result = await session.execute(select(Guild).where(Guild.id == 123456789))
        fetched_guild = result.scalar_one_or_none()

        assert fetched_guild is not None
        assert fetched_guild.name == "Test Guild"
        assert fetched_guild.prefix == "!"


async def test_database_session_rollback_on_error(test_database: DatabaseService) -> None:
    """Test that session rolls back on error.

    Args:
        test_database: Test database service fixture
    """
    with pytest.raises(ValueError):
        async with test_database.session() as session:
            guild = Guild(id=999, name="Test Guild", prefix="!")
            session.add(guild)
            # Raise an error to trigger rollback
            raise ValueError("Test error")

    # Verify the guild was not saved
    async with test_database.session() as session:
        result = await session.execute(select(Guild).where(Guild.id == 999))
        fetched_guild = result.scalar_one_or_none()

        assert fetched_guild is None


async def test_database_close(test_database: DatabaseService) -> None:
    """Test database close.

    Args:
        test_database: Test database service fixture
    """
    await test_database.close()

    # Engine should still exist but be disposed
    assert test_database._engine is not None


def test_database_engine_not_initialized() -> None:
    """Test that accessing engine before initialization raises RuntimeError."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")
    db_service = DatabaseService(settings)

    # Try to access engine without calling initialize()
    with pytest.raises(RuntimeError) as exc_info:
        _ = db_service.engine

    assert "Motor de base de datos no inicializado" in str(exc_info.value)
    assert "initialize()" in str(exc_info.value)


def test_database_session_maker_not_initialized() -> None:
    """Test that accessing session_maker before initialization raises RuntimeError."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")
    db_service = DatabaseService(settings)

    # Try to access session_maker without calling initialize()
    with pytest.raises(RuntimeError) as exc_info:
        _ = db_service.session_maker

    assert "Creador de sesiones de base de datos no inicializado" in str(exc_info.value)
    assert "initialize()" in str(exc_info.value)


def test_database_get_session_not_initialized() -> None:
    """Test that get_session() fails when session_maker is not initialized."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")
    db_service = DatabaseService(settings)

    # get_session() will try to access session_maker property, which should raise
    with pytest.raises(RuntimeError) as exc_info:
        db_service.get_session()

    assert "Creador de sesiones de base de datos no inicializado" in str(exc_info.value)


def test_get_database_service() -> None:
    """Test the get_database_service function logic (line 127).

    Note: The function uses @lru_cache which requires hashable arguments,
    but DatabaseSettings is not hashable. We test the underlying function
    by accessing __wrapped__ to bypass the cache.
    """
    settings = DatabaseSettings(url="sqlite+aiosqlite:///:memory:")

    # Access the wrapped function (bypasses lru_cache)
    if hasattr(get_database_service, "__wrapped__"):
        service = get_database_service.__wrapped__(settings)
    else:
        # If not wrapped (shouldn't happen), call directly
        service = DatabaseService(settings)

    assert isinstance(service, DatabaseService)
    assert service.settings == settings


def test_ensure_database_directory_creates_directory() -> None:
    """Test that _ensure_database_directory creates missing directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # Use a relative path that doesn't exist
            settings = DatabaseSettings(url="sqlite+aiosqlite:///foo/bar/test.db")
            db_service = DatabaseService(settings)

            # Directory should not exist yet
            db_dir = Path(tmpdir) / "foo" / "bar"
            assert not db_dir.exists()

            # Call the method
            with patch("discord_bot.common.services.database.logger") as mock_logger:
                db_service._ensure_database_directory()

                # Directory should now exist
                assert db_dir.exists()
                assert db_dir.is_dir()

                # Logger should have been called
                mock_logger.info.assert_called_once()
                log_message = mock_logger.info.call_args[0][0]
                assert "Creado directorio de base de datos" in log_message
        finally:
            os.chdir(original_cwd)


def test_ensure_database_directory_handles_existing_directory() -> None:
    """Test that _ensure_database_directory doesn't fail if directory exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            # Create the directory first
            db_dir = Path(tmpdir) / "existing"
            db_dir.mkdir(parents=True, exist_ok=True)

            # Use the existing directory
            settings = DatabaseSettings(url="sqlite+aiosqlite:///existing/test.db")
            db_service = DatabaseService(settings)

            # Call the method - should not fail
            with patch("discord_bot.common.services.database.logger") as mock_logger:
                db_service._ensure_database_directory()

                # Directory should still exist
                assert db_dir.exists()

                # Logger should NOT be called since directory already existed
                mock_logger.info.assert_not_called()
        finally:
            os.chdir(original_cwd)


def test_ensure_database_directory_skips_current_directory() -> None:
    """Test that _ensure_database_directory skips if parent is current directory."""
    settings = DatabaseSettings(url="sqlite+aiosqlite:///test.db")
    db_service = DatabaseService(settings)

    with patch("discord_bot.common.services.database.logger") as mock_logger:
        # Should not try to create "." directory
        db_service._ensure_database_directory()

        # Logger should not be called
        mock_logger.info.assert_not_called()


def test_ensure_database_directory_skips_in_memory() -> None:
    """Test that _ensure_database_directory skips for in-memory databases."""
    # Test both :memory: formats
    for url in ["sqlite+aiosqlite:///:memory:", "sqlite:///:memory:"]:
        settings = DatabaseSettings(url=url)
        db_service = DatabaseService(settings)

        with patch("discord_bot.common.services.database.logger") as mock_logger:
            db_service._ensure_database_directory()

            # Should not create any directory or log anything
            mock_logger.info.assert_not_called()


def test_ensure_database_directory_skips_non_sqlite() -> None:
    """Test that _ensure_database_directory skips for non-SQLite databases."""
    # Test PostgreSQL URL
    settings = DatabaseSettings(url="postgresql+asyncpg://user:pass@localhost/dbname")
    db_service = DatabaseService(settings)

    with patch("discord_bot.common.services.database.logger") as mock_logger:
        db_service._ensure_database_directory()

        # Should not create any directory or log anything
        mock_logger.info.assert_not_called()


def test_ensure_database_directory_with_relative_path() -> None:
    """Test _ensure_database_directory with a simple relative path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Change to temp directory to test relative paths
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            settings = DatabaseSettings(url="sqlite+aiosqlite:///data/bot.db")
            db_service = DatabaseService(settings)

            with patch("discord_bot.common.services.database.logger") as mock_logger:
                db_service._ensure_database_directory()

                # Directory should be created relative to current dir
                data_dir = Path(tmpdir) / "data"
                assert data_dir.exists()
                assert data_dir.is_dir()

                # Logger should have been called
                mock_logger.info.assert_called_once()
        finally:
            os.chdir(original_cwd)
