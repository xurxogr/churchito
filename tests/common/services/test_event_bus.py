"""Tests for event bus module."""

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest

from discord_bot.common.services.event_bus import EventBus, get_event_bus


@pytest.fixture
def event_bus() -> Generator[EventBus, None, None]:
    """Create a fresh event bus for testing.

    Returns:
        EventBus: New event bus instance
    """
    bus = EventBus()
    yield bus
    bus.clear()


def test_subscribe_and_emit(event_bus: EventBus) -> None:
    """Test subscribing to and emitting events.

    Args:
        event_bus: Event bus fixture
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
        event_bus: Event bus fixture
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
    """Test unsubscribing from events.

    Args:
        event_bus: Event bus fixture
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
    """Test that handler exceptions don't break event emission.

    Args:
        event_bus: Event bus fixture
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
    """Test that get_event_bus returns a singleton."""
    bus1 = get_event_bus()
    bus2 = get_event_bus()

    assert bus1 is bus2


def test_clear(event_bus: EventBus) -> None:
    """Test clearing all subscriptions.

    Args:
        event_bus: Event bus fixture
    """
    received_data: list[dict[str, Any]] = []

    def handler(data: dict[str, Any]) -> None:
        received_data.append(data)

    event_bus.subscribe("test.event", handler)
    event_bus.clear()
    event_bus.emit("test.event", {"foo": "bar"})

    assert len(received_data) == 0


def test_unsubscribe_nonexistent_handler(event_bus: EventBus) -> None:
    """Test unsubscribing a handler that was never subscribed (line 45).

    Args:
        event_bus: Event bus fixture
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
        assert "no encontrado" in warning_call
        assert "test.event" in warning_call


def test_unsubscribe_handler_twice(event_bus: EventBus) -> None:
    """Test unsubscribing the same handler twice triggers warning.

    Args:
        event_bus: Event bus fixture
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
        assert "no encontrado" in warning_call
