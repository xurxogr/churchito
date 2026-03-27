"""Tests for the event bus."""

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest

from discord_bot.common.services.event_bus import EventBus, get_event_bus


@pytest.fixture
def event_bus() -> Generator[EventBus, None, None]:
    """Create an event bus.

    Returns:
        EventBus: New event bus instance
    """
    bus = EventBus()
    yield bus
    bus.clear()


def test_subscribe_and_emit(event_bus: EventBus) -> None:
    """Test subscribing and emitting an event.

    Args:
        event_bus (EventBus): Event bus instance
    """
    received_data: list[dict[str, Any]] = []

    def handler(data: dict[str, Any]) -> None:
        received_data.append(data)

    # Subscribe
    event_bus.subscribe("test.event", handler)

    # Emit
    event_bus.emit("test.event", {"foo": "bar"})

    assert len(received_data) == 1
    assert received_data[0] == {"foo": "bar"}


def test_multiple_subscribers(event_bus: EventBus) -> None:
    """Test multiple subscribers for the same event.

    Args:
        event_bus (EventBus): Event bus instance
    """
    counter = {"count": 0}

    def handler1(data: dict[str, Any]) -> None:
        counter["count"] += 1

    def handler2(data: dict[str, Any]) -> None:
        counter["count"] += 10

    event_bus.subscribe("test.event", handler1)
    event_bus.subscribe("test.event", handler2)

    event_bus.emit("test.event", {})

    assert counter["count"] == 11


def test_unsubscribe(event_bus: EventBus) -> None:
    """Test unsubscribing a handler.

    Args:
        event_bus (EventBus): Event bus instance
    """
    received_data: list[dict[str, Any]] = []

    def handler(data: dict[str, Any]) -> None:
        received_data.append(data)

    event_bus.subscribe("test.event", handler)
    event_bus.emit("test.event", {"test": 1})

    event_bus.unsubscribe("test.event", handler)
    event_bus.emit("test.event", {"test": 2})

    assert len(received_data) == 1
    assert received_data[0] == {"test": 1}


def test_handler_exception_doesnt_break_emit(event_bus: EventBus) -> None:
    """Test that an exception in a handler doesn't break emission.

    Args:
        event_bus (EventBus): Event bus instance
    """
    received_data: list[dict[str, Any]] = []

    def failing_handler(data: dict[str, Any]) -> None:
        raise ValueError("Test error")

    def working_handler(data: dict[str, Any]) -> None:
        received_data.append(data)

    event_bus.subscribe("test.event", failing_handler)
    event_bus.subscribe("test.event", working_handler)

    event_bus.emit("test.event", {"foo": "bar"})

    # Working handler should still receive the event
    assert len(received_data) == 1
    assert received_data[0] == {"foo": "bar"}


def test_get_event_bus_singleton() -> None:
    """Test that get_event_bus returns the same instance."""
    bus1 = get_event_bus()
    bus2 = get_event_bus()

    assert bus1 is bus2


def test_clear(event_bus: EventBus) -> None:
    """Test that clear removes all subscribers.

    Args:
        event_bus (EventBus): Event bus instance
    """
    received_data: list[dict[str, Any]] = []

    def handler(data: dict[str, Any]) -> None:
        received_data.append(data)

    event_bus.subscribe("test.event", handler)
    event_bus.clear()
    event_bus.emit("test.event", {"foo": "bar"})

    assert len(received_data) == 0


def test_unsubscribe_nonexistent_handler(event_bus: EventBus) -> None:
    """Test unsubscribing a handler that is not subscribed.

    Args:
        event_bus (EventBus): Event bus instance
    """

    def handler1(data: dict[str, Any]) -> None:
        pass

    def handler2(data: dict[str, Any]) -> None:
        pass

    # Subscribe handler1 so the event type exists in _subscribers
    event_bus.subscribe("test.event", handler1)

    # Mock the logger to verify warning is logged
    with patch("discord_bot.common.services.event_bus.logger") as mock_logger:
        # Try to unsubscribe handler2 that was never subscribed
        event_bus.unsubscribe("test.event", handler2)

        # Verify a warning was logged (line 46-48)
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args[0][0]
        assert "not found" in warning_call
        assert "test.event" in warning_call


def test_unsubscribe_handler_twice(event_bus: EventBus) -> None:
    """Test unsubscribing a handler twice.

    Args:
        event_bus (EventBus): Event bus instance
    """

    def handler(data: dict[str, Any]) -> None:
        pass

    # Subscribe handler
    event_bus.subscribe("test.event", handler)

    # Unsubscribe once (should succeed)
    event_bus.unsubscribe("test.event", handler)

    # Mock the logger to verify warning on second unsubscribe
    with patch("discord_bot.common.services.event_bus.logger") as mock_logger:
        # Try to unsubscribe again (should trigger ValueError -> warning)
        event_bus.unsubscribe("test.event", handler)

        # Verify a warning was logged
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args[0][0]
        assert "not found" in warning_call
