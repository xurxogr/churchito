"""Configuración de despliegue para el cog de purga.

Estos settings son globales (afectan a todos los guilds) y se configuran
mediante variables de entorno o archivo JSON. No son editables desde la web UI.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

CONFIG_FILE = Path.home() / ".config" / "discord-bot" / "purga.json"


class PurgaSettings(BaseSettings):
    """Configuración de despliegue del cog de purga.

    Estos valores sobrescriben o restringen la configuración por guild.
    """

    test_mode_allowed: bool = Field(
        default=False,
        description="Si False, el modo prueba está deshabilitado para todos los guilds",
    )

    model_config = SettingsConfigDict(
        env_prefix="PURGA__",
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
        """Personalizar las fuentes de configuración.

        Prioridad (mayor a menor):
        1. Variables de entorno
        2. Archivo .env
        3. Archivo JSON
        4. Valores por defecto
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            JsonConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


# Singleton para evitar recargar settings en cada uso
_settings: PurgaSettings | None = None


def get_purga_settings() -> PurgaSettings:
    """Obtener la instancia de settings del cog de purga.

    Returns:
        PurgaSettings: Configuración de despliegue.
    """
    global _settings
    if _settings is None:
        _settings = PurgaSettings()
    return _settings
