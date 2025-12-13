"""Tests for general cog."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from discord.ext import commands

from discord_bot.general.cog import GeneralCog, setup


@pytest.fixture
def mock_bot() -> MagicMock:
    """Create a mock Discord bot.

    Returns:
        MagicMock: Mocked bot instance
    """
    bot = MagicMock(spec=commands.Bot)
    bot.latency = 0.05  # 50ms latency
    bot.command_prefix = "!"

    # Mock guilds
    type(bot).guilds = PropertyMock(return_value=[MagicMock(), MagicMock()])

    # Mock user
    mock_user = MagicMock()
    mock_user.name = "TestBot"
    mock_user.id = 123456789
    type(bot).user = PropertyMock(return_value=mock_user)

    return bot


@pytest.fixture
def general_cog(mock_bot: MagicMock) -> GeneralCog:
    """Create a GeneralCog instance.

    Args:
        mock_bot: Mock bot fixture

    Returns:
        GeneralCog: General cog instance
    """
    return GeneralCog(mock_bot)


@pytest.fixture
def mock_context(mock_bot: MagicMock) -> MagicMock:
    """Create a mock command context.

    Args:
        mock_bot: Mock bot fixture

    Returns:
        MagicMock: Mocked context
    """
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.author = MagicMock()
    ctx.author.name = "TestUser"
    ctx.author.id = 987654321
    return ctx


def test_general_cog_initialization(mock_bot: MagicMock) -> None:
    """Test GeneralCog initialization.

    Args:
        mock_bot: Mock bot fixture
    """
    cog = GeneralCog(mock_bot)
    assert cog.bot == mock_bot


async def test_ping_command(
    general_cog: GeneralCog, mock_context: MagicMock, mock_bot: MagicMock
) -> None:
    """Test ping command.

    Args:
        general_cog: General cog fixture
        mock_context: Mock context fixture
        mock_bot: Mock bot fixture
    """
    with patch("discord_bot.general.cog.logger") as mock_logger:
        # Call the underlying command function directly (bypasses decorator complexity)
        # Type ignore needed: mypy doesn't understand discord.py's callback pattern
        await general_cog.ping.callback(general_cog, mock_context)  # type: ignore[call-arg, arg-type]

        # Verify message was sent
        mock_context.send.assert_called_once()
        sent_message = mock_context.send.call_args[0][0]
        assert "Pong!" in sent_message
        assert "50ms" in sent_message  # bot.latency = 0.05 * 1000 = 50ms

        # Verify logging
        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]
        assert "ping ejecutado" in log_message
        assert "50ms" in log_message


async def test_ping_command_with_high_latency(
    general_cog: GeneralCog, mock_context: MagicMock, mock_bot: MagicMock
) -> None:
    """Test ping command with high latency.

    Args:
        general_cog: General cog fixture
        mock_context: Mock context fixture
        mock_bot: Mock bot fixture
    """
    # Set high latency
    mock_bot.latency = 0.123  # 123ms

    await general_cog.ping.callback(general_cog, mock_context)  # type: ignore[call-arg, arg-type]

    sent_message = mock_context.send.call_args[0][0]
    assert "123ms" in sent_message


async def test_info_command(
    general_cog: GeneralCog, mock_context: MagicMock, mock_bot: MagicMock
) -> None:
    """Test info command.

    Args:
        general_cog: General cog fixture
        mock_context: Mock context fixture
        mock_bot: Mock bot fixture
    """
    with patch("discord_bot.general.cog.logger") as mock_logger:
        await general_cog.info.callback(general_cog, mock_context)  # type: ignore[call-arg, arg-type]

        # Verify message was sent
        mock_context.send.assert_called_once()
        sent_message = mock_context.send.call_args[0][0]

        # Check all expected information is present
        assert "Información del Bot" in sent_message
        assert "TestBot" in sent_message  # bot name
        assert "Servidores: 2" in sent_message  # guild count
        assert "Prefijo: `!`" in sent_message  # command prefix

        # Verify logging
        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]
        assert "info ejecutado" in log_message


async def test_info_command_no_user(
    general_cog: GeneralCog, mock_context: MagicMock, mock_bot: MagicMock
) -> None:
    """Test info command when bot.user is None.

    Args:
        general_cog: General cog fixture
        mock_context: Mock context fixture
        mock_bot: Mock bot fixture
    """
    # Set user to None
    type(mock_bot).user = PropertyMock(return_value=None)

    await general_cog.info.callback(general_cog, mock_context)  # type: ignore[call-arg, arg-type]

    sent_message = mock_context.send.call_args[0][0]
    assert "Desconocido" in sent_message


async def test_info_command_with_list_prefix(
    general_cog: GeneralCog, mock_context: MagicMock, mock_bot: MagicMock
) -> None:
    """Test info command with list of prefixes.

    Args:
        general_cog: General cog fixture
        mock_context: Mock context fixture
        mock_bot: Mock bot fixture
    """
    # Set command prefix to a list
    mock_bot.command_prefix = ["!", "?", "$"]

    await general_cog.info.callback(general_cog, mock_context)  # type: ignore[call-arg, arg-type]

    sent_message = mock_context.send.call_args[0][0]
    # Should display all prefixes
    assert "Prefijo:" in sent_message


async def test_info_command_with_callable_prefix(
    general_cog: GeneralCog, mock_context: MagicMock, mock_bot: MagicMock
) -> None:
    """Test info command with callable prefix.

    Args:
        general_cog: General cog fixture
        mock_context: Mock context fixture
        mock_bot: Mock bot fixture
    """
    # Set command prefix to a callable
    mock_bot.command_prefix = lambda bot, msg: "!"

    await general_cog.info.callback(general_cog, mock_context)  # type: ignore[call-arg, arg-type]

    sent_message = mock_context.send.call_args[0][0]
    assert "Prefijo:" in sent_message


async def test_setup_function() -> None:
    """Test the setup function adds the cog to the bot."""
    mock_bot = MagicMock(spec=commands.Bot)
    mock_bot.add_cog = AsyncMock()

    await setup(mock_bot)

    # Verify add_cog was called once
    mock_bot.add_cog.assert_called_once()

    # Verify the argument is a GeneralCog instance
    added_cog = mock_bot.add_cog.call_args[0][0]
    assert isinstance(added_cog, GeneralCog)
    assert added_cog.bot == mock_bot
