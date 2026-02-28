"""Modos de comparación de nombre para verificación."""

from enum import StrEnum


class NameMatchMode(StrEnum):
    """Modos de comparación entre nombre de Discord y nombre del juego."""

    NONE = "none"  # No comprobar
    EXACT = "exact"  # Comparación exacta
    CONTAINS = "contains"  # Uno debe contener al otro
