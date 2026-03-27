"""Deployment configuration for the purge cog.

These settings are global (affect all guilds) and are configured
via environment variables or JSON file. Not editable from the web UI.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

CONFIG_FILE = Path.home() / ".config" / "discord-bot" / "purge.json"


class PurgeSettings(BaseSettings):
    """Deployment configuration for the purge cog.

    These values override or restrict per-guild configuration.
    """

    test_mode_allowed: bool = Field(
        default=False,
        description="If False, test mode is disabled for all guilds",
    )

    model_config = SettingsConfigDict(
        env_prefix="PURGE__",
        env_file=".env",
        env_file_encoding="utf-8",
        json_file=str(CONFIG_FILE),
        json_file_encoding="utf-8",
        extra="ignore",
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
        """Customize configuration sources.

        Priority (highest to lowest):
        1. Environment variables
        2. .env file
        3. JSON file
        4. Default values
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            JsonConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


# Singleton to avoid reloading settings on each use
_settings: PurgeSettings | None = None


def get_purge_settings() -> PurgeSettings:
    """Get the purge cog settings instance.

    Returns:
        PurgeSettings: Deployment configuration.
    """
    global _settings
    if _settings is None:
        _settings = PurgeSettings()
    return _settings
