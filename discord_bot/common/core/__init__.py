"""Configuration module for the application."""

from functools import lru_cache

from discord_bot.common.core.app_settings import AppSettings


@lru_cache
def get_settings() -> AppSettings:
    """Get the application settings.

    Returns:
        AppSettings: The settings
    """
    return AppSettings()


# Alias for compatibility
get_app_settings = get_settings


__all__ = [
    "AppSettings",
    "get_app_settings",
    "get_settings",
]
