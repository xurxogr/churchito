"""Section type enumerations for configurable embeds."""

from enum import StrEnum


class EmbedSectionType(StrEnum):
    """Available section types for building embeds."""

    TEXT = "text"  # Full-width field with title + content
    FIELDS = "fields"  # Inline fields (up to 3 per row)
