"""Verification configuration."""

from pydantic import BaseModel, ConfigDict, Field


class VerificationSettings(BaseModel):
    """Configuration for external verification service."""

    api_url: str = Field(
        description="Verification API endpoint URL (empty to disable)",
        default="",
    )
    api_key: str = Field(
        description="API key for authentication (sent as X-API-Key header)",
        default="",
    )
    api_timeout: int = Field(
        description="Timeout in seconds for API calls",
        default=30,
        gt=0,
        le=120,
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "api_url": "https://api.example.com/verify",
                "api_key": "your-api-key",
                "api_timeout": 30,
            }
        },
    )
