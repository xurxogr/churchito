"""Rejection types for verification."""

from enum import StrEnum


class RejectType(StrEnum):
    """Types of verification rejection.

    Used to identify the reason for rejection and control auto-rejection per type.
    Order: Invalid screenshots -> Faction -> Shard -> Regiment -> Name -> Time diff
    """

    INVALID_SCREENSHOTS = "invalid_screenshots"  # API 422 - unreadable screenshots
    WRONG_FACTION = "wrong_faction"  # Wrong faction
    WRONG_SHARD = "wrong_shard"  # Wrong shard
    HAS_REGIMENT = "has_regiment"  # User has (wrong) regiment
    NAME_MISMATCH = "name_mismatch"  # Discord name doesn't match game name
    TIME_DIFF = "time_diff"  # Screenshot too old
