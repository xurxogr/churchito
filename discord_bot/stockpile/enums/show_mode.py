"""Display modes for the stockpile show command."""

from enum import StrEnum


class ShowMode(StrEnum):
    """How the show command renders the stockpiles a member can view.

    DETAILED sends one configurable embed per stockpile (creator, roles,
    dates...). COMPACT sends a single embed listing name and code, grouped
    by location, which stays readable with many stockpiles.
    """

    DETAILED = "detailed"
    COMPACT = "compact"
