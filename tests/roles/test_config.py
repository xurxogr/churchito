"""Tests for roles configuration schema."""

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.roles.config import COG_NAME, ROLES_CONFIG_SCHEMA
from discord_bot.roles.enums import ConfigKey


class TestRolesConfigSchema:
    """Tests for ROLES_CONFIG_SCHEMA."""

    def test_cog_name(self) -> None:
        """Test cog name is correct."""
        assert COG_NAME == "roles"
        assert ROLES_CONFIG_SCHEMA.cog_name == "roles"

    def test_display_name(self) -> None:
        """Test display name is set."""
        assert ROLES_CONFIG_SCHEMA.display_name == "Reaction Roles"

    def test_has_description(self) -> None:
        """Test schema has description."""
        assert ROLES_CONFIG_SCHEMA.description is not None
        assert len(ROLES_CONFIG_SCHEMA.description) > 0

    def test_has_icon(self) -> None:
        """Test schema has icon."""
        assert ROLES_CONFIG_SCHEMA.icon is not None
        assert ROLES_CONFIG_SCHEMA.icon == "🎭"

    def test_command_prefix_option(self) -> None:
        """Test command prefix option exists."""
        options = {opt.key: opt for opt in ROLES_CONFIG_SCHEMA.options}

        assert ConfigKey.COMMAND_PREFIX in options
        assert options[ConfigKey.COMMAND_PREFIX].option_type == ConfigOptionType.STRING
        assert options[ConfigKey.COMMAND_PREFIX].default == "roles"
        assert options[ConfigKey.COMMAND_PREFIX].max_length == 32

    def test_permission_option(self) -> None:
        """Test manage roles permission option exists."""
        options = {opt.key: opt for opt in ROLES_CONFIG_SCHEMA.options}

        assert ConfigKey.MANAGE_ROLES in options
        assert options[ConfigKey.MANAGE_ROLES].option_type == ConfigOptionType.ROLE_LIST
        assert options[ConfigKey.MANAGE_ROLES].default == []

    def test_audit_channel_option(self) -> None:
        """Test audit channel option exists."""
        options = {opt.key: opt for opt in ROLES_CONFIG_SCHEMA.options}

        assert ConfigKey.AUDIT_CHANNEL in options
        assert options[ConfigKey.AUDIT_CHANNEL].option_type == ConfigOptionType.CHANNEL
        assert options[ConfigKey.AUDIT_CHANNEL].default is None

    def test_audit_notification_switches(self) -> None:
        """Test audit notification toggle options exist."""
        options = {opt.key: opt for opt in ROLES_CONFIG_SCHEMA.options}

        switch_keys = [
            ConfigKey.AUDIT_PANEL_CREATED,
            ConfigKey.AUDIT_PANEL_EDITED,
            ConfigKey.AUDIT_PANEL_DELETED,
            ConfigKey.AUDIT_USER_ROLE_ADD,
            ConfigKey.AUDIT_USER_ROLE_REMOVE,
        ]

        for key in switch_keys:
            assert key in options, f"Missing option: {key}"
            assert options[key].option_type == ConfigOptionType.BOOLEAN

        # Check defaults
        assert options[ConfigKey.AUDIT_PANEL_CREATED].default is True
        assert options[ConfigKey.AUDIT_PANEL_EDITED].default is True
        assert options[ConfigKey.AUDIT_PANEL_DELETED].default is True
        assert options[ConfigKey.AUDIT_USER_ROLE_ADD].default is False
        assert options[ConfigKey.AUDIT_USER_ROLE_REMOVE].default is False

    def test_audit_message_options(self) -> None:
        """Test audit message template options exist."""
        options = {opt.key: opt for opt in ROLES_CONFIG_SCHEMA.options}

        message_keys = [
            ConfigKey.AUDIT_PANEL_CREATED_MSG,
            ConfigKey.AUDIT_PANEL_EDITED_MSG,
            ConfigKey.AUDIT_PANEL_DELETED_MSG,
            ConfigKey.AUDIT_USER_ROLE_ADD_MSG,
            ConfigKey.AUDIT_USER_ROLE_REMOVE_MSG,
        ]

        for key in message_keys:
            assert key in options, f"Missing option: {key}"
            assert options[key].option_type == ConfigOptionType.TEXTAREA
            assert options[key].max_length == 500
            assert options[key].default is not None

    def test_audit_panel_created_msg_placeholders(self) -> None:
        """Test audit panel created message has correct placeholders."""
        options = {opt.key: opt for opt in ROLES_CONFIG_SCHEMA.options}

        opt = options[ConfigKey.AUDIT_PANEL_CREATED_MSG]
        assert opt.placeholders is not None
        assert "panel_name" in opt.placeholders
        assert "panel_type" in opt.placeholders
        assert "channel_mention" in opt.placeholders
        assert "user_mention" in opt.placeholders
        assert "created_at" in opt.placeholders

    def test_audit_user_role_add_msg_placeholders(self) -> None:
        """Test audit user role add message has correct placeholders."""
        options = {opt.key: opt for opt in ROLES_CONFIG_SCHEMA.options}

        opt = options[ConfigKey.AUDIT_USER_ROLE_ADD_MSG]
        assert opt.placeholders is not None
        assert "user_mention" in opt.placeholders
        assert "role_mention" in opt.placeholders
        assert "role_name" in opt.placeholders
        assert "panel_name" in opt.placeholders

    def test_dm_message_options(self) -> None:
        """Test DM message options exist."""
        options = {opt.key: opt for opt in ROLES_CONFIG_SCHEMA.options}

        dm_keys = [
            ConfigKey.DM_MISSING_ROLE_MSG,
            ConfigKey.DM_ROLE_ADDED_MSG,
            ConfigKey.DM_ROLE_REMOVED_MSG,
        ]

        for key in dm_keys:
            assert key in options, f"Missing option: {key}"
            assert options[key].option_type == ConfigOptionType.TEXTAREA
            assert options[key].max_length == 1000

        # DM messages default to None (disabled)
        assert options[ConfigKey.DM_MISSING_ROLE_MSG].default is None
        assert options[ConfigKey.DM_ROLE_ADDED_MSG].default is None
        assert options[ConfigKey.DM_ROLE_REMOVED_MSG].default is None

    def test_dm_missing_role_msg_placeholders(self) -> None:
        """Test DM missing role message has correct placeholders."""
        options = {opt.key: opt for opt in ROLES_CONFIG_SCHEMA.options}

        opt = options[ConfigKey.DM_MISSING_ROLE_MSG]
        assert opt.placeholders is not None
        assert "user_name" in opt.placeholders
        assert "panel_name" in opt.placeholders
        assert "required_roles" in opt.placeholders
        assert "guild_name" in opt.placeholders

    def test_dm_role_added_msg_placeholders(self) -> None:
        """Test DM role added message has correct placeholders."""
        options = {opt.key: opt for opt in ROLES_CONFIG_SCHEMA.options}

        opt = options[ConfigKey.DM_ROLE_ADDED_MSG]
        assert opt.placeholders is not None
        assert "user_name" in opt.placeholders
        assert "role_name" in opt.placeholders
        assert "role_mention" in opt.placeholders
        assert "panel_name" in opt.placeholders
        assert "guild_name" in opt.placeholders

    def test_error_message_options(self) -> None:
        """Test error message options exist."""
        options = {opt.key: opt for opt in ROLES_CONFIG_SCHEMA.options}

        error_keys = [
            ConfigKey.NO_PERMISSION_TEXT,
            ConfigKey.NOT_FOUND_TEXT,
            ConfigKey.MISSING_REQUIRED_ROLE_TEXT,
        ]

        for key in error_keys:
            assert key in options, f"Missing option: {key}"
            assert options[key].option_type == ConfigOptionType.STRING
            assert options[key].max_length == 200
            assert options[key].default is not None

    def test_all_options_have_group(self) -> None:
        """Test all options have a group assigned."""
        for opt in ROLES_CONFIG_SCHEMA.options:
            assert opt.group is not None, f"Option {opt.key} has no group"
            assert len(opt.group) > 0, f"Option {opt.key} has empty group"

    def test_groups_are_valid(self) -> None:
        """Test all groups are from expected set."""
        expected_groups = {
            "General",
            "Permissions",
            "Audit",
            "Audit Messages",
            "User DM Messages",
            "Error Messages",
        }
        actual_groups = {opt.group for opt in ROLES_CONFIG_SCHEMA.options}

        assert actual_groups == expected_groups


class TestConfigKey:
    """Tests for ConfigKey class."""

    def test_all_keys_are_strings(self) -> None:
        """Test all config keys are strings."""
        # Get all class attributes that don't start with underscore
        keys = [
            getattr(ConfigKey, attr)
            for attr in dir(ConfigKey)
            if not attr.startswith("_") and attr.isupper()
        ]

        for key in keys:
            assert isinstance(key, str), f"Key {key} is not a string"

    def test_key_values_are_snake_case(self) -> None:
        """Test all key values are snake_case."""
        keys = [
            getattr(ConfigKey, attr)
            for attr in dir(ConfigKey)
            if not attr.startswith("_") and attr.isupper()
        ]

        for key in keys:
            assert key == key.lower(), f"Key {key} is not lowercase"
            assert " " not in key, f"Key {key} contains spaces"

    def test_command_prefix_key(self) -> None:
        """Test command prefix key."""
        assert ConfigKey.COMMAND_PREFIX == "command_prefix"

    def test_manage_roles_key(self) -> None:
        """Test manage roles key."""
        assert ConfigKey.MANAGE_ROLES == "manage_roles"

    def test_audit_channel_key(self) -> None:
        """Test audit channel key."""
        assert ConfigKey.AUDIT_CHANNEL == "audit_channel"

    def test_dm_message_keys(self) -> None:
        """Test DM message keys."""
        assert ConfigKey.DM_MISSING_ROLE_MSG == "dm_missing_role_msg"
        assert ConfigKey.DM_ROLE_ADDED_MSG == "dm_role_added_msg"
        assert ConfigKey.DM_ROLE_REMOVED_MSG == "dm_role_removed_msg"

    def test_error_message_keys(self) -> None:
        """Test error message keys."""
        assert ConfigKey.NO_PERMISSION_TEXT == "no_permission_text"
        assert ConfigKey.NOT_FOUND_TEXT == "not_found_text"
        assert ConfigKey.MISSING_REQUIRED_ROLE_TEXT == "missing_required_role_text"
