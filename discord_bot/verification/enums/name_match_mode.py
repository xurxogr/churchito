"""Name comparison modes for verification."""

from enum import StrEnum


class NameMatchMode(StrEnum):
    """Comparison modes between Discord name and game name."""

    NONE = "none"  # Don't check
    EXACT = "exact"  # Exact comparison
    CONTAINS = "contains"  # One must contain the other
