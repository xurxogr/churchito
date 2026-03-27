"""Configuration option schema for cogs."""

from typing import Any

from pydantic import BaseModel, Field

from discord_bot.common.enums.config_option_type import ConfigOptionType


class ConfigOption(BaseModel):
    """Definition of a configuration option for a cog.

    This model represents the metadata of a configuration option,
    including its type, default value, validations and constraints.
    """

    key: str = Field(description="Unique identifier for the option within the cog")
    name: str = Field(description="Human-readable name to display in the UI")
    description: str = Field(default="", description="Description of the option")
    option_type: ConfigOptionType = Field(description="Data type of the option")
    default: Any = Field(default=None, description="Default value if not configured")
    required: bool = Field(default=False, description="Whether the option is required")
    section: str | None = Field(
        default=None,
        description="Top-level section for organizing option groups (main title)",
    )
    group: str | None = Field(
        default=None,
        description="Group for organizing related options within a section",
    )
    choices: list[tuple[str, Any]] | None = Field(
        default=None,
        description="List of valid options (label, value) for TEXT_CHOICE",
    )
    min_value: int | None = Field(default=None, description="Minimum value for INTEGER")
    max_value: int | None = Field(default=None, description="Maximum value for INTEGER")
    max_length: int | None = Field(default=None, description="Maximum length for STRING")
    placeholders: list[str] | None = Field(
        default=None,
        description="List of available placeholders for TEXTAREA",
    )
    columns: list[dict[str, Any]] | None = Field(
        default=None,
        description="Column definition for TABLE (key, name, type, required, etc.)",
    )

    def validate_value(self, value: Any) -> tuple[bool, str | None]:
        """Validate a value against this option's constraints.

        Args:
            value (Any): Value to validate

        Returns:
            tuple[bool, str | None]: (is_valid, error_message)
        """
        if value is None:
            if self.required:
                return False, f"Option '{self.name}' is required"
            return True, None

        match self.option_type:
            case ConfigOptionType.STRING | ConfigOptionType.TEXTAREA:
                if not isinstance(value, str):
                    return False, f"'{self.name}' must be text"
                if self.max_length and len(value) > self.max_length:
                    return False, f"'{self.name}' cannot exceed {self.max_length} characters"

            case ConfigOptionType.INTEGER:
                if not isinstance(value, int):
                    return False, f"'{self.name}' must be an integer"
                if self.min_value is not None and value < self.min_value:
                    return False, f"'{self.name}' must be at least {self.min_value}"
                if self.max_value is not None and value > self.max_value:
                    return False, f"'{self.name}' cannot exceed {self.max_value}"

            case ConfigOptionType.BOOLEAN:
                if not isinstance(value, bool):
                    return False, f"'{self.name}' must be true or false"

            case ConfigOptionType.CHANNEL | ConfigOptionType.ROLE:
                if not isinstance(value, int):
                    return False, f"'{self.name}' must be a valid ID"

            case ConfigOptionType.CHANNEL_LIST | ConfigOptionType.ROLE_LIST:
                if not isinstance(value, list) or not all(isinstance(v, int) for v in value):
                    return False, f"'{self.name}' must be a list of IDs"

            case ConfigOptionType.TEXT_CHOICE:
                if self.choices:
                    valid_values = [choice[1] for choice in self.choices]
                    # Allow empty string for non-required fields (means "no selection")
                    if value == "" and not self.required:
                        pass
                    elif value not in valid_values:
                        return False, f"'{self.name}' must be one of the valid options"

            case ConfigOptionType.TABLE:
                if not isinstance(value, list):
                    return False, f"'{self.name}' must be a list"
                for i, row in enumerate(value):
                    if not isinstance(row, dict):
                        return False, f"'{self.name}' row {i + 1} must be an object"
                    # Validate required columns
                    if self.columns:
                        for col in self.columns:
                            if col.get("required") and not row.get(col["key"]):
                                return (
                                    False,
                                    f"'{self.name}' row {i + 1}: '{col['name']}' is required",
                                )

        return True, None
