"""Enumeraciones de tipos de secciones para embeds configurables."""

from enum import StrEnum


class EmbedSectionType(StrEnum):
    """Tipos de secciones disponibles para construir embeds."""

    TEXT = "text"
    TEXT_COLORED = "text_colored"
    HEADER = "header"
    PROGRESS = "progress"
    FIELDS = "fields"


class AnsiColor(StrEnum):
    """Colores ANSI disponibles para TEXT_COLORED."""

    GRAY = "gray"
    RED = "red"
    GREEN = "green"
    YELLOW = "yellow"
    BLUE = "blue"
    PINK = "pink"
    CYAN = "cyan"
    WHITE = "white"
