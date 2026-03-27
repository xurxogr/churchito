"""Cog configuration schema."""

import copy

from pydantic import BaseModel, Field

from discord_bot.common.schemas.config_option import ConfigOption


class CogConfigSchema(BaseModel):
    """Complete configuration schema for a cog.

    This model represents the configuration schema of a cog,
    including cog metadata and the list of configurable options.
    """

    cog_name: str = Field(description="Unique identifier for the cog")
    display_name: str = Field(description="Human-readable name to display in the UI")
    description: str = Field(default="", description="Description of the cog")
    icon: str = Field(default="", description="Emoji or icon to display in the UI")
    toggleable: bool = Field(default=True, description="Whether the cog can be enabled/disabled")
    options: list[ConfigOption] = Field(
        default_factory=list, description="List of configurable options"
    )

    def get_option(self, key: str) -> ConfigOption | None:
        """Get a configuration option by its key.

        Args:
            key (str): Key of the option to find

        Returns:
            ConfigOption | None: The option if it exists, None otherwise
        """
        for option in self.options:
            if option.key == key:
                return option
        return None

    def get_default_values(self) -> dict[str, object]:
        """Get a dictionary with default values for all options.

        Returns:
            dict[str, object]: Dictionary with key -> default_value
        """
        return {option.key: copy.deepcopy(option.default) for option in self.options}
