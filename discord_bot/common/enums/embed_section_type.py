"""Enumeraciones de tipos de secciones para embeds configurables."""

from enum import StrEnum


class EmbedSectionType(StrEnum):
    """Tipos de secciones disponibles para construir embeds."""

    TEXT = "text"
    HEADER = "header"
    PROGRESS = "progress"
    FIELDS = "fields"
