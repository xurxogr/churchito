"""Utilidades comunes."""

from discord_bot.common.utils.discord import delete_message, has_any_role
from discord_bot.common.utils.embed_config_columns import (
    EMBED_SECTIONS_COLUMNS,
    get_embed_sections_columns,
)

__all__ = [
    "EMBED_SECTIONS_COLUMNS",
    "delete_message",
    "get_embed_sections_columns",
    "has_any_role",
]
