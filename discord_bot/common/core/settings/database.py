"""Database configuration."""

from pydantic import BaseModel, ConfigDict, Field


class DatabaseSettings(BaseModel):
    """Configuration for the database."""

    url: str = Field(
        description="Database URL",
        default="sqlite+aiosqlite:///data/bot.db",
    )
    echo: bool = Field(description="Show SQL statements", default=False)
    pool_recycle: int = Field(description="Pool recycle time in seconds", default=3600)

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "url": "sqlite+aiosqlite:///data/bot.db",
                "echo": False,
                "pool_recycle": 3600,
            }
        },
    )
