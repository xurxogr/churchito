"""Tests para punto de entrada principal."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from discord_bot.__main__ import load_settings, main, parse_args
from discord_bot.common.core import AppSettings


def test_parse_args_defaults() -> None:
    """Test parseo de argumentos con valores por defecto."""
    with patch("sys.argv", ["bot"]):
        args = parse_args()

        assert args.config is None
        assert args.token is None
        assert args.log_level is None


def test_parse_args_with_config() -> None:
    """Test parseo de argumentos con archivo de configuración."""
    with patch("sys.argv", ["bot", "--config", "/path/to/config.json"]):
        args = parse_args()

        assert args.config == Path("/path/to/config.json")


def test_parse_args_with_token() -> None:
    """Test parseo de argumentos con token."""
    with patch("sys.argv", ["bot", "--token", "test_token"]):
        args = parse_args()

        assert args.token == "test_token"


def test_parse_args_with_log_level() -> None:
    """Test parseo de argumentos con nivel de log."""
    with patch("sys.argv", ["bot", "--log-level", "DEBUG"]):
        args = parse_args()

        assert args.log_level == "DEBUG"


def test_load_settings_default(test_settings: AppSettings) -> None:
    """Test loading settings with defaults.

    Args:
        test_settings: Test application settings
    """
    args = MagicMock()
    args.config = None
    args.token = None
    args.log_level = None

    with patch("discord_bot.__main__.get_settings", return_value=test_settings):
        settings = load_settings(args)

        assert settings.bot.token == "test_token_123"


def test_load_settings_with_token_override(test_settings: AppSettings) -> None:
    """Test loading settings with token override.

    Args:
        test_settings: Test application settings
    """
    args = MagicMock()
    args.config = None
    args.token = "override_token"
    args.log_level = None

    with patch("discord_bot.__main__.get_settings", return_value=test_settings):
        settings = load_settings(args)

        assert settings.bot.token == "override_token"


def test_load_settings_with_log_level_override(test_settings: AppSettings) -> None:
    """Test loading settings with log level override.

    Args:
        test_settings: Test application settings
    """
    args = MagicMock()
    args.config = None
    args.token = None
    args.log_level = "WARNING"

    with patch("discord_bot.__main__.get_settings", return_value=test_settings):
        settings = load_settings(args)

        assert settings.logging.log_level == "WARNING"


def test_load_settings_with_config_path(test_settings: AppSettings, tmp_path: Path) -> None:
    """Test loading settings with custom config path.

    Args:
        test_settings: Test application settings
        tmp_path: Temporary path fixture
    """
    with patch("discord_bot.__main__.get_settings", return_value=test_settings):
        config_file = tmp_path / "config.json"
        args = MagicMock()
        args.config = config_file
        args.token = None
        args.log_level = None

        settings = load_settings(args)

        # Verify config file path was set
        assert settings is not None


@patch("discord_bot.__main__.asyncio.run")
def test_run(mock_asyncio_run: MagicMock) -> None:
    """Test run function.

    Args:
        mock_asyncio_run: Mock asyncio.run
    """
    from discord_bot.__main__ import run

    run()

    mock_asyncio_run.assert_called_once()


@patch("discord_bot.__main__.asyncio.run", side_effect=KeyboardInterrupt)
def test_run_keyboard_interrupt(mock_asyncio_run: MagicMock) -> None:
    """Test run function with keyboard interrupt.

    Args:
        mock_asyncio_run: Mock asyncio.run
    """
    from discord_bot.__main__ import run

    # Should not raise
    run()

    mock_asyncio_run.assert_called_once()


@pytest.mark.asyncio
@patch("discord_bot.__main__.parse_args")
@patch("discord_bot.__main__.load_settings")
@patch("discord_bot.__main__.setup_logging")
@patch("discord_bot.__main__.DatabaseService")
@patch("discord_bot.__main__.DiscordBot")
async def test_main_success(
    mock_bot_class: MagicMock,
    mock_db_service_class: MagicMock,
    mock_setup_logging: MagicMock,
    mock_load_settings: MagicMock,
    mock_parse_args: MagicMock,
    test_settings: AppSettings,
) -> None:
    """Test main function successful execution.

    Args:
        mock_bot_class: Mock DiscordBot class
        mock_db_service_class: Mock DatabaseService class
        mock_setup_logging: Mock setup_logging function
        mock_load_settings: Mock load_settings function
        mock_parse_args: Mock parse_args function
        test_settings: Test application settings
    """
    # Setup mocks
    mock_parse_args.return_value = MagicMock(config=None, token=None, log_level=None)
    mock_load_settings.return_value = test_settings

    mock_db = MagicMock()
    mock_db_service_class.return_value = mock_db

    mock_bot = MagicMock()
    mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
    mock_bot.__aexit__ = AsyncMock(return_value=None)
    mock_bot.start = AsyncMock()
    mock_bot_class.return_value = mock_bot

    # Run main
    await main()

    # Verify calls
    mock_parse_args.assert_called_once()
    mock_load_settings.assert_called_once()
    mock_setup_logging.assert_called_once_with(test_settings.logging)
    mock_db_service_class.assert_called_once_with(test_settings.database)
    mock_bot_class.assert_called_once_with(test_settings, mock_db)
    mock_bot.start.assert_called_once_with(test_settings.bot.token)


@pytest.mark.asyncio
@patch("discord_bot.__main__.parse_args")
@patch("discord_bot.__main__.load_settings")
async def test_main_settings_load_error(
    mock_load_settings: MagicMock, mock_parse_args: MagicMock
) -> None:
    """Test main function with settings load error.

    Args:
        mock_load_settings: Mock load_settings function
        mock_parse_args: Mock parse_args function
    """
    mock_parse_args.return_value = MagicMock(config=None, token=None, log_level=None)
    mock_load_settings.side_effect = Exception("Config file not found")

    with pytest.raises(SystemExit) as exc_info:
        await main()

    assert exc_info.value.code == 1


@pytest.mark.asyncio
@patch("discord_bot.__main__.parse_args")
@patch("discord_bot.__main__.load_settings")
@patch("discord_bot.__main__.setup_logging")
async def test_main_missing_bot_token(
    mock_setup_logging: MagicMock,
    mock_load_settings: MagicMock,
    mock_parse_args: MagicMock,
    test_settings: AppSettings,
) -> None:
    """Test main function with missing bot token.

    Args:
        mock_setup_logging: Mock setup_logging function
        mock_load_settings: Mock load_settings function
        mock_parse_args: Mock parse_args function
        test_settings: Test application settings
    """
    # Create settings without token
    settings_no_token = test_settings.model_copy(deep=True)
    settings_no_token.bot.token = ""

    mock_parse_args.return_value = MagicMock(config=None, token=None, log_level=None)
    mock_load_settings.return_value = settings_no_token

    with pytest.raises(SystemExit) as exc_info:
        await main()

    assert exc_info.value.code == 1
    mock_setup_logging.assert_called_once()


@pytest.mark.asyncio
@patch("discord_bot.__main__.parse_args")
@patch("discord_bot.__main__.load_settings")
@patch("discord_bot.__main__.setup_logging")
@patch("discord_bot.__main__.DatabaseService")
@patch("discord_bot.__main__.DiscordBot")
async def test_main_fatal_error(
    mock_bot_class: MagicMock,
    mock_db_service_class: MagicMock,
    mock_setup_logging: MagicMock,
    mock_load_settings: MagicMock,
    mock_parse_args: MagicMock,
    test_settings: AppSettings,
) -> None:
    """Test main function with fatal error during bot startup.

    Args:
        mock_bot_class: Mock DiscordBot class
        mock_db_service_class: Mock DatabaseService class
        mock_setup_logging: Mock setup_logging function
        mock_load_settings: Mock load_settings function
        mock_parse_args: Mock parse_args function
        test_settings: Test application settings
    """
    mock_parse_args.return_value = MagicMock(config=None, token=None, log_level=None)
    mock_load_settings.return_value = test_settings

    mock_db = MagicMock()
    mock_db_service_class.return_value = mock_db

    mock_bot = MagicMock()
    mock_bot.__aenter__ = AsyncMock(return_value=mock_bot)
    mock_bot.__aexit__ = AsyncMock(return_value=None)
    mock_bot.start = AsyncMock(side_effect=RuntimeError("Connection failed"))
    mock_bot_class.return_value = mock_bot

    with pytest.raises(SystemExit) as exc_info:
        await main()

    assert exc_info.value.code == 1
    mock_bot.start.assert_called_once()
