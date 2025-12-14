"""Implementación de bus de eventos para el patrón pub/sub."""

import logging
from collections import defaultdict
from collections.abc import Callable
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


EventHandler = Callable[[dict[str, Any]], None]


class EventBus:
    """Bus de eventos simple para publicar y suscribirse a eventos."""

    def __init__(self) -> None:
        """Inicializar el bus de eventos."""
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Suscribirse a un manejador para un tipo de evento.

        Args:
            event_type (str): El tipo de evento al que suscribirse
            handler (EventHandler): Callable que será invocado cuando se emita el evento
        """
        self._subscribers[event_type].append(handler)
        logger.debug(f"Suscrito el manejador {handler.__name__} al evento '{event_type}'")

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Cancelar la suscripción de un manejador de un tipo de evento.

        Args:
            event_type (str): El tipo de evento del que cancelar la suscripción
            handler (EventHandler): El manejador a eliminar
        """
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
                logger.debug(
                    f"Cancelada la suscripción del manejador {handler.__name__} "
                    "del evento '{event_type}'"
                )
            except ValueError:
                logger.warning(
                    f"Manejador {handler.__name__} no encontrado para el evento '{event_type}'"
                )

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Emitir un evento a todos los manejadores suscritos.

        Args:
            event_type (str): El tipo de evento que se emite
            data (dict[str, Any]): Datos del evento a pasar a los manejadores
        """
        handlers = self._subscribers.get(event_type, [])
        logger.debug(f"Emitiendo evento '{event_type}' a {len(handlers)} manejador(es)")

        for handler in handlers:
            try:
                handler(data)
            except Exception:
                # No permitir que las fallas del manejador interrumpan la emisión del evento
                logger.error(
                    f"Error en el manejador de eventos {handler.__name__} "
                    "para el evento '{event_type}': {e}",
                    exc_info=True,
                )

    def clear(self) -> None:
        """Limpiar todas las suscripciones."""
        self._subscribers.clear()
        logger.debug("Se limpiaron todas las suscripciones de eventos")


@lru_cache
def get_event_bus() -> EventBus:
    """Obtener la instancia global del bus de eventos.

    Returns:
        EventBus: El singleton global del bus de eventos
    """
    return EventBus()
