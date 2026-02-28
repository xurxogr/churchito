"""Modos de procesamiento automático de verificación."""

from enum import StrEnum


class AutoProcessMode(StrEnum):
    """Modos de procesamiento automático de verificaciones."""

    NONE = "none"  # Sin procesamiento automático
    REJECT_ONLY = "reject_only"  # Solo rechazos automáticos
    APPROVE_ONLY = "approve_only"  # Solo aprobaciones automáticas
    BOTH = "both"  # Ambos
