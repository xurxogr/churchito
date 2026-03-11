"""Utilidades comunes."""

from discord_bot.common.utils.discord import (
    DISCORD_CDN_DOMAINS,
    delete_message,
    has_any_role,
    is_valid_discord_cdn_url,
)
from discord_bot.common.utils.embed_config_columns import (
    EMBED_SECTIONS_COLUMNS,
    get_embed_sections_columns,
)

__all__ = [
    "DISCORD_CDN_DOMAINS",
    "EMBED_SECTIONS_COLUMNS",
    "delete_message",
    "get_embed_sections_columns",
    "has_any_role",
    "is_valid_discord_cdn_url",
]
