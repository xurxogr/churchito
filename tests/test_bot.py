"""Tests for main bot class."""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from discord_bot.bot import DiscordBot
from discord_bot.common.core import AppSettings
from discord_bot.common.services import DatabaseService


@pytest.fixture
async def test_bot(
    test_settings: AppSettings, test_database: DatabaseService
) -> AsyncGenerator[DiscordBot, None]:
    """Create a test bot instance.

    Args:
        test_settings: Test application settings
        test_database: Test database service

    Returns:
        DiscordBot: Test bot instance
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        # Mock guilds and user as properties
        type(bot).guilds = PropertyMock(return_value=[])  # type: ignore[method-assign]
        mock_user = MagicMock()
        mock_user.name = "TestBot"
        mock_user.id = 123456789
        type(bot).user = PropertyMock(return_value=mock_user)  # type: ignore[method-assign]
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]
        yield bot


def test_bot_initialization(test_settings: AppSettings, test_database: DatabaseService) -> None:
    """Test bot initialization.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        assert bot.settings == test_settings
        assert bot.database == test_database
        assert bot.event_bus is not None


async def test_bot_on_ready(test_bot: DiscordBot) -> None:
    """Test bot on_ready event.

    Args:
        test_bot: Test bot instance
    """
    # Mock event bus emit
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit  # type: ignore[method-assign]

    # Call on_ready
    await test_bot.on_ready()

    # Verify event was emitted with correct data
    from discord_bot.common.enums.event_type import EventType

    mock_emit.assert_called_once_with(
        EventType.BOT_READY,
        {
            "bot_name": "TestBot",
            "bot_id": 123456789,
            "guild_count": 0,
        },
    )


async def test_bot_close(test_bot: DiscordBot) -> None:
    """Test bot close method.

    Args:
        test_bot: Test bot instance
    """
    # Mock the database close and parent close
    test_bot.database.close = AsyncMock()  # type: ignore[method-assign]

    # Mock event bus emit
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit  # type: ignore[method-assign]

    # Create a real asyncio task that can be cancelled
    async def dummy_monitor() -> None:
        await asyncio.sleep(100)  # Long sleep to simulate running task

    monitor_task = asyncio.create_task(dummy_monitor())
    test_bot._monitor_task = monitor_task

    with patch("discord_bot.bot.commands.Bot.close", new_callable=AsyncMock):
        await test_bot.close()

        # Verify shutdown event was emitted
        from discord_bot.common.enums.event_type import EventType

        mock_emit.assert_called_once_with(EventType.BOT_SHUTDOWN, {})

        # Verify monitor task was cancelled
        assert monitor_task.cancelled()

        # Verify database was closed
        test_bot.database.close.assert_called_once()


async def test_bot_setup_hook(test_settings: AppSettings, test_database: DatabaseService) -> None:
    """Test bot setup hook.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]

        # Mock the database and table creation
        test_database.initialize = AsyncMock()  # type: ignore[method-assign]

        with (
            patch.object(bot, "_create_tables", new_callable=AsyncMock) as mock_create_tables,
            patch.object(bot, "_load_cogs", new_callable=AsyncMock) as mock_load_cogs,
        ):
            await bot.setup_hook()

            # Verify all setup methods were called
            test_database.initialize.assert_called_once()
            mock_create_tables.assert_called_once()
            mock_load_cogs.assert_called_once()


async def test_bot_load_cogs_success(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test bot cog loading success.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock()  # type: ignore[method-assign]

        # Should load all cogs successfully
        await bot._load_cogs()

        # Verify load_extension was called for each cog
        assert bot.load_extension.call_count > 0
        bot.load_extension.assert_any_call("discord_bot.general.cog")


async def test_bot_load_cogs_with_error(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test bot cog loading with errors.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock(side_effect=Exception("Test error"))  # type: ignore[method-assign]

        # Should not raise even if cog loading fails
        await bot._load_cogs()

        # Verify load_extension was called for each cog
        assert bot.load_extension.call_count > 0


async def test_bot_create_tables(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test database table creation.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        # Mock database engine and connection
        mock_conn = AsyncMock()
        mock_begin_context = AsyncMock()
        mock_begin_context.__aenter__.return_value = mock_conn
        mock_begin_context.__aexit__.return_value = None

        # Mock the engine's begin method
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_begin_context

        # Patch the engine property
        with patch.object(
            type(test_database), "engine", new_callable=PropertyMock
        ) as mock_engine_prop:
            mock_engine_prop.return_value = mock_engine

            await bot._create_tables()

            # Verify connection was used
            mock_conn.run_sync.assert_called_once()


async def test_bot_close_with_done_monitor_task(test_bot: DiscordBot) -> None:
    """Test bot close when monitor task is already done.

    Args:
        test_bot: Test bot instance
    """
    # Mock the database close and parent close
    test_bot.database.close = AsyncMock()  # type: ignore[method-assign]

    # Mock event bus emit
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit  # type: ignore[method-assign]

    # Mock monitor task as already done
    mock_task = AsyncMock()
    mock_task.done.return_value = True
    test_bot._monitor_task = mock_task

    with patch("discord_bot.bot.commands.Bot.close", new_callable=AsyncMock):
        await test_bot.close()

        # Verify shutdown event was emitted
        from discord_bot.common.enums.event_type import EventType

        mock_emit.assert_called_once_with(EventType.BOT_SHUTDOWN, {})

        # Verify database was closed
        test_bot.database.close.assert_called_once()


async def test_bot_close_without_monitor_task(test_bot: DiscordBot) -> None:
    """Test bot close when no monitor task exists.

    Args:
        test_bot: Test bot instance
    """
    # Mock the database close and parent close
    test_bot.database.close = AsyncMock()  # type: ignore[method-assign]

    # Mock event bus emit
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit  # type: ignore[method-assign]

    # No monitor task
    test_bot._monitor_task = None

    with patch("discord_bot.bot.commands.Bot.close", new_callable=AsyncMock):
        await test_bot.close()

        # Verify shutdown event was emitted
        from discord_bot.common.enums.event_type import EventType

        mock_emit.assert_called_once_with(EventType.BOT_SHUTDOWN, {})

        # Verify database was closed
        test_bot.database.close.assert_called_once()


@pytest.mark.timeout(2)
async def test_monitor_event_loop_cancellation(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test event loop monitor cancellation.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        # Start monitoring
        task = asyncio.create_task(bot._monitor_event_loop())

        # Let it run briefly
        await asyncio.sleep(0.2)

        # Cancel the task
        task.cancel()

        # Verify it handles cancellation
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.timeout(3)
async def test_monitor_event_loop_detects_lag(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test event loop monitor detects blocking operations.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    import time

    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        # Set a low threshold for testing
        bot.settings.bot.event_loop_warning_threshold = 0.1

        # Mock the logger to capture warnings
        with patch("discord_bot.bot.logger") as mock_logger:
            # Start monitoring
            task = asyncio.create_task(bot._monitor_event_loop())

            # Let monitor start
            await asyncio.sleep(0.15)

            # Simulate a blocking operation (blocks the event loop)
            # This is intentional - we're testing that the monitor detects blocking calls
            time.sleep(0.6)  # noqa: ASYNC251

            # Give monitor time to detect the lag
            await asyncio.sleep(0.15)

            # Cancel the task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify warning was logged
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "Retraso en el bucle de eventos detectado" in str(call)
            ]
            assert len(warning_calls) > 0, "Expected warning about event loop delay"


@pytest.mark.timeout(2)
async def test_monitor_event_loop_uses_custom_threshold(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test event loop monitor uses custom threshold from settings.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        # Set custom threshold
        test_settings.bot.event_loop_warning_threshold = 2.0
        bot = DiscordBot(test_settings, test_database)

        # Mock the logger
        with patch("discord_bot.bot.logger") as mock_logger:
            # Start monitoring
            task = asyncio.create_task(bot._monitor_event_loop())

            # Let it run briefly
            await asyncio.sleep(0.2)

            # Cancel the task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # With high threshold (2.0s), no warnings should be logged for normal operation
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "Retraso en el bucle de eventos detectado" in str(call)
            ]
            assert len(warning_calls) == 0, "Should not log warnings with high threshold"
