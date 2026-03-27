"""Verification statuses."""

from enum import StrEnum


class VerificationStatus(StrEnum):
    """Possible statuses for a verification request."""

    PENDING_SCREENSHOTS = "pending_screenshots"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
