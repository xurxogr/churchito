"""Tests for the event bus."""

from discord_bot.common.services.event_bus import EventBus, get_event_bus


def test_get_event_bus_singleton() -> None:
    """Test that get_event_bus returns the same instance."""
    bus1 = get_event_bus()
    bus2 = get_event_bus()

    assert bus1 is bus2


def test_emit_no_subscribers() -> None:
    """Test that emit works with no subscribers."""
    event_bus = EventBus()
    # Should not raise
    event_bus.emit("test.event", {"foo": "bar"})
