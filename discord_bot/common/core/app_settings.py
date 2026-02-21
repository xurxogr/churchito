"""Configuración principal de la aplicación."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from discord_bot.common.core.settings.bot import BotSettings
from discord_bot.common.core.settings.database import DatabaseSettings
from discord_bot.common.core.settings.logging import LoggingSettings
from discord_bot.common.core.settings.verification import VerificationSettings
from discord_bot.common.core.settings.web import WebSettings


class AppSettings(BaseSettings):
    """Configuración principal de la aplicación."""

    bot: BotSettings = Field(default_factory=BotSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    web: WebSettings = Field(default_factory=WebSettings)
    verification: VerificationSettings = Field(default_factory=VerificationSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="forbid",
        json_file=str(Path.home() / ".config" / "discord-bot" / "config.json"),
        json_file_encoding="utf-8",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources to include JSON file support.

        Priority order (highest to lowest):
        1. Init settings (passed directly to constructor)
        2. Environment variables
        3. .env file
        4. JSON config file
        5. Default values
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            JsonConfigSettingsSource(settings_cls),
            file_secret_settings,
        )
