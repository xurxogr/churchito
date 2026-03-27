"""Column definitions for embed configuration tables."""

from typing import Any

from discord_bot.common.enums.embed_section_type import EmbedSectionType

# Columns for embed sections table
EMBED_SECTIONS_COLUMNS: list[dict[str, Any]] = [
    {
        "key": "type",
        "name": "Type",
        "type": "choice",
        "required": True,
        "choices": [
            ("Text", EmbedSectionType.TEXT),
            ("Fields (3 columns)", EmbedSectionType.FIELDS),
        ],
    },
    # Fields for TEXT
    {
        "key": "title",
        "name": "Title",
        "type": "string",
        "required": False,
        "max_length": 256,
        "description": "Field title (displayed in bold)",
        "show_when": {"type": EmbedSectionType.TEXT},
    },
    {
        "key": "content",
        "name": "Content",
        "type": "textarea",
        "required": False,
        "max_length": 1024,
        "description": "Field content. Supports placeholders.",
        "show_when": {"type": EmbedSectionType.TEXT},
    },
    # Fields for FIELDS
    {
        "key": "inline",
        "name": "Inline",
        "type": "boolean",
        "required": False,
        "default": True,
        "description": "Display fields on the same line (max 3 per row)",
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
    {
        "key": "field_1_name",
        "name": "Field 1: Name",
        "type": "string",
        "required": False,
        "max_length": 256,
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
    {
        "key": "field_1_value",
        "name": "Field 1: Value",
        "type": "string",
        "required": False,
        "max_length": 1024,
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
    {
        "key": "field_2_name",
        "name": "Field 2: Name",
        "type": "string",
        "required": False,
        "max_length": 256,
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
    {
        "key": "field_2_value",
        "name": "Field 2: Value",
        "type": "string",
        "required": False,
        "max_length": 1024,
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
    {
        "key": "field_3_name",
        "name": "Field 3: Name",
        "type": "string",
        "required": False,
        "max_length": 256,
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
    {
        "key": "field_3_value",
        "name": "Field 3: Value",
        "type": "string",
        "required": False,
        "max_length": 1024,
        "show_when": {"type": EmbedSectionType.FIELDS},
    },
]


def get_embed_sections_columns() -> list[dict[str, Any]]:
    """Get the columns for an embed sections table.

    Returns:
        List of column definitions for ConfigOption.columns.
    """
    return EMBED_SECTIONS_COLUMNS.copy()
