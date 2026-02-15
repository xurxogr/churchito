"""Estados de verificacion."""

from enum import StrEnum


class VerificationStatus(StrEnum):
    """Estados posibles de una solicitud de verificacion."""

    PENDING_SCREENSHOTS = "pending_screenshots"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
