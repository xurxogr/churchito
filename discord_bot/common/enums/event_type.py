"""Event type enumerations."""

from enum import StrEnum


class EventType(StrEnum):
    """Event types for the event bus."""

    BOT_READY = "bot.ready"
    BOT_SHUTDOWN = "bot.shutdown"
    MEMBER_JOIN = "member.join"
    MEMBER_LEAVE = "member.leave"
    MESSAGE_RECEIVED = "message.received"
    COMMAND_EXECUTED = "command.executed"
    COMMAND_ERROR = "command.error"
