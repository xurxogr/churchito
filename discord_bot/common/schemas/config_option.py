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
        description=(
            "Column definition for TABLE (key, name, type, required, etc.); role columns "
            "accept ``manageable_only`` with the same meaning as the option-level flag"
        ),
    )
    manageable_only: bool = Field(
        default=False,
        description=(
            "For ROLE/ROLE_LIST: offer only roles the bot can assign or remove (below its "
            "top role). Leave False for roles the bot merely checks membership of"
        ),
    )
    custom_validator: Any = Field(
        default=None,
        exclude=True,
        description=(
            "Optional callable (value) -> str | None for semantic validation "
            "beyond type checks; returns an error message or None"
        ),
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
                    # Validate required columns and string constraints
                    if self.columns:
                        for col in self.columns:
                            if col.get("required") and not row.get(col["key"]):
                                return (
                                    False,
                                    f"'{self.name}' row {i + 1}: '{col['name']}' is required",
                                )
                            cell_error = self._validate_table_cell(
                                row=row, col=col, row_number=i + 1
                            )
                            if cell_error:
                                return False, cell_error

        if self.custom_validator is not None and value is not None:
            error = self.custom_validator(value)
            if error:
                return False, error

        return True, None

    def _validate_table_cell(
        self, row: dict[str, Any], col: dict[str, Any], row_number: int
    ) -> str | None:
        """Validate one table cell against its column definition.

        Only string-like columns are checked: the declared ``max_length`` was
        previously never enforced server-side, so oversized values reached the
        stored configuration. Role/channel columns are deliberately not
        type-checked here because legacy rows hold string IDs that the web
        router still normalizes on save.

        Args:
            row (dict[str, Any]): Table row being validated.
            col (dict[str, Any]): Column definition.
            row_number (int): 1-indexed row number for error messages.

        Returns:
            str | None: Error message, or None when the cell is valid.
        """
        if col.get("type") not in ("string", "textarea"):
            return None
        cell = row.get(col["key"])
        if cell is None:
            return None
        if not isinstance(cell, str):
            return f"'{self.name}' row {row_number}: '{col['name']}' must be text"
        max_length = col.get("max_length")
        if max_length and len(cell) > max_length:
            return (
                f"'{self.name}' row {row_number}: '{col['name']}' cannot exceed "
                f"{max_length} characters"
            )
        return None
