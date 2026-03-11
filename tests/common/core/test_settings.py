"""Tests para la configuración de devops."""

import pytest

from discord_bot.common.core import AppSettings, get_settings
from discord_bot.common.core.settings.bot import BotSettings
from discord_bot.common.core.settings.database import DatabaseSettings
from discord_bot.common.core.settings.logging import LoggingSettings
from discord_bot.common.core.settings.web import MIN_DISCORD_SNOWFLAKE, WebSettings


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


class TestWebSettings:
    """Tests para WebSettings."""

    def test_web_settings_default(self) -> None:
        """Probar opciones por defecto de WebSettings."""
        settings = WebSettings()

        assert settings.enabled is False
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.owner_ids == []

    def test_valid_owner_ids(self) -> None:
        """Probar que owner_ids válidos son aceptados."""
        valid_id = 123456789012345678  # 18 dígitos, válido
        settings = WebSettings(owner_ids=[valid_id])

        assert settings.owner_ids == [valid_id]

    def test_multiple_valid_owner_ids(self) -> None:
        """Probar múltiples owner_ids válidos."""
        ids = [123456789012345678, 987654321098765432]
        settings = WebSettings(owner_ids=ids)

        assert settings.owner_ids == ids

    def test_invalid_owner_id_too_small(self) -> None:
        """Probar que owner_id muy pequeño es rechazado."""
        invalid_id = 12345  # Muy pequeño para ser un snowflake

        with pytest.raises(ValueError) as exc_info:
            WebSettings(owner_ids=[invalid_id])

        assert "snowflake válido" in str(exc_info.value)
        assert str(invalid_id) in str(exc_info.value)

    def test_invalid_owner_id_mixed(self) -> None:
        """Probar que mezcla de IDs válidos e inválidos es rechazada."""
        valid_id = 123456789012345678
        invalid_id = 999

        with pytest.raises(ValueError) as exc_info:
            WebSettings(owner_ids=[valid_id, invalid_id])

        assert str(invalid_id) in str(exc_info.value)

    def test_min_discord_snowflake_constant(self) -> None:
        """Probar que la constante MIN_DISCORD_SNOWFLAKE es razonable."""
        # Debe ser al menos 17 dígitos (Discord empezó en 2015)
        assert MIN_DISCORD_SNOWFLAKE >= 10**16
        # Pero no demasiado grande
        assert MIN_DISCORD_SNOWFLAKE < 10**18
