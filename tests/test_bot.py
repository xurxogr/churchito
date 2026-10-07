"""Tests for the main bot class."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord
import pytest
from sqlalchemy import select

from discord_bot.bot import DiscordBot
from discord_bot.common.core import AppSettings
from discord_bot.common.models import Guild as GuildModel
from discord_bot.common.services import DatabaseService


@pytest.fixture
async def test_bot(
    test_settings: AppSettings, test_database: DatabaseService
) -> AsyncGenerator[DiscordBot, None]:
    """Fixture to create a test bot instance.

    Args:
        test_settings (AppSettings): Test application settings
        test_database (DatabaseService): Test database service

    Returns:
        DiscordBot: Test bot instance
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        # Mock necessary properties
        type(bot).guilds = PropertyMock(return_value=[])
        mock_user = MagicMock()
        mock_user.name = "TestBot"
        mock_user.id = 123456789
        type(bot).user = PropertyMock(return_value=mock_user)
        bot.load_extension = AsyncMock()
        type(bot).cogs = PropertyMock(return_value={})
        yield bot


def test_bot_initialization(test_settings: AppSettings, test_database: DatabaseService) -> None:
    """Test bot initialization.

    Args:
        test_settings (AppSettings): Test application settings
        test_database (DatabaseService): Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        assert bot.settings == test_settings
        assert bot.database == test_database
        assert bot.event_bus is not None


def test_bot_disables_message_cache(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that the internal message cache is disabled.

    Args:
        test_settings (AppSettings): Test application settings
        test_database (DatabaseService): Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None) as mock_init:
        DiscordBot(test_settings, test_database)

        assert mock_init.call_args.kwargs["max_messages"] is None


def test_bot_disables_mass_mentions_by_default(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that everyone/role pings are disabled in the default allowed mentions.

    Args:
        test_settings (AppSettings): Test application settings
        test_database (DatabaseService): Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None) as mock_init:
        DiscordBot(test_settings, test_database)

        allowed = mock_init.call_args.kwargs["allowed_mentions"]
        assert allowed.everyone is False
        assert allowed.roles is False
        assert allowed.users is True
        assert allowed.replied_user is True


async def test_bot_on_ready(test_bot: DiscordBot) -> None:
    """Test the bot's on_ready method.

    Args:
        test_bot: Test bot instance
    """
    # Mock the event bus emit method
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit

    # Call on_ready
    await test_bot.on_ready()

    # Verify that the correct event was emitted
    from discord_bot.common.enums.event_type import EventType

    mock_emit.assert_called_once_with(
        EventType.BOT_READY,
        {
            "bot_name": "TestBot",
            "bot_id": 123456789,
            "guild_count": 0,
        },
    )


async def test_bot_on_ready_syncs_commands_only_once(test_bot: DiscordBot) -> None:
    """Test that a reconnect on_ready does not repeat the rate-limited command sync.

    Args:
        test_bot: Test bot instance
    """
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit

    mock_tree = MagicMock()
    mock_tree.sync = AsyncMock(return_value=[])

    with patch.object(type(test_bot), "tree", new_callable=PropertyMock, return_value=mock_tree):
        # First ready at startup, second one from a gateway re-IDENTIFY
        await test_bot.on_ready()
        await test_bot.on_ready()

    assert mock_tree.sync.await_count == 1
    assert mock_emit.call_count == 1


async def test_bot_on_ready_reconciles_guilds_every_time(test_bot: DiscordBot) -> None:
    """Test that guild reconciliation still runs on reconnects.

    A guild that invited the bot during a disconnect only shows up in the
    READY payload, so the reconnect must reconcile it into the database.

    Args:
        test_bot: Test bot instance
    """
    test_bot.event_bus.emit = MagicMock()

    mock_tree = MagicMock()
    mock_tree.sync = AsyncMock(return_value=[])

    with (
        patch.object(type(test_bot), "tree", new_callable=PropertyMock, return_value=mock_tree),
        patch.object(test_bot, "_reconcile_guilds", new=AsyncMock()) as mock_reconcile,
    ):
        await test_bot.on_ready()
        await test_bot.on_ready()

    assert mock_reconcile.await_count == 2


async def test_bot_close(test_bot: DiscordBot) -> None:
    """Test the bot's close method.

    Args:
        test_bot: Test bot instance
    """
    # Mock the database close
    test_bot.database.close = AsyncMock()

    # Mock the event bus emit method
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit

    # Create a fake monitor task
    async def dummy_monitor() -> None:
        await asyncio.sleep(100)  # Long sleep to simulate running task

    monitor_task = asyncio.create_task(dummy_monitor())
    test_bot._monitor_task = monitor_task

    with patch("discord_bot.bot.commands.Bot.close", new_callable=AsyncMock):
        await test_bot.close()

        # Verify that the shutdown event was emitted
        from discord_bot.common.enums.event_type import EventType

        mock_emit.assert_called_once_with(EventType.BOT_SHUTDOWN, {})

        # Verify that the monitor task was cancelled
        assert monitor_task.cancelled()

        # Verify that the database was closed
        test_bot.database.close.assert_called_once()


async def test_bot_setup_hook(test_settings: AppSettings, test_database: DatabaseService) -> None:
    """Test the bot's setup_hook method.

    Args:
        test_settings (AppSettings): Test application settings
        test_database (DatabaseService): Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock()

        # Mock the tree for error handler assignment
        mock_tree = MagicMock()
        bot._BotBase__tree = mock_tree

        # Mock the database initialization
        test_database.initialize = AsyncMock()

        with (
            patch.object(bot, "_create_tables", new_callable=AsyncMock) as mock_create_tables,
            patch.object(bot, "_load_cogs", new_callable=AsyncMock) as mock_load_cogs,
        ):
            await bot.setup_hook()

            # Verify that the correct methods were called
            test_database.initialize.assert_called_once()
            mock_create_tables.assert_called_once()
            mock_load_cogs.assert_called_once()

            # Verify that the error handler was set
            assert mock_tree.on_error == bot._on_app_command_error


async def test_bot_load_cogs_success(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test successful cog loading for the bot.

    Args:
        test_settings (AppSettings): Test application settings
        test_database (DatabaseService): Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock()

        # Should load without errors
        await bot._load_cogs()

        # Validate that expected extensions were called
        assert bot.load_extension.call_count > 0
        bot.load_extension.assert_any_call("discord_bot.verification.cog")


async def test_bot_load_cogs_with_error(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test bot cog loading with errors.

    Args:
        test_settings (AppSettings): Test application settings
        test_database (DatabaseService): Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock(side_effect=Exception("Test error"))

        # Should handle the error internally
        await bot._load_cogs()

        # Validate that expected extensions were called
        assert bot.load_extension.call_count > 0


async def test_bot_create_tables(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test database migration application.

    Args:
        test_settings (AppSettings): Test application settings
        test_database (DatabaseService): Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        # Patch alembic command.upgrade
        with patch("alembic.command.upgrade") as mock_upgrade:
            await bot._create_tables()

            # Verify alembic upgrade was called
            mock_upgrade.assert_called_once()


async def test_bot_close_with_done_monitor_task(test_bot: DiscordBot) -> None:
    """Test bot close when monitor task is already completed.

    Args:
        test_bot: Test bot instance
    """
    # Mock database close
    test_bot.database.close = AsyncMock()

    # Mock event bus emit method
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit

    # Mock an already completed monitor task
    mock_task = AsyncMock()
    mock_task.done.return_value = True
    test_bot._monitor_task = mock_task

    with patch("discord_bot.bot.commands.Bot.close", new_callable=AsyncMock):
        await test_bot.close()

        # Verify shutdown event was emitted
        from discord_bot.common.enums.event_type import EventType

        mock_emit.assert_called_once_with(EventType.BOT_SHUTDOWN, {})

        # Verify monitor task was not cancelled (already done)
        test_bot.database.close.assert_called_once()


async def test_bot_close_without_monitor_task(test_bot: DiscordBot) -> None:
    """Test bot close when there is no monitor task.

    Args:
        test_bot: Test bot instance
    """
    # Mock database close
    test_bot.database.close = AsyncMock()

    # Mock event bus emit method
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit

    # No monitor task
    test_bot._monitor_task = None

    with patch("discord_bot.bot.commands.Bot.close", new_callable=AsyncMock):
        await test_bot.close()

        # Verify shutdown event was emitted
        from discord_bot.common.enums.event_type import EventType

        mock_emit.assert_called_once_with(EventType.BOT_SHUTDOWN, {})

        # Verify database was closed
        test_bot.database.close.assert_called_once()


async def test_monitor_event_loop_cancellation(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test event loop monitor cancellation.

    Args:
        test_settings (AppSettings): Test application settings
        test_database (DatabaseService): Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        # Start the monitor
        task = asyncio.create_task(bot._monitor_event_loop())

        # Let it run a bit
        await asyncio.sleep(0.2)

        # Cancel the task
        task.cancel()

        # Verify it cancels without errors
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_monitor_event_loop_detects_lag(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that event loop monitor detects lag.

    Args:
        test_settings (AppSettings): Test application settings
        test_database (DatabaseService): Test database service
    """
    import time

    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        # Set low threshold for testing
        bot.settings.bot.event_loop_warning_threshold = 0.1

        # Mock the logger
        with patch("discord_bot.bot.logger") as mock_logger:
            # Start the monitor
            task = asyncio.create_task(bot._monitor_event_loop())

            # Let it run a bit
            await asyncio.sleep(0.15)

            # Introduce artificial lag
            time.sleep(0.6)  # noqa: ASYNC251

            # Give monitor time to detect lag
            await asyncio.sleep(0.15)

            # Cancel the task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify warning was logged about lag
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "Event loop lag detected" in str(call)
            ]
            assert len(warning_calls) > 0, "Expected warning about event loop delay"


async def test_monitor_event_loop_uses_custom_threshold(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that event loop monitor uses custom threshold.

    Args:
        test_settings (AppSettings): Test application settings
        test_database (DatabaseService): Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        # Set high threshold for testing
        test_settings.bot.event_loop_warning_threshold = 2.0
        bot = DiscordBot(test_settings, test_database)

        # Mock the logger
        with patch("discord_bot.bot.logger") as mock_logger:
            # Start the monitor
            task = asyncio.create_task(bot._monitor_event_loop())

            # Let it run a bit
            await asyncio.sleep(0.2)

            # Cancel the task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Confirm no warnings were logged
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "Event loop lag detected" in str(call)
            ]
            assert len(warning_calls) == 0, "Should not log warnings with high threshold"


async def test_bot_on_ready_without_user(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test on_ready when bot user is None.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        type(bot).user = PropertyMock(return_value=None)

        mock_emit = MagicMock()
        bot.event_bus.emit = mock_emit

        # Should execute without errors when user is None
        await bot.on_ready()

        # Should not emit event when there is no user
        mock_emit.assert_not_called()


async def test_bot_on_ready_sync_error(test_bot: DiscordBot) -> None:
    """Test on_ready when tree.sync() raises an exception.

    Args:
        test_bot: Test bot instance
    """
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit

    # Mock tree.sync to raise exception
    mock_tree = MagicMock()
    mock_tree.sync = AsyncMock(side_effect=Exception("Sync failed"))
    type(test_bot).tree = PropertyMock(return_value=mock_tree)

    # Should handle error without propagating
    with patch("discord_bot.bot.logger") as mock_logger:
        await test_bot.on_ready()

        # Verify error was logged
        error_calls = [
            call
            for call in mock_logger.error.call_args_list
            if "Error syncing commands" in str(call)
        ]
        assert len(error_calls) > 0, "Expected error log about sync failure"

    # Event should have been emitted anyway
    from discord_bot.common.enums.event_type import EventType

    mock_emit.assert_called_once_with(
        EventType.BOT_READY,
        {
            "bot_name": "TestBot",
            "bot_id": 123456789,
            "guild_count": 0,
        },
    )


async def test_bot_on_ready_sync_success(test_bot: DiscordBot) -> None:
    """Test on_ready when tree.sync() succeeds.

    Args:
        test_bot: Test bot instance
    """
    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit

    # Mock tree.sync to return synced commands
    mock_tree = MagicMock()
    mock_tree.sync = AsyncMock(return_value=[MagicMock(), MagicMock()])
    type(test_bot).tree = PropertyMock(return_value=mock_tree)

    with patch("discord_bot.bot.logger") as mock_logger:
        await test_bot.on_ready()

        # Verify successful sync was logged
        info_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "Synced 2 application commands" in str(call)
        ]
        assert len(info_calls) > 0, "Expected info log about synced commands"


async def test_bot_setup_hook_creates_monitor_task(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that setup_hook creates the monitor task.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock()
        test_database.initialize = AsyncMock()

        # Mock _create_tables and _load_cogs
        with (
            patch.object(bot, "_create_tables", new_callable=AsyncMock),
            patch.object(bot, "_load_cogs", new_callable=AsyncMock),
        ):
            await bot.setup_hook()

            # Verify monitor task was created
            assert bot._monitor_task is not None
            assert not bot._monitor_task.done()

            # Cleanup task
            bot._monitor_task.cancel()
            try:
                await bot._monitor_task
            except asyncio.CancelledError:
                pass


def test_bot_initialization_sets_intents(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that initialization sets intents correctly.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__") as mock_init:
        mock_init.return_value = None

        DiscordBot(test_settings, test_database)

        # Verify parent constructor was called with correct arguments
        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args.kwargs

        assert call_kwargs["command_prefix"] == test_settings.bot.command_prefix
        assert call_kwargs["description"] == test_settings.bot.description
        assert call_kwargs["owner_id"] == test_settings.bot.owner_id

        # Verify intents
        intents = call_kwargs["intents"]
        assert intents.message_content is True
        assert intents.members is True


def test_bot_initialization_with_different_settings(
    test_database: DatabaseService,
) -> None:
    """Test initialization with different settings.

    Args:
        test_database: Test database service
    """
    from discord_bot.common.core import AppSettings
    from discord_bot.common.core.settings.bot import BotSettings

    custom_settings = AppSettings(
        bot=BotSettings(
            token="test_token",
            command_prefix=">>",
            description="Custom Bot Description",
            owner_id=999888777,
        )
    )

    with patch("discord_bot.bot.commands.Bot.__init__") as mock_init:
        mock_init.return_value = None

        bot = DiscordBot(custom_settings, test_database)

        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs["command_prefix"] == ">>"
        assert call_kwargs["description"] == "Custom Bot Description"
        assert call_kwargs["owner_id"] == 999888777
        assert bot.settings == custom_settings


async def test_bot_on_ready_logs_guild_count(test_bot: DiscordBot) -> None:
    """Test that on_ready logs guild count.

    Args:
        test_bot: Test bot instance
    """
    # Setup multiple guilds
    mock_guilds = [MagicMock(), MagicMock(), MagicMock()]
    type(test_bot).guilds = PropertyMock(return_value=mock_guilds)

    mock_emit = MagicMock()
    test_bot.event_bus.emit = mock_emit

    mock_tree = MagicMock()
    mock_tree.sync = AsyncMock(return_value=[])
    type(test_bot).tree = PropertyMock(return_value=mock_tree)

    with patch("discord_bot.bot.logger") as mock_logger:
        await test_bot.on_ready()

        # Verify guild count was logged
        info_calls = [
            call for call in mock_logger.info.call_args_list if "3 server(s)" in str(call)
        ]
        assert len(info_calls) > 0, "Expected info log about guild count"

    # Verify emitted event
    from discord_bot.common.enums.event_type import EventType

    mock_emit.assert_called_once_with(
        EventType.BOT_READY,
        {
            "bot_name": "TestBot",
            "bot_id": 123456789,
            "guild_count": 3,
        },
    )


async def test_bot_load_cogs_loads_all_configured_cogs(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that _load_cogs attempts to load all configured cogs.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock()

        with patch("discord_bot.bot.logger") as mock_logger:
            await bot._load_cogs()

            # Verify successful loading was logged
            info_calls = [
                call for call in mock_logger.info.call_args_list if "Loaded cog:" in str(call)
            ]
            assert len(info_calls) > 0, "Expected info log about loaded cogs"


async def test_bot_load_cogs_logs_errors(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that _load_cogs logs errors when loading cogs.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock(side_effect=Exception("Failed to load"))

        with patch("discord_bot.bot.logger") as mock_logger:
            await bot._load_cogs()

            # Verify error was logged
            error_calls = [
                call
                for call in mock_logger.error.call_args_list
                if "Error loading cog" in str(call)
            ]
            assert len(error_calls) > 0, "Expected error log about cog loading failure"


async def test_bot_create_tables_logs_success(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that _create_tables logs successful migration application.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        with (
            patch("alembic.command.upgrade"),
            patch("discord_bot.bot.logger") as mock_logger,
        ):
            await bot._create_tables()

            # Verify migration application was logged
            info_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "Database migrations applied" in str(call)
            ]
            assert len(info_calls) > 0, "Expected info log about migrations"


async def test_bot_close_logs_shutdown(test_bot: DiscordBot) -> None:
    """Test that close logs the shutdown process.

    Args:
        test_bot: Test bot instance
    """
    test_bot.database.close = AsyncMock()
    test_bot.event_bus.emit = MagicMock()
    test_bot._monitor_task = None

    with (
        patch("discord_bot.bot.commands.Bot.close", new_callable=AsyncMock),
        patch("discord_bot.bot.logger") as mock_logger,
    ):
        await test_bot.close()

        # Verify log messages
        info_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("Shutting down the bot" in call for call in info_calls)
        assert any("Bot shutdown completed" in call for call in info_calls)


async def test_bot_setup_hook_logs_progress(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that setup_hook logs progress.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        bot.load_extension = AsyncMock()
        test_database.initialize = AsyncMock()

        with (
            patch.object(bot, "_create_tables", new_callable=AsyncMock),
            patch.object(bot, "_load_cogs", new_callable=AsyncMock),
            patch("discord_bot.bot.logger") as mock_logger,
        ):
            await bot.setup_hook()

            # Verify log messages
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("Running setup hook" in call for call in info_calls)
            assert any("Setup hook completed" in call for call in info_calls)

            # Cleanup
            if bot._monitor_task:
                bot._monitor_task.cancel()
                try:
                    await bot._monitor_task
                except asyncio.CancelledError:
                    pass


async def test_monitor_event_loop_logs_start(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that _monitor_event_loop logs start.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        with patch("discord_bot.bot.logger") as mock_logger:
            task = asyncio.create_task(bot._monitor_event_loop())
            await asyncio.sleep(0.05)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify start was logged
            info_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "Event loop monitoring started" in str(call)
            ]
            assert len(info_calls) > 0


async def test_monitor_event_loop_logs_stop(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that _monitor_event_loop logs stop.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        with patch("discord_bot.bot.logger") as mock_logger:
            task = asyncio.create_task(bot._monitor_event_loop())
            await asyncio.sleep(0.05)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify stop was logged
            info_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "Event loop monitoring stopped" in str(call)
            ]
            assert len(info_calls) > 0


# Tests for guild reconciliation on ready


def _ready_guild(guild_id: int, name: str, owner_id: int) -> MagicMock:
    """Guild mock without audit-log access, so the inviter falls back to the owner.

    Args:
        guild_id (int): Guild ID.
        name (str): Guild name.
        owner_id (int): Guild owner ID.

    Returns:
        MagicMock: Guild mock.
    """
    guild = MagicMock()
    guild.id = guild_id
    guild.name = name
    guild.owner_id = owner_id
    guild.me = None
    return guild


class TestOnReadyReconcilesGuilds:
    """on_ready must register guilds joined while the bot was offline and refresh names."""

    async def test_registers_guilds_missing_from_database(
        self, test_bot: DiscordBot, test_database: DatabaseService
    ) -> None:
        """A guild without a row is saved with the owner as inviter (no audit log access)."""
        guild = _ready_guild(guild_id=424242, name="Joined Offline", owner_id=777)
        type(test_bot).guilds = PropertyMock(return_value=[guild])
        type(test_bot).tree = PropertyMock(return_value=MagicMock(sync=AsyncMock(return_value=[])))

        await test_bot.on_ready()

        async with test_database.session() as session:
            row = (
                await session.execute(select(GuildModel).where(GuildModel.id == 424242))
            ).scalar_one_or_none()
        assert row is not None
        assert row.name == "Joined Offline"
        assert row.invited_by_id == 777

    async def test_refreshes_renamed_guild_without_touching_inviter(
        self, test_bot: DiscordBot, test_database: DatabaseService
    ) -> None:
        """A known guild gets its name updated but keeps who invited the bot."""
        async with test_database.session() as session:
            session.add(GuildModel(id=515151, name="Old Name", invited_by_id=42))
            await session.commit()
        guild = _ready_guild(guild_id=515151, name="New Name", owner_id=777)
        type(test_bot).guilds = PropertyMock(return_value=[guild])
        type(test_bot).tree = PropertyMock(return_value=MagicMock(sync=AsyncMock(return_value=[])))

        await test_bot.on_ready()

        async with test_database.session() as session:
            row = (
                await session.execute(select(GuildModel).where(GuildModel.id == 515151))
            ).scalar_one()
        assert row.name == "New Name"
        assert row.invited_by_id == 42

    async def test_known_unchanged_guild_is_not_rewritten(
        self, test_bot: DiscordBot, test_database: DatabaseService
    ) -> None:
        """A guild whose row is current is left alone."""
        async with test_database.session() as session:
            session.add(GuildModel(id=616161, name="Same", invited_by_id=42))
            await session.commit()
        guild = _ready_guild(guild_id=616161, name="Same", owner_id=777)
        type(test_bot).guilds = PropertyMock(return_value=[guild])
        type(test_bot).tree = PropertyMock(return_value=MagicMock(sync=AsyncMock(return_value=[])))

        with patch.object(test_bot, "_save_guild", new_callable=AsyncMock) as mock_save:
            await test_bot.on_ready()

        mock_save.assert_not_awaited()

    async def test_reconciliation_failure_does_not_stop_startup(self, test_bot: DiscordBot) -> None:
        """A database error while saving a guild is logged and on_ready carries on."""
        guild = _ready_guild(guild_id=717171, name="Broken", owner_id=777)
        type(test_bot).guilds = PropertyMock(return_value=[guild])
        mock_tree = MagicMock(sync=AsyncMock(return_value=[]))
        type(test_bot).tree = PropertyMock(return_value=mock_tree)
        mock_emit = MagicMock()
        test_bot.event_bus.emit = mock_emit

        with (
            patch.object(
                test_bot, "_save_guild", new_callable=AsyncMock, side_effect=RuntimeError("db gone")
            ),
            patch("discord_bot.bot.logger") as mock_logger,
        ):
            await test_bot.on_ready()

        assert any("db gone" in str(call) for call in mock_logger.error.call_args_list)
        mock_tree.sync.assert_awaited_once()
        mock_emit.assert_called_once()


# Tests for on_guild_join


async def test_on_guild_join_finds_inviter_in_audit_log(test_bot: DiscordBot) -> None:
    """Test that on_guild_join finds inviter in audit log.

    Args:
        test_bot: Test bot instance
    """
    # Create guild mock
    mock_guild = MagicMock()
    mock_guild.id = 123456
    mock_guild.name = "Test Server"
    mock_guild.owner_id = 999999

    # Configure permissions
    mock_me = MagicMock()
    mock_me.guild_permissions.view_audit_log = True
    mock_guild.me = mock_me

    # Create audit log entry matching the bot
    mock_entry = MagicMock()
    mock_entry.target = MagicMock()
    mock_entry.target.id = 123456789  # Same ID as test_bot.user
    mock_entry.user = MagicMock()
    mock_entry.user.id = 888777666
    mock_entry.user.name = "InviterUser"

    async def mock_audit_logs(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
        yield mock_entry

    mock_guild.audit_logs = mock_audit_logs

    # Mock _save_guild
    with patch.object(test_bot, "_save_guild", new_callable=AsyncMock) as mock_save:
        await test_bot.on_guild_join(mock_guild)

        # Verify _save_guild was called with correct inviter
        mock_save.assert_called_once_with(mock_guild, 888777666)


async def test_on_guild_join_fallback_to_owner_when_no_audit_log_permission(
    test_bot: DiscordBot,
) -> None:
    """Test that on_guild_join uses owner when no audit log permission.

    Args:
        test_bot: Test bot instance
    """
    mock_guild = MagicMock()
    mock_guild.id = 123456
    mock_guild.name = "Test Server"
    mock_guild.owner_id = 999999

    # No audit log permission
    mock_me = MagicMock()
    mock_me.guild_permissions.view_audit_log = False
    mock_guild.me = mock_me

    with patch.object(test_bot, "_save_guild", new_callable=AsyncMock) as mock_save:
        await test_bot.on_guild_join(mock_guild)

        # Should use owner_id
        mock_save.assert_called_once_with(mock_guild, 999999)


async def test_on_guild_join_fallback_to_owner_when_guild_me_is_none(
    test_bot: DiscordBot,
) -> None:
    """Test that on_guild_join uses owner when guild.me is None.

    Args:
        test_bot: Test bot instance
    """
    mock_guild = MagicMock()
    mock_guild.id = 123456
    mock_guild.name = "Test Server"
    mock_guild.owner_id = 999999
    mock_guild.me = None

    with patch.object(test_bot, "_save_guild", new_callable=AsyncMock) as mock_save:
        await test_bot.on_guild_join(mock_guild)

        mock_save.assert_called_once_with(mock_guild, 999999)


async def test_on_guild_join_fallback_to_owner_when_bot_user_is_none(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that on_guild_join uses owner when self.user is None.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)
        type(bot).user = PropertyMock(return_value=None)

        mock_guild = MagicMock()
        mock_guild.id = 123456
        mock_guild.name = "Test Server"
        mock_guild.owner_id = 999999

        mock_me = MagicMock()
        mock_me.guild_permissions.view_audit_log = True
        mock_guild.me = mock_me

        with patch.object(bot, "_save_guild", new_callable=AsyncMock) as mock_save:
            await bot.on_guild_join(mock_guild)

            mock_save.assert_called_once_with(mock_guild, 999999)


async def test_on_guild_join_handles_forbidden_exception(test_bot: DiscordBot) -> None:
    """Test that on_guild_join handles discord.Forbidden correctly.

    Args:
        test_bot: Test bot instance
    """
    mock_guild = MagicMock()
    mock_guild.id = 123456
    mock_guild.name = "Test Server"
    mock_guild.owner_id = 999999

    mock_me = MagicMock()
    mock_me.guild_permissions.view_audit_log = True
    mock_guild.me = mock_me

    # Simulate Forbidden exception
    async def mock_audit_logs(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
        raise discord.Forbidden(MagicMock(), "No permission")
        yield  # To make it a generator

    mock_guild.audit_logs = mock_audit_logs

    with (
        patch.object(test_bot, "_save_guild", new_callable=AsyncMock) as mock_save,
        patch("discord_bot.bot.logger") as mock_logger,
    ):
        await test_bot.on_guild_join(mock_guild)

        # Should use owner_id as fallback
        mock_save.assert_called_once_with(mock_guild, 999999)

        # Verify warning was logged
        warning_calls = [
            call
            for call in mock_logger.warning.call_args_list
            if "Could not access audit log" in str(call)
        ]
        assert len(warning_calls) > 0


async def test_on_guild_join_handles_generic_exception(test_bot: DiscordBot) -> None:
    """Test that on_guild_join handles generic exceptions correctly.

    Args:
        test_bot: Test bot instance
    """
    mock_guild = MagicMock()
    mock_guild.id = 123456
    mock_guild.name = "Test Server"
    mock_guild.owner_id = 999999

    mock_me = MagicMock()
    mock_me.guild_permissions.view_audit_log = True
    mock_guild.me = mock_me

    # Simulate generic exception
    async def mock_audit_logs(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
        raise RuntimeError("Something went wrong")
        yield  # To make it a generator

    mock_guild.audit_logs = mock_audit_logs

    with (
        patch.object(test_bot, "_save_guild", new_callable=AsyncMock) as mock_save,
        patch("discord_bot.bot.logger") as mock_logger,
    ):
        await test_bot.on_guild_join(mock_guild)

        # Should use owner_id as fallback
        mock_save.assert_called_once_with(mock_guild, 999999)

        # Verify error was logged
        error_calls = [
            call
            for call in mock_logger.error.call_args_list
            if "Error querying audit log" in str(call)
        ]
        assert len(error_calls) > 0


async def test_on_guild_join_no_matching_entry_in_audit_log(test_bot: DiscordBot) -> None:
    """Test that on_guild_join uses owner when no matching entry found.

    Args:
        test_bot: Test bot instance
    """
    mock_guild = MagicMock()
    mock_guild.id = 123456
    mock_guild.name = "Test Server"
    mock_guild.owner_id = 999999

    mock_me = MagicMock()
    mock_me.guild_permissions.view_audit_log = True
    mock_guild.me = mock_me

    # Create audit log entry that does NOT match the bot
    mock_entry = MagicMock()
    mock_entry.target = MagicMock()
    mock_entry.target.id = 111111111  # Different ID from bot
    mock_entry.user = MagicMock()
    mock_entry.user.id = 888777666

    async def mock_audit_logs(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
        yield mock_entry

    mock_guild.audit_logs = mock_audit_logs

    with patch.object(test_bot, "_save_guild", new_callable=AsyncMock) as mock_save:
        await test_bot.on_guild_join(mock_guild)

        # Should use owner_id because no matching entry found
        mock_save.assert_called_once_with(mock_guild, 999999)


async def test_on_guild_join_entry_with_none_target(test_bot: DiscordBot) -> None:
    """Test that on_guild_join handles entry with None target.

    Args:
        test_bot: Test bot instance
    """
    mock_guild = MagicMock()
    mock_guild.id = 123456
    mock_guild.name = "Test Server"
    mock_guild.owner_id = 999999

    mock_me = MagicMock()
    mock_me.guild_permissions.view_audit_log = True
    mock_guild.me = mock_me

    # Entry with None target
    mock_entry = MagicMock()
    mock_entry.target = None
    mock_entry.user = MagicMock()
    mock_entry.user.id = 888777666

    async def mock_audit_logs(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
        yield mock_entry

    mock_guild.audit_logs = mock_audit_logs

    with patch.object(test_bot, "_save_guild", new_callable=AsyncMock) as mock_save:
        await test_bot.on_guild_join(mock_guild)

        mock_save.assert_called_once_with(mock_guild, 999999)


async def test_on_guild_join_entry_with_none_user(test_bot: DiscordBot) -> None:
    """Test that on_guild_join handles entry with None user.

    Args:
        test_bot: Test bot instance
    """
    mock_guild = MagicMock()
    mock_guild.id = 123456
    mock_guild.name = "Test Server"
    mock_guild.owner_id = 999999

    mock_me = MagicMock()
    mock_me.guild_permissions.view_audit_log = True
    mock_guild.me = mock_me

    # Entry with None user
    mock_entry = MagicMock()
    mock_entry.target = MagicMock()
    mock_entry.target.id = 123456789  # Same ID as test_bot.user
    mock_entry.user = None

    async def mock_audit_logs(*args: Any, **kwargs: Any) -> AsyncIterator[MagicMock]:
        yield mock_entry

    mock_guild.audit_logs = mock_audit_logs

    with patch.object(test_bot, "_save_guild", new_callable=AsyncMock) as mock_save:
        await test_bot.on_guild_join(mock_guild)

        mock_save.assert_called_once_with(mock_guild, 999999)


async def test_on_guild_join_logs_info(test_bot: DiscordBot) -> None:
    """Test that on_guild_join logs information.

    Args:
        test_bot: Test bot instance
    """
    mock_guild = MagicMock()
    mock_guild.id = 123456
    mock_guild.name = "Test Server"
    mock_guild.owner_id = 999999
    mock_guild.me = None

    with (
        patch.object(test_bot, "_save_guild", new_callable=AsyncMock),
        patch("discord_bot.bot.logger") as mock_logger,
    ):
        await test_bot.on_guild_join(mock_guild)

        # Verify join log
        info_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "Bot joined server: Test Server" in str(call)
        ]
        assert len(info_calls) > 0


# Tests for _save_guild


async def test_save_guild_creates_new_guild(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that _save_guild creates a new guild in the DB.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        mock_guild = MagicMock()
        mock_guild.id = 987654321
        mock_guild.name = "New Test Server"

        await bot._save_guild(mock_guild, invited_by_id=111222333)

        # Verify it was created in DB
        async with test_database.session() as session:
            result = await session.execute(select(GuildModel).where(GuildModel.id == 987654321))
            saved_guild = result.scalar_one_or_none()

            assert saved_guild is not None
            assert saved_guild.name == "New Test Server"
            assert saved_guild.invited_by_id == 111222333


async def test_save_guild_updates_existing_guild_name(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that _save_guild updates name of existing guild.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        # Create initial guild
        async with test_database.session() as session:
            initial_guild = GuildModel(
                id=555666777,
                name="Old Name",
                invited_by_id=111222333,
            )
            session.add(initial_guild)
            await session.commit()

        # Update
        mock_guild = MagicMock()
        mock_guild.id = 555666777
        mock_guild.name = "New Name"

        await bot._save_guild(mock_guild, invited_by_id=444555666)

        # Verify update
        async with test_database.session() as session:
            result = await session.execute(select(GuildModel).where(GuildModel.id == 555666777))
            updated_guild = result.scalar_one_or_none()

            assert updated_guild is not None
            assert updated_guild.name == "New Name"
            # invited_by_id is updated when bot is re-invited
            assert updated_guild.invited_by_id == 444555666


async def test_save_guild_updates_invited_by_if_null(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that _save_guild updates invited_by_id if it was NULL.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        # Create guild without inviter
        async with test_database.session() as session:
            initial_guild = GuildModel(
                id=888999000,
                name="Server Without Inviter",
                invited_by_id=None,
            )
            session.add(initial_guild)
            await session.commit()

        # Update with inviter
        mock_guild = MagicMock()
        mock_guild.id = 888999000
        mock_guild.name = "Server Without Inviter"

        await bot._save_guild(mock_guild, invited_by_id=123123123)

        # Verify invited_by_id was updated
        async with test_database.session() as session:
            result = await session.execute(select(GuildModel).where(GuildModel.id == 888999000))
            updated_guild = result.scalar_one_or_none()

            assert updated_guild is not None
            assert updated_guild.invited_by_id == 123123123


async def test_save_guild_does_not_update_invited_by_if_none_provided(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that _save_guild does not update invited_by_id if None is passed.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        # Create guild without inviter
        async with test_database.session() as session:
            initial_guild = GuildModel(
                id=777888999,
                name="Server",
                invited_by_id=None,
            )
            session.add(initial_guild)
            await session.commit()

        # Update passing None as invited_by_id
        mock_guild = MagicMock()
        mock_guild.id = 777888999
        mock_guild.name = "Server Updated"

        await bot._save_guild(mock_guild, invited_by_id=None)

        # Verify it remains None
        async with test_database.session() as session:
            result = await session.execute(select(GuildModel).where(GuildModel.id == 777888999))
            updated_guild = result.scalar_one_or_none()

            assert updated_guild is not None
            assert updated_guild.name == "Server Updated"
            assert updated_guild.invited_by_id is None


async def test_save_guild_logs_success(
    test_settings: AppSettings, test_database: DatabaseService
) -> None:
    """Test that _save_guild logs success.

    Args:
        test_settings: Test application settings
        test_database: Test database service
    """
    with patch("discord_bot.bot.commands.Bot.__init__", return_value=None):
        bot = DiscordBot(test_settings, test_database)

        mock_guild = MagicMock()
        mock_guild.id = 111222333444
        mock_guild.name = "Log Test Server"

        with patch("discord_bot.bot.logger") as mock_logger:
            await bot._save_guild(mock_guild, invited_by_id=None)

            # Verify success log
            info_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "Server saved to DB: Log Test Server" in str(call)
            ]
            assert len(info_calls) > 0


# Tests for on_guild_remove


async def test_on_guild_remove_logs_info(test_bot: DiscordBot) -> None:
    """Test that on_guild_remove logs removal.

    Args:
        test_bot: Test bot instance
    """
    mock_guild = MagicMock()
    mock_guild.id = 123456
    mock_guild.name = "Removed Server"

    # Mock guilds list (remaining servers)
    mock_remaining_guilds = [MagicMock(), MagicMock()]
    type(test_bot).guilds = PropertyMock(return_value=mock_remaining_guilds)

    with patch("discord_bot.bot.logger") as mock_logger:
        await test_bot.on_guild_remove(mock_guild)

        # Verify removal log
        info_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("Bot removed from server: Removed Server" in call for call in info_calls)
        assert any("2 server(s)" in call for call in info_calls)


# Tests for _on_app_command_error


async def test_on_app_command_error_handles_command_not_found(test_bot: DiscordBot) -> None:
    """Test that _on_app_command_error handles CommandNotFound.

    Args:
        test_bot: Test bot instance
    """
    from discord import app_commands

    # Create mock interaction
    mock_interaction = MagicMock()
    mock_interaction.guild = MagicMock()
    mock_interaction.response.is_done.return_value = False
    mock_interaction.response.send_message = AsyncMock()

    # Create CommandNotFound error (requires name and parents list)
    error = app_commands.CommandNotFound("test_command", [])

    with patch("discord_bot.bot.logger") as mock_logger:
        await test_bot._on_app_command_error(mock_interaction, error)

        # Verify warning was logged
        warning_calls = [
            call
            for call in mock_logger.warning.call_args_list
            if "CommandNotFound" in str(call) and "test_command" in str(call)
        ]
        assert len(warning_calls) > 0

        # Verify user was notified
        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert call_kwargs["ephemeral"] is True


async def test_on_app_command_error_command_not_found_response_already_done(
    test_bot: DiscordBot,
) -> None:
    """Test CommandNotFound when response is already done.

    Args:
        test_bot: Test bot instance
    """
    from discord import app_commands

    mock_interaction = MagicMock()
    mock_interaction.guild = MagicMock()
    mock_interaction.response.is_done.return_value = True
    mock_interaction.response.send_message = AsyncMock()

    error = app_commands.CommandNotFound("test_command", [])

    with patch("discord_bot.bot.logger"):
        await test_bot._on_app_command_error(mock_interaction, error)

        # Should not try to send message when response is done
        mock_interaction.response.send_message.assert_not_called()


async def test_on_app_command_error_command_not_found_http_exception(
    test_bot: DiscordBot,
) -> None:
    """Test CommandNotFound when HTTPException is raised.

    Args:
        test_bot: Test bot instance
    """
    from discord import app_commands

    mock_interaction = MagicMock()
    mock_interaction.guild = MagicMock()
    mock_interaction.response.is_done.return_value = False
    mock_interaction.response.send_message = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(), "Interaction expired")
    )

    error = app_commands.CommandNotFound("test_command", [])

    with patch("discord_bot.bot.logger"):
        # Should not raise - HTTPException is caught
        await test_bot._on_app_command_error(mock_interaction, error)


async def test_on_app_command_error_handles_other_errors(test_bot: DiscordBot) -> None:
    """Test that _on_app_command_error logs other errors.

    Args:
        test_bot: Test bot instance
    """
    from discord import app_commands

    mock_interaction = MagicMock()
    mock_interaction.command = MagicMock()
    mock_interaction.command.name = "failing_command"
    mock_interaction.response.is_done.return_value = False
    mock_interaction.response.send_message = AsyncMock()

    error = app_commands.AppCommandError("Something went wrong")

    with patch("discord_bot.bot.logger") as mock_logger:
        await test_bot._on_app_command_error(mock_interaction, error)

        # Verify error was logged
        error_calls = [
            call for call in mock_logger.error.call_args_list if "failing_command" in str(call)
        ]
        assert len(error_calls) > 0


async def test_on_app_command_error_handles_unknown_command(test_bot: DiscordBot) -> None:
    """Test that _on_app_command_error handles None command.

    Args:
        test_bot: Test bot instance
    """
    from discord import app_commands

    mock_interaction = MagicMock()
    mock_interaction.command = None
    mock_interaction.response.is_done.return_value = False
    mock_interaction.response.send_message = AsyncMock()

    error = app_commands.AppCommandError("Error with unknown command")

    with patch("discord_bot.bot.logger") as mock_logger:
        await test_bot._on_app_command_error(mock_interaction, error)

        # Verify error was logged with "unknown"
        error_calls = [call for call in mock_logger.error.call_args_list if "unknown" in str(call)]
        assert len(error_calls) > 0


class TestAppCommandErrorReply:
    """Unhandled command errors are reported to the user instead of hanging the interaction."""

    async def test_replies_ephemerally_when_not_yet_responded(self, test_bot: DiscordBot) -> None:
        """An error before any response gets an ephemeral initial response."""
        interaction = MagicMock()
        interaction.command.name = "stockpile_add"
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()

        await test_bot._on_app_command_error(
            interaction, discord.app_commands.AppCommandError("db")
        )

        interaction.response.send_message.assert_awaited_once()
        assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True
        interaction.followup.send.assert_not_called()

    async def test_uses_followup_when_already_deferred(self, test_bot: DiscordBot) -> None:
        """An error after defer() is sent as a followup so the "thinking" state resolves."""
        interaction = MagicMock()
        interaction.command.name = "purge"
        interaction.response.is_done.return_value = True
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()

        await test_bot._on_app_command_error(
            interaction, discord.app_commands.AppCommandError("db")
        )

        interaction.followup.send.assert_awaited_once()
        assert interaction.followup.send.call_args.kwargs["ephemeral"] is True
        interaction.response.send_message.assert_not_called()

    async def test_expired_interaction_does_not_raise(self, test_bot: DiscordBot) -> None:
        """A failed reply (expired interaction) is swallowed; the error is already logged."""
        interaction = MagicMock()
        interaction.command.name = "purge"
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(status=404), "Unknown interaction")
        )

        await test_bot._on_app_command_error(
            interaction, discord.app_commands.AppCommandError("db")
        )


class TestStaleCommandRecovery:
    """CommandNotFound means Discord still offers a command the tree lost: heal it."""

    @staticmethod
    def _stale(guild: MagicMock | None, *, autocomplete: bool = False) -> MagicMock:
        interaction = MagicMock()
        interaction.guild = guild
        interaction.type = (
            discord.InteractionType.autocomplete
            if autocomplete
            else discord.InteractionType.application_command
        )
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()
        interaction.response.autocomplete = AsyncMock()
        return interaction

    @staticmethod
    def _guild(guild_id: int = 846) -> MagicMock:
        guild = MagicMock()
        guild.id = guild_id
        guild.name = "Guild"
        return guild

    @staticmethod
    async def _settle(test_bot: DiscordBot) -> None:
        await asyncio.gather(*test_bot._command_recovery_tasks)

    async def test_autocomplete_gets_an_empty_choice_list(self, test_bot: DiscordBot) -> None:
        """An autocomplete cannot take a message; an empty choice list avoids Discord's error."""
        interaction = self._stale(self._guild(), autocomplete=True)

        with patch("discord_bot.bot.logger"):
            await test_bot._on_app_command_error(
                interaction, discord.app_commands.CommandNotFound("stockpile_show", [])
            )
            await self._settle(test_bot)

        interaction.response.autocomplete.assert_awaited_once_with([])
        interaction.response.send_message.assert_not_called()

    async def test_recovers_commands_through_the_cogs(self, test_bot: DiscordBot) -> None:
        """Every cog exposing recover_guild_commands is asked to restore the guild."""
        guild = self._guild()
        healing_cog = MagicMock()
        healing_cog.recover_guild_commands = AsyncMock()
        plain_cog = MagicMock(spec=[])  # no recover_guild_commands attribute
        type(test_bot).cogs = PropertyMock(
            return_value={"Healing": healing_cog, "Plain": plain_cog}
        )

        with patch("discord_bot.bot.logger"):
            await test_bot._on_app_command_error(
                self._stale(guild), discord.app_commands.CommandNotFound("stockpile_show", [])
            )
            await self._settle(test_bot)

        healing_cog.recover_guild_commands.assert_awaited_once_with(guild=guild)

    async def test_recovery_runs_once_per_guild_within_cooldown(self, test_bot: DiscordBot) -> None:
        """A stale command fires one error per keystroke; only the first triggers a recovery."""
        guild = self._guild()
        other_guild = self._guild(guild_id=999)
        healing_cog = MagicMock()
        healing_cog.recover_guild_commands = AsyncMock()
        type(test_bot).cogs = PropertyMock(return_value={"Healing": healing_cog})
        error = discord.app_commands.CommandNotFound("stockpile_show", [])

        with patch("discord_bot.bot.logger"):
            await test_bot._on_app_command_error(self._stale(guild), error)
            await test_bot._on_app_command_error(self._stale(guild, autocomplete=True), error)
            await test_bot._on_app_command_error(self._stale(other_guild), error)
            await self._settle(test_bot)

        assert healing_cog.recover_guild_commands.await_count == 2
        awaited = {c.kwargs["guild"].id for c in healing_cog.recover_guild_commands.await_args_list}
        assert awaited == {guild.id, other_guild.id}

    async def test_no_recovery_outside_a_guild(self, test_bot: DiscordBot) -> None:
        """Commands are registered per guild; a DM interaction has nothing to restore."""
        healing_cog = MagicMock()
        healing_cog.recover_guild_commands = AsyncMock()
        type(test_bot).cogs = PropertyMock(return_value={"Healing": healing_cog})

        with patch("discord_bot.bot.logger"):
            await test_bot._on_app_command_error(
                self._stale(None), discord.app_commands.CommandNotFound("stockpile_show", [])
            )
            await self._settle(test_bot)

        healing_cog.recover_guild_commands.assert_not_awaited()

    async def test_failing_cog_is_logged_and_does_not_stop_the_others(
        self, test_bot: DiscordBot
    ) -> None:
        """One cog's recovery error is logged; the remaining cogs still get their turn."""
        guild = self._guild()
        broken_cog = MagicMock()
        broken_cog.qualified_name = "Broken"
        broken_cog.recover_guild_commands = AsyncMock(side_effect=RuntimeError("db down"))
        healing_cog = MagicMock()
        healing_cog.recover_guild_commands = AsyncMock()
        type(test_bot).cogs = PropertyMock(
            return_value={"Broken": broken_cog, "Healing": healing_cog}
        )

        with patch("discord_bot.bot.logger") as mock_logger:
            await test_bot._on_app_command_error(
                self._stale(guild), discord.app_commands.CommandNotFound("stockpile_show", [])
            )
            await self._settle(test_bot)

        healing_cog.recover_guild_commands.assert_awaited_once_with(guild=guild)
        assert any(
            "Broken" in str(c) and "db down" in str(c) for c in mock_logger.error.call_args_list
        )
