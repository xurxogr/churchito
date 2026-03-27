"""Tests for discord_bot/purge/config.py."""

import discord

from discord_bot.purge.config import (
    BUTTON_STYLES,
    COG_NAME,
    DEFAULT_MOD_MESSAGE,
    DEFAULT_USER_MESSAGE,
    PURGE_CONFIG_SCHEMA,
)


class TestButtonStyles:
    """Tests for BUTTON_STYLES."""

    def test_blurple_style(self) -> None:
        """Test blurple style."""
        assert BUTTON_STYLES["blurple"] == discord.ButtonStyle.primary

    def test_grey_style(self) -> None:
        """Test grey style."""
        assert BUTTON_STYLES["grey"] == discord.ButtonStyle.secondary

    def test_green_style(self) -> None:
        """Test green style."""
        assert BUTTON_STYLES["green"] == discord.ButtonStyle.success

    def test_red_style(self) -> None:
        """Test red style."""
        assert BUTTON_STYLES["red"] == discord.ButtonStyle.danger


class TestCogName:
    """Tests for COG_NAME."""

    def test_cog_name_value(self) -> None:
        """Test that the cog name is correct."""
        assert COG_NAME == "purge"


class TestDefaultMessages:
    """Tests for default message templates."""

    def test_mod_message_has_placeholders(self) -> None:
        """Test that the moderation message has the necessary placeholders."""
        assert "{purge_type}" in DEFAULT_MOD_MESSAGE
        assert "{status}" in DEFAULT_MOD_MESSAGE
        assert "{required_reactions}" in DEFAULT_MOD_MESSAGE
        assert "{authorized_by}" in DEFAULT_MOD_MESSAGE
        assert "{cancellations}" in DEFAULT_MOD_MESSAGE
        assert "{date}" in DEFAULT_MOD_MESSAGE

    def test_user_message_has_placeholders(self) -> None:
        """Test that the user message has the necessary placeholders."""
        assert "{roles}" in DEFAULT_USER_MESSAGE
        assert "{date}" in DEFAULT_USER_MESSAGE
        assert "{reaction_role}" in DEFAULT_USER_MESSAGE


class TestPurgeConfigSchema:
    """Tests for PURGE_CONFIG_SCHEMA."""

    def test_schema_cog_name(self) -> None:
        """Test cog name in schema."""
        assert PURGE_CONFIG_SCHEMA.cog_name == "purge"

    def test_schema_display_name(self) -> None:
        """Test display name."""
        assert PURGE_CONFIG_SCHEMA.display_name == "Purge"

    def test_schema_is_toggleable(self) -> None:
        """Test that the cog is toggleable."""
        assert PURGE_CONFIG_SCHEMA.toggleable is True

    def test_schema_has_options(self) -> None:
        """Test that the schema has options."""
        assert len(PURGE_CONFIG_SCHEMA.options) > 0

    def test_schema_has_mod_channel_option(self) -> None:
        """Test that the moderation channel option exists."""
        keys = [opt.key for opt in PURGE_CONFIG_SCHEMA.options]
        assert "mod_channel" in keys

    def test_schema_has_user_channel_option(self) -> None:
        """Test that the user channel option exists."""
        keys = [opt.key for opt in PURGE_CONFIG_SCHEMA.options]
        assert "user_channel" in keys

    def test_schema_has_war_admin_roles_option(self) -> None:
        """Test that the admin roles option exists."""
        keys = [opt.key for opt in PURGE_CONFIG_SCHEMA.options]
        assert "war_admin_roles" in keys

    def test_schema_has_war_affected_roles_option(self) -> None:
        """Test that the affected roles option exists."""
        keys = [opt.key for opt in PURGE_CONFIG_SCHEMA.options]
        assert "war_affected_roles" in keys

    def test_schema_has_icon(self) -> None:
        """Test that the schema has an icon."""
        assert PURGE_CONFIG_SCHEMA.icon is not None
