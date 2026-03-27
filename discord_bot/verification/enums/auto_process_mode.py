"""Automatic verification processing modes."""

from enum import StrEnum


class AutoProcessMode(StrEnum):
    """Automatic verification processing modes."""

    NONE = "none"  # No automatic processing
    REJECT_ONLY = "reject_only"  # Automatic rejections only
    APPROVE_ONLY = "approve_only"  # Automatic approvals only
    BOTH = "both"  # Both
