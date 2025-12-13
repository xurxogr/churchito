"""Módulo de configuración para la aplicación."""

from functools import lru_cache

from discord_bot.common.core.app_settings import AppSettings


@lru_cache
def get_settings() -> AppSettings:
    """Obtiene la configuración.

    Returns:
        AppSettings: La configuración
    """
    return AppSettings()


__all__ = [
    "AppSettings",
    "get_settings",
]
