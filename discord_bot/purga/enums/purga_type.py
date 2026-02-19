"""Tipos de purga."""

from enum import StrEnum


class PurgaType(StrEnum):
    """Tipos de purga."""

    WAR_END = "war_end"  # Purga de fin de guerra
    GLOBAL = "global"  # Purga global (todos excepto excluidos)
