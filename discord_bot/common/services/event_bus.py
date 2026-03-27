"""Event bus implementation for pub/sub pattern."""

import logging
from collections import defaultdict
from collections.abc import Callable
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


EventHandler = Callable[[dict[str, Any]], None]


class EventBus:
    """Simple event bus for publishing and subscribing to events."""

    def __init__(self) -> None:
        """Initialize the event bus."""
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe a handler to an event type.

        Args:
            event_type (str): The event type to subscribe to
            handler (EventHandler): Callable that will be invoked when the event is emitted
        """
        self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed handler {handler.__name__} to event '{event_type}'")

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type.

        Args:
            event_type (str): The event type to unsubscribe from
            handler (EventHandler): The handler to remove
        """
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
                logger.debug(f"Unsubscribed handler {handler.__name__} from event '{{event_type}}'")
            except ValueError:
                logger.warning(f"Handler {handler.__name__} not found for event '{event_type}'")

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit an event to all subscribed handlers.

        Args:
            event_type (str): The event type being emitted
            data (dict[str, Any]): Event data to pass to handlers
        """
        handlers = self._subscribers.get(event_type, [])
        logger.debug(f"Emitting event '{event_type}' to {len(handlers)} handler(s)")

        for handler in handlers:
            try:
                handler(data)
            except Exception:
                # Don't let handler failures interrupt event emission
                logger.error(
                    f"Error in event handler {handler.__name__} for event '{{event_type}}': {{e}}",
                    exc_info=True,
                )

    def clear(self) -> None:
        """Clear all subscriptions."""
        self._subscribers.clear()
        logger.debug("Cleared all event subscriptions")


@lru_cache
def get_event_bus() -> EventBus:
    """Get the global event bus instance.

    Returns:
        EventBus: The global event bus singleton
    """
    return EventBus()
