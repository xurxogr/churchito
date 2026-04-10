"""User context for permission verification."""

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """User context for permission verification.

    This model represents a user's identity and permissions without
    Discord-specific dependencies. Both Discord cogs and web routers
    can create this context from their respective sources.
    """

    user_id: int = Field(description="Unique user ID")
    guild_id: int = Field(description="Guild/server ID")
    role_ids: list[int] = Field(default_factory=lambda: [], description="User's role IDs")
    username: str | None = Field(default=None, description="User's display name")
