"""Tests for event type enum."""

from discord_bot.common.enums.event_type import EventType


def test_event_type_values() -> None:
    """Test event type enum values."""
    assert EventType.BOT_READY.value == "bot.ready"
    assert EventType.BOT_SHUTDOWN.value == "bot.shutdown"
    assert EventType.MEMBER_JOIN.value == "member.join"
    assert EventType.MEMBER_LEAVE.value == "member.leave"
    assert EventType.MESSAGE_RECEIVED.value == "message.received"
    assert EventType.COMMAND_EXECUTED.value == "command.executed"
    assert EventType.COMMAND_ERROR.value == "command.error"


def test_event_type_is_string() -> None:
    """Test that event types are strings."""
    assert isinstance(EventType.BOT_READY.value, str)
    assert isinstance(EventType.MEMBER_JOIN.value, str)
