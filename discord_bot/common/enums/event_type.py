"""Event type enumerations."""

from enum import StrEnum


class EventType(StrEnum):
    """Event types for the event bus."""

    BOT_READY = "bot.ready"
    BOT_SHUTDOWN = "bot.shutdown"
