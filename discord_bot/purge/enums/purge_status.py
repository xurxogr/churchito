"""Possible purge statuses."""

from enum import StrEnum


class PurgeStatus(StrEnum):
    """Possible purge statuses."""

    PENDING = "pending"  # Waiting for authorizations
    AUTHORIZED = "authorized"  # Authorized, waiting for execution
    EXPIRED = "expired"  # Expired without enough authorizations
    CANCEL_PENDING = "cancel_pending"  # Cancellation initiated
    CANCELLED = "cancelled"  # Cancelled
    EXECUTED = "executed"  # Executed successfully
    FAILED = "failed"  # Failed during execution
