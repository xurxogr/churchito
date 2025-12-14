"""Tests para el bus de eventos."""

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest

from discord_bot.common.services.event_bus import EventBus, get_event_bus


@pytest.fixture
def event_bus() -> Generator[EventBus, None, None]:
    """Crear un bus de eventos.

    Returns:
        EventBus: Nueva instancia del bus de eventos
    """
    bus = EventBus()
    yield bus
    bus.clear()


def test_subscribe_and_emit(event_bus: EventBus) -> None:
    """Probar a suscribirse y emitir un evento.

    Args:
        event_bus (EventBus): Instancia del bus de eventos
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
    """Probar múltiples suscriptores para el mismo evento.

    Args:
        event_bus (EventBus): Instancia del bus de eventos
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
    """Probar la desuscripción de un manejador.

    Args:
        event_bus (EventBus): Instancia del bus de eventos
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
    """Probar que una excepción en un manejador no rompe la emisión.

    Args:
        event_bus (EventBus): Instancia del bus de eventos
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
    """Probar que get_event_bus devuelve la misma instancia."""
    bus1 = get_event_bus()
    bus2 = get_event_bus()

    assert bus1 is bus2


def test_clear(event_bus: EventBus) -> None:
    """Probar que clear elimina todos los suscriptores.

    Args:
        event_bus (EventBus): Instancia del bus de eventos
    """
    received_data: list[dict[str, Any]] = []

    def handler(data: dict[str, Any]) -> None:
        received_data.append(data)

    event_bus.subscribe("test.event", handler)
    event_bus.clear()
    event_bus.emit("test.event", {"foo": "bar"})

    assert len(received_data) == 0


def test_unsubscribe_nonexistent_handler(event_bus: EventBus) -> None:
    """Probar desuscribir un manejador que no está suscrito.

    Args:
        event_bus (EventBus): Instancia del bus de eventos
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
    """Probar desuscribir un manejador dos veces.

    Args:
        event_bus (EventBus): Instancia del bus de eventos
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
