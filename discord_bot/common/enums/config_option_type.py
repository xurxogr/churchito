"""Enumeraciones de tipos de opciones de configuración."""

from enum import StrEnum


class ConfigOptionType(StrEnum):
    """Tipos de opciones de configuración para cogs."""

    STRING = "string"
    TEXTAREA = "textarea"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    CHANNEL = "channel"
    ROLE = "role"
    CHANNEL_LIST = "channel_list"
    ROLE_LIST = "role_list"
    TEXT_CHOICE = "text_choice"
    TABLE = "table"
    EMBED = "embed"
    EMBED_SECTIONS = "embed_sections"  # Only sections, for appending to existing embeds
