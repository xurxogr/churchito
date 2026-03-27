"""Tests for stockpile configuration schema."""

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.stockpile.config import COG_NAME, STOCKPILE_CONFIG_SCHEMA
from discord_bot.stockpile.enums import ConfigKey


class TestStockpileConfigSchema:
    """Tests for STOCKPILE_CONFIG_SCHEMA."""

    def test_cog_name(self) -> None:
        """Test cog name is correct."""
        assert COG_NAME == "stockpile"
        assert STOCKPILE_CONFIG_SCHEMA.cog_name == "stockpile"

    def test_display_name(self) -> None:
        """Test display name is set."""
        assert STOCKPILE_CONFIG_SCHEMA.display_name == "Stockpile"

    def test_has_description(self) -> None:
        """Test schema has description."""
        assert STOCKPILE_CONFIG_SCHEMA.description is not None
        assert len(STOCKPILE_CONFIG_SCHEMA.description) > 0

    def test_has_icon(self) -> None:
        """Test schema has icon."""
        assert STOCKPILE_CONFIG_SCHEMA.icon is not None

    def test_command_name_options(self) -> None:
        """Test command name options exist."""
        options = {opt.key: opt for opt in STOCKPILE_CONFIG_SCHEMA.options}

        assert ConfigKey.ADD_COMMAND_NAME in options
        assert ConfigKey.SHOW_COMMAND_NAME in options
        assert ConfigKey.DELETE_COMMAND_NAME in options

        # Check they are STRING type
        assert options[ConfigKey.ADD_COMMAND_NAME].option_type == ConfigOptionType.STRING
        assert options[ConfigKey.SHOW_COMMAND_NAME].option_type == ConfigOptionType.STRING
        assert options[ConfigKey.DELETE_COMMAND_NAME].option_type == ConfigOptionType.STRING

        # Check defaults
        assert options[ConfigKey.ADD_COMMAND_NAME].default == "stockpile_add"
        assert options[ConfigKey.SHOW_COMMAND_NAME].default == "stockpile_show"
        assert options[ConfigKey.DELETE_COMMAND_NAME].default == "stockpile_delete"

    def test_permission_options(self) -> None:
        """Test permission options exist."""
        options = {opt.key: opt for opt in STOCKPILE_CONFIG_SCHEMA.options}

        assert ConfigKey.ADD_ROLES in options
        assert ConfigKey.DELETE_ROLES in options
        assert ConfigKey.ALLOWED_VIEW_ROLES in options

        # Check they are ROLE_LIST type
        assert options[ConfigKey.ADD_ROLES].option_type == ConfigOptionType.ROLE_LIST
        assert options[ConfigKey.DELETE_ROLES].option_type == ConfigOptionType.ROLE_LIST
        assert options[ConfigKey.ALLOWED_VIEW_ROLES].option_type == ConfigOptionType.ROLE_LIST

        # Check defaults are empty lists
        assert options[ConfigKey.ADD_ROLES].default == []
        assert options[ConfigKey.DELETE_ROLES].default == []
        assert options[ConfigKey.ALLOWED_VIEW_ROLES].default == []

    def test_message_options(self) -> None:
        """Test message options exist."""
        options = {opt.key: opt for opt in STOCKPILE_CONFIG_SCHEMA.options}

        message_keys = [
            ConfigKey.ADD_SUCCESS_TEXT,
            ConfigKey.SHOW_HEADER_TEXT,
            ConfigKey.SHOW_ITEM_TEXT,
            ConfigKey.SHOW_EMPTY_TEXT,
            ConfigKey.DELETE_SUCCESS_TEXT,
            ConfigKey.NO_PERMISSION_TEXT,
            ConfigKey.NOT_FOUND_TEXT,
            ConfigKey.INVALID_CODE_TEXT,
            ConfigKey.INVALID_ROLES_TEXT,
        ]

        for key in message_keys:
            assert key in options, f"Missing option: {key}"
            assert options[key].default is not None, f"No default for: {key}"

    def test_add_success_text_placeholders(self) -> None:
        """Test add success text has correct placeholders."""
        options = {opt.key: opt for opt in STOCKPILE_CONFIG_SCHEMA.options}

        opt = options[ConfigKey.ADD_SUCCESS_TEXT]
        assert opt.placeholders is not None
        assert "name" in opt.placeholders
        assert "hex" in opt.placeholders
        assert "city" in opt.placeholders
        assert "code" in opt.placeholders

    def test_show_item_text_placeholders(self) -> None:
        """Test show item text has correct placeholders."""
        options = {opt.key: opt for opt in STOCKPILE_CONFIG_SCHEMA.options}

        opt = options[ConfigKey.SHOW_ITEM_TEXT]
        assert opt.placeholders is not None
        assert "name" in opt.placeholders
        assert "code" in opt.placeholders
        assert "creator" in opt.placeholders

    def test_all_options_have_group(self) -> None:
        """Test all options have a group assigned."""
        for opt in STOCKPILE_CONFIG_SCHEMA.options:
            assert opt.group is not None, f"Option {opt.key} has no group"
            assert len(opt.group) > 0, f"Option {opt.key} has empty group"

    def test_groups_are_valid(self) -> None:
        """Test all groups are from expected set."""
        expected_groups = {"Commands", "Permissions", "Messages", "Notifications"}
        actual_groups = {opt.group for opt in STOCKPILE_CONFIG_SCHEMA.options}

        assert actual_groups == expected_groups


class TestConfigKey:
    """Tests for ConfigKey enum."""

    def test_all_keys_are_strings(self) -> None:
        """Test all config keys are strings."""
        # Get all attributes that don't start with underscore
        keys = [getattr(ConfigKey, attr) for attr in dir(ConfigKey) if not attr.startswith("_")]

        for key in keys:
            assert isinstance(key, str), f"Key {key} is not a string"

    def test_key_values_are_snake_case(self) -> None:
        """Test all key values are snake_case."""
        keys = [getattr(ConfigKey, attr) for attr in dir(ConfigKey) if not attr.startswith("_")]

        for key in keys:
            assert key == key.lower(), f"Key {key} is not lowercase"
            assert " " not in key, f"Key {key} contains spaces"
