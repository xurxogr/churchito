"""Modos de procesamiento automático de verificación."""

from enum import StrEnum


class AutoProcessMode(StrEnum):
    """Modos de procesamiento automático de verificaciones."""

    NONE = "none"
    REJECT_ONLY = "reject_only"
    APPROVE_ONLY = "approve_only"
    BOTH = "both"
