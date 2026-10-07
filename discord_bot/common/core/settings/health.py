"""Periodic self-check of the bot process.

The check is global to the process (loaded cogs, command tree, what Discord
has published per guild), so its cadence is decided by the operator in the
config file, never per guild from the dashboard.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Below this the check would poll Discord for every guild too often.
MIN_INTERVAL_MINUTES = 5


class HealthSettings(BaseModel):
    """Configuration for the periodic health check."""

    interval_minutes: int = Field(
        description=(
            "Minutes between health checks of cogs and guild commands. "
            f"0 disables the check; otherwise at least {MIN_INTERVAL_MINUTES}."
        ),
        default=0,
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"interval_minutes": 60}},
    )

    @field_validator("interval_minutes")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        """Accept 0 (disabled) or an interval of at least the minimum.

        Args:
            v (int): Configured minutes.

        Returns:
            int: The validated value.

        Raises:
            ValueError: If the value is negative or shorter than the minimum.
        """
        if v == 0:
            return v
        if v < MIN_INTERVAL_MINUTES:
            raise ValueError(
                f"interval_minutes must be 0 (disabled) or at least {MIN_INTERVAL_MINUTES}"
            )
        return v

    @property
    def enabled(self) -> bool:
        """Whether the periodic check runs.

        Returns:
            bool: True when an interval is configured.
        """
        return self.interval_minutes > 0

    @property
    def interval_seconds(self) -> float:
        """Configured interval in seconds, for the sleeping loop.

        Returns:
            float: Interval in seconds.
        """
        return float(self.interval_minutes * 60)
