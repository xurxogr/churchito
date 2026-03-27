"""Purge types."""

from enum import StrEnum


class PurgeType(StrEnum):
    """Purge types."""

    WAR_END = "war_end"  # War end purge
    GLOBAL = "global"  # Global purge (all except excluded)
