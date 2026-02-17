"""Estados posibles de una purga."""

from enum import StrEnum


class PurgaStatus(StrEnum):
    """Estados posibles de una purga."""

    PENDING = "pending"  # Esperando autorizaciones
    AUTHORIZED = "authorized"  # Autorizada, esperando ejecución
    EXPIRED = "expired"  # Expiró sin suficientes autorizaciones
    CANCEL_PENDING = "cancel_pending"  # Cancelación iniciada
    CANCELLED = "cancelled"  # Cancelada
    EXECUTED = "executed"  # Ejecutada exitosamente
    FAILED = "failed"  # Falló durante ejecución
