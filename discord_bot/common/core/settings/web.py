"""Web dashboard configuration."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Minimum valid Discord snowflake (approximately January 2015)
# Discord snowflakes encode timestamp from their epoch (1420070400000)
MIN_DISCORD_SNOWFLAKE = 10_000_000_000_000_000  # ~17 digits minimum


class WebSettings(BaseModel):
    """Configuration for web dashboard with Discord OAuth."""

    enabled: bool = Field(
        description="Enable the web dashboard",
        default=False,
    )
    host: str = Field(
        description="Host for the web server",
        default="0.0.0.0",  # noqa: S104 - Intentional for server binding
    )
    port: int = Field(
        description="Port for the web server",
        default=8000,
    )
    root_path: str = Field(
        description="Base path when served behind a proxy (e.g., /bot)",
        default="",
    )
    secret_key: str = Field(
        description="Secret key for sessions (auto-generated if empty)",
        default="",
    )
    client_id: str = Field(
        description="Discord OAuth application client ID",
        default="",
    )
    client_secret: str = Field(
        description="Discord OAuth application client secret",
        default="",
    )
    redirect_uri: str = Field(
        description="OAuth redirect URI (e.g., http://localhost:8000/auth/callback)",
        default="http://localhost:8000/auth/callback",
    )
    owner_ids: list[int] = Field(
        description="User IDs with admin access to the dashboard",
        default_factory=list,
    )
    https_only: bool = Field(
        description="Only send session cookie over HTTPS (use True in production)",
        default=True,
    )
    session_max_age: int = Field(
        description="Maximum session duration in seconds (default: 2 hours)",
        default=7200,
    )
    trusted_hosts: list[str] = Field(
        description=(
            "Trusted hosts for proxy headers (X-Forwarded-For, X-Forwarded-Proto). "
            "Use ['*'] if there's a reverse proxy in front that sanitizes these headers. "
            "Defaults to ['127.0.0.1'] if not configured."
        ),
        default_factory=list,
    )
    rate_limit_enabled: bool = Field(
        description=(
            "Enable internal rate limiting. NOTE: The rate limiter uses local memory, "
            "so it does NOT scale in multi-worker deployments. In production with multiple "
            "workers, disable this and use external rate limiting (nginx, Cloudflare, etc.)."
        ),
        default=True,
    )

    @field_validator("owner_ids")
    @classmethod
    def validate_owner_ids(cls, v: list[int]) -> list[int]:
        """Validate that owner_ids are valid Discord snowflakes.

        Args:
            v (list[int]): List of IDs

        Returns:
            list[int]: Validated list

        Raises:
            ValueError: If any ID is not a valid snowflake
        """
        for user_id in v:
            if user_id < MIN_DISCORD_SNOWFLAKE:
                raise ValueError(
                    f"owner_id {user_id} is not a valid Discord snowflake "
                    f"(must be >= {MIN_DISCORD_SNOWFLAKE})"
                )
        return v

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "enabled": True,
                "host": "0.0.0.0",  # noqa: S104
                "port": 8000,
                "root_path": "/bot",
                "secret_key": "your-secret-key-here",
                "client_id": "your-discord-client-id",
                "client_secret": "your-discord-client-secret",
                "redirect_uri": "http://localhost:8000/auth/callback",
                "owner_ids": [123456789012345678],
                "https_only": True,
                "session_max_age": 7200,
                "trusted_hosts": ["*"],
                "rate_limit_enabled": False,
            }
        },
    )
