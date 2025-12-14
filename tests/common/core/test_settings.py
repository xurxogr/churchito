"""Tests para la configuración de devops."""

from discord_bot.common.core import AppSettings, get_settings
from discord_bot.common.core.settings.bot import BotSettings
from discord_bot.common.core.settings.database import DatabaseSettings
from discord_bot.common.core.settings.logging import LoggingSettings


def test_bot_settings_default() -> None:
    """Probar opciones por defecto de BotSettings."""
    settings = BotSettings(token="test_token")

    assert settings.token == "test_token"
    assert settings.command_prefix == "!"
    assert settings.owner_id is None
    assert settings.description == "Un bot de Discord con arquitectura basada en cogs"


def test_logging_settings_default() -> None:
    """Probar opciones por defecto de LoggingSettings."""
    settings = LoggingSettings()

    assert settings.log_level == "INFO"
    assert settings.log_file is None
    assert settings.rotate_logs is False
    assert len(settings.loggers) == 0


def test_database_settings_default() -> None:
    """Probar opciones por defecto de DatabaseSettings."""
    settings = DatabaseSettings()

    assert settings.url == "sqlite+aiosqlite:///data/bot.db"
    assert settings.echo is False
    assert settings.pool_recycle == 3600


def test_app_settings_creation(test_settings: AppSettings) -> None:
    """Probar creación de AppSettings.

    Args:
        test_settings (AppSettings): Instancia de configuración de la aplicación para pruebas
    """
    assert test_settings.bot.token == "test_token_123"
    assert test_settings.bot.command_prefix == "!"
    assert test_settings.logging.log_level == "DEBUG"
    assert test_settings.database.url == "sqlite+aiosqlite:///:memory:"


def test_get_settings_singleton() -> None:
    """Probar que se devuelve un singleton."""
    settings1 = get_settings()
    settings2 = get_settings()

    assert settings1 is settings2
