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


@lru_cache
def get_event_bus() -> EventBus:
    """Get the global event bus instance.

    Returns:
        EventBus: The global event bus singleton
    """
    return EventBus()
