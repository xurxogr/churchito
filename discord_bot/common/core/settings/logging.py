"""Logging configuration."""

from pydantic import BaseModel, ConfigDict, Field


class LoggingSettings(BaseModel):
    """Configuration for logging."""

    loggers: dict[str, str] = Field(description="Loggers and their levels", default_factory=dict)
    log_level: str = Field(description="Log level", default="INFO")
    log_format: str = Field(
        description="Log format",
        default="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
    )
    date_format: str = Field(description="Log date format", default="%Y-%m-%d %H:%M:%S")
    rotate_logs: bool = Field(description="Rotate logs daily", default=False)
    log_file: str | None = Field(description="Log file to write to", default=None)

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "loggers": {"discord_bot": "DEBUG", "discord": "INFO"},
                "log_level": "INFO",
                "log_format": "[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
                "date_format": "%Y-%m-%d %H:%M:%S",
                "rotate_logs": False,
                "log_file": None,
            }
        },
    )
