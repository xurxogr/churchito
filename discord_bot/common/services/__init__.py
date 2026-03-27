"""Common services."""

from discord_bot.common.services.config_schema_service import (
    ConfigSchemaService,
    get_config_schema_service,
)
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.database import DatabaseService
from discord_bot.common.services.embed_builder import (
    ANSI_COLORS,
    COLOR_TAGS,
    DOT_EMOJIS,
    GLOBAL_PLACEHOLDERS,
    EmbedFieldLimitError,
    PlaceholderContext,
    build_embed,
    build_embed_from_rows,
    create_progress_bar,
    format_placeholders,
    format_with_colors,
)

__all__ = [
    "ANSI_COLORS",
    "COLOR_TAGS",
    "ConfigSchemaService",
    "ConfigService",
    "DOT_EMOJIS",
    "DatabaseService",
    "EmbedFieldLimitError",
    "GLOBAL_PLACEHOLDERS",
    "PlaceholderContext",
    "build_embed",
    "build_embed_from_rows",
    "create_progress_bar",
    "format_placeholders",
    "format_with_colors",
    "get_config_schema_service",
]
