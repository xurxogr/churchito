"""Bot configuration."""

from pydantic import BaseModel, ConfigDict, Field


class BotSettings(BaseModel):
    """Configuration for Discord bot."""

    token: str = Field(description="Discord bot token", default="")
    command_prefix: str = Field(description="Command prefix", default="!")
    owner_id: int | None = Field(description="Bot owner user ID", default=None)
    description: str = Field(
        description="Bot description",
        default="A Discord bot with cog-based architecture",
    )
    event_loop_warning_threshold: float = Field(
        description="Warning threshold for event loop delays (in seconds)",
        default=0.5,
        gt=0,
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "token": "YOUR_BOT_TOKEN",
                "command_prefix": "!",
                "owner_id": None,
                "description": "A Discord bot with cog-based architecture",
                "event_loop_warning_threshold": 0.5,
            }
        },
    )
