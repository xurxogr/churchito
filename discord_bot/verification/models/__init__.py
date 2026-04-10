"""Verification cog models."""

from discord_bot.verification.models.api_response import (
    VerificationAPIResponse,
    VerificationAPIResult,
)
from discord_bot.verification.models.verification_request import VerificationRequest

__all__ = [
    "VerificationAPIResponse",
    "VerificationAPIResult",
    "VerificationRequest",
]
