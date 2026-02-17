"""Tipos de purga."""

from enum import StrEnum


class PurgaType(StrEnum):
    """Tipos de purga."""

    WAR_END = "war_end"  # Purga de fin de guerra
    MAINTENANCE = "maintenance"  # Purga de mantenimiento
