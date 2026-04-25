"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from discord_bot.common.core import AppSettings
from discord_bot.common.core.settings.bot import BotSettings
from discord_bot.common.core.settings.database import DatabaseSettings
from discord_bot.common.core.settings.logging import LoggingSettings
from discord_bot.common.models.base import Base
from discord_bot.common.services import DatabaseService


@pytest.fixture
def test_bot_settings() -> BotSettings:
    """Create test bot settings.

    Returns:
        BotSettings: Test bot settings
    """
    return BotSettings(
        token="test_token_123",
        command_prefix="!",
        owner_id=123456789,
        description="Test bot",
    )


@pytest.fixture
def test_logging_settings() -> LoggingSettings:
    """Create test logging settings.

    Returns:
        LoggingSettings: Test logging settings
    """
    return LoggingSettings(
        log_level="DEBUG",
        log_file=None,
    )


@pytest.fixture
def test_database_settings() -> DatabaseSettings:
    """Create test database settings with in-memory SQLite.

    Returns:
        DatabaseSettings: Test database settings
    """
    return DatabaseSettings(
        url="sqlite+aiosqlite:///:memory:",
        echo=False,
    )


@pytest.fixture
def test_settings(
    test_bot_settings: BotSettings,
    test_logging_settings: LoggingSettings,
    test_database_settings: DatabaseSettings,
) -> AppSettings:
    """Create test application settings.

    Args:
        test_bot_settings: Test bot settings
        test_logging_settings: Test logging settings
        test_database_settings: Test database settings

    Returns:
        AppSettings: Test application settings
    """
    return AppSettings(
        bot=test_bot_settings,
        logging=test_logging_settings,
        database=test_database_settings,
    )


@pytest.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a test database engine with in-memory SQLite.

    Returns:
        AsyncEngine: Test database engine
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()
    # Small delay to let aiosqlite worker thread finish before event loop closes
    await asyncio.sleep(0.01)


@pytest.fixture
async def test_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session.

    Args:
        test_engine: Test database engine

    Returns:
        AsyncSession: Test database session
    """
    session_maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        yield session


@pytest.fixture
async def test_database(
    test_database_settings: DatabaseSettings,
) -> AsyncGenerator[DatabaseService, None]:
    """Create a test database service.

    Args:
        test_database_settings: Test database settings

    Returns:
        DatabaseService: Test database service
    """
    db = DatabaseService(test_database_settings)
    await db.initialize()

    # Create tables
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield db

    await db.close()
    # Small delay to let aiosqlite worker thread finish before event loop closes
    await asyncio.sleep(0.01)


@pytest.fixture
def mock_discord_user() -> MagicMock:
    """Create a mock Discord user.

    Returns:
        MagicMock: Mock Discord user
    """
    user = MagicMock(spec=discord.User)
    user.id = 123456789
    user.name = "TestUser"
    user.discriminator = "0001"
    user.bot = False
    return user


@pytest.fixture
def mock_discord_guild() -> MagicMock:
    """Create a mock Discord guild.

    Returns:
        MagicMock: Mock Discord guild
    """
    guild = MagicMock(spec=discord.Guild)
    guild.id = 987654321
    guild.name = "Test Guild"
    return guild


@pytest.fixture
def mock_discord_member(mock_discord_user: MagicMock, mock_discord_guild: MagicMock) -> MagicMock:
    """Create a mock Discord member.

    Args:
        mock_discord_user: Mock Discord user
        mock_discord_guild: Mock Discord guild

    Returns:
        MagicMock: Mock Discord member
    """
    member = MagicMock(spec=discord.Member)
    member.id = mock_discord_user.id
    member.name = mock_discord_user.name
    member.guild = mock_discord_guild
    return member


@pytest.fixture
def mock_discord_channel() -> MagicMock:
    """Create a mock Discord text channel.

    Returns:
        MagicMock: Mock Discord text channel
    """
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 111222333
    channel.name = "test-channel"
    channel.send = AsyncMock()
    return channel


@pytest.fixture
def mock_discord_message(
    mock_discord_user: MagicMock, mock_discord_channel: MagicMock
) -> MagicMock:
    """Create a mock Discord message.

    Args:
        mock_discord_user: Mock Discord user
        mock_discord_channel: Mock Discord channel

    Returns:
        MagicMock: Mock Discord message
    """
    message = MagicMock(spec=discord.Message)
    message.id = 444555666
    message.content = "!test"
    message.author = mock_discord_user
    message.channel = mock_discord_channel
    message.guild = mock_discord_channel.guild
    return message


@pytest.fixture
def mock_context(mock_discord_message: MagicMock, mock_discord_channel: MagicMock) -> MagicMock:
    """Create a mock Discord command context.

    Args:
        mock_discord_message: Mock Discord message
        mock_discord_channel: Mock Discord channel

    Returns:
        MagicMock: Mock Discord context
    """
    ctx = MagicMock(spec=commands.Context)
    ctx.message = mock_discord_message
    ctx.author = mock_discord_message.author
    ctx.channel = mock_discord_channel
    ctx.guild = mock_discord_channel.guild
    ctx.send = AsyncMock()
    ctx.reply = AsyncMock()
    ctx.command = MagicMock()
    ctx.command.name = "test_command"
    return ctx


@pytest.fixture
def mock_bot(test_settings: AppSettings) -> MagicMock:
    """Create a mock Discord bot.

    Args:
        test_settings: Test application settings

    Returns:
        MagicMock: Mock Discord bot
    """
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock(spec=discord.ClientUser)
    bot.user.id = 999888777
    bot.user.name = "TestBot"
    bot.latency = 0.05
    bot.guilds = []
    bot.command_prefix = test_settings.bot.command_prefix
    bot.add_cog = AsyncMock()
    bot.load_extension = AsyncMock()
    bot.close = AsyncMock()
    return bot
