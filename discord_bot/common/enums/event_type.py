"""Enumeraciones de tipos de eventos."""

from enum import StrEnum


class EventType(StrEnum):
    """Tipos de eventos para el bus de eventos."""

    BOT_READY = "bot.ready"
    BOT_SHUTDOWN = "bot.shutdown"
    MEMBER_JOIN = "member.join"
    MEMBER_LEAVE = "member.leave"
    MESSAGE_RECEIVED = "message.received"
    COMMAND_EXECUTED = "command.executed"
    COMMAND_ERROR = "command.error"
