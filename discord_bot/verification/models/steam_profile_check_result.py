"""Pydantic model for Steam profile privacy check results."""

from pydantic import BaseModel, ConfigDict, Field


class SteamProfileCheckResult(BaseModel):
    """Result of checking a Steam profile's privacy status.

    Attributes:
        success (bool): Whether the check completed successfully.
        is_private (bool | None): Whether the profile is private, if known.
        error_message (str | None): Error message if the check failed.
    """

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(description="Whether the check completed successfully")
    is_private: bool | None = Field(default=None, description="Whether the profile is private")
    error_message: str | None = Field(default=None, description="Error message if the check failed")
