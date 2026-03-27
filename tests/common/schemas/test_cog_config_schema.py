"""Tests for CogConfigSchema."""

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption


class TestCogConfigSchema:
    """Tests for CogConfigSchema."""

    def test_get_option_found(self) -> None:
        """Test getting an existing option."""
        schema = CogConfigSchema(
            cog_name="test",
            display_name="Test Cog",
            options=[
                ConfigOption(
                    key="option1",
                    name="Option 1",
                    option_type=ConfigOptionType.STRING,
                ),
                ConfigOption(
                    key="option2",
                    name="Option 2",
                    option_type=ConfigOptionType.INTEGER,
                ),
            ],
        )
        option = schema.get_option("option1")
        assert option is not None
        assert option.key == "option1"
        assert option.name == "Option 1"

    def test_get_option_not_found(self) -> None:
        """Test getting a non-existent option."""
        schema = CogConfigSchema(
            cog_name="test",
            display_name="Test Cog",
            options=[
                ConfigOption(
                    key="option1",
                    name="Option 1",
                    option_type=ConfigOptionType.STRING,
                ),
            ],
        )
        option = schema.get_option("nonexistent")
        assert option is None

    def test_get_default_values(self) -> None:
        """Test getting default values."""
        schema = CogConfigSchema(
            cog_name="test",
            display_name="Test Cog",
            options=[
                ConfigOption(
                    key="string_opt",
                    name="String Option",
                    option_type=ConfigOptionType.STRING,
                    default="hello",
                ),
                ConfigOption(
                    key="int_opt",
                    name="Integer Option",
                    option_type=ConfigOptionType.INTEGER,
                    default=42,
                ),
                ConfigOption(
                    key="bool_opt",
                    name="Boolean Option",
                    option_type=ConfigOptionType.BOOLEAN,
                    default=True,
                ),
                ConfigOption(
                    key="no_default",
                    name="No Default",
                    option_type=ConfigOptionType.STRING,
                ),
            ],
        )
        defaults = schema.get_default_values()
        assert defaults["string_opt"] == "hello"
        assert defaults["int_opt"] == 42
        assert defaults["bool_opt"] is True
        assert defaults["no_default"] is None

    def test_empty_options(self) -> None:
        """Test schema without options."""
        schema = CogConfigSchema(
            cog_name="empty",
            display_name="Empty Cog",
        )
        assert schema.options == []
        assert schema.get_default_values() == {}
        assert schema.get_option("anything") is None
