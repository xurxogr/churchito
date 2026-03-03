"""Enumeraciones de tipos de secciones para embeds configurables."""

from enum import StrEnum


class EmbedSectionType(StrEnum):
    """Tipos de secciones disponibles para construir embeds."""

    TEXT = "text"  # Full-width field with title + content
    FIELDS = "fields"  # Inline fields (up to 3 per row)
