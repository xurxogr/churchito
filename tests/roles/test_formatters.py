"""Tests for roles formatters."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import discord

from discord_bot.roles.formatters import (
    build_panel_embed,
    build_panel_placeholder_data,
    build_role_change_placeholder_data,
    format_emoji_display,
    format_mappings_display,
    format_message,
)
from discord_bot.roles.models import PanelType, ReactionPanel


class TestFormatMessage:
    """Tests for format_message function."""

    def test_simple_replacement(self) -> None:
        """Test simple placeholder replacement."""
        result = format_message("Hello {name}!", name="World")
        assert result == "Hello World!"

    def test_multiple_replacements(self) -> None:
        """Test multiple placeholder replacements."""
        result = format_message(
            "{greeting} {name}, welcome to {place}!",
            greeting="Hello",
            name="User",
            place="Discord",
        )
        assert result == "Hello User, welcome to Discord!"

    def test_none_template(self) -> None:
        """Test with None template."""
        result = format_message(None)
        assert result == ""

    def test_empty_template(self) -> None:
        """Test with empty template."""
        result = format_message("")
        assert result == ""

    def test_none_value(self) -> None:
        """Test with None value."""
        result = format_message("Value: {value}", value=None)
        assert result == "Value: "

    def test_unknown_placeholder_unchanged(self) -> None:
        """Test that unknown placeholders are left unchanged."""
        result = format_message("Hello {name} and {unknown}!", name="World")
        assert result == "Hello World and {unknown}!"

    def test_integer_value(self) -> None:
        """Test with integer value."""
        result = format_message("Count: {count}", count=42)
        assert result == "Count: 42"

    def test_newline_conversion(self) -> None:
        r"""Test that literal \n is converted to newlines."""
        result = format_message("Line 1\\nLine 2")
        assert result == "Line 1\nLine 2"

    def test_newline_with_placeholders(self) -> None:
        """Test newline conversion combined with placeholders."""
        result = format_message("{greeting}\\n{name}", greeting="Hello", name="World")
        assert result == "Hello\nWorld"


class TestFormatEmojiDisplay:
    """Tests for format_emoji_display function."""

    def test_unicode_emoji(self) -> None:
        """Test formatting unicode emoji."""
        result = format_emoji_display("👍", None)
        assert result == "👍"

    def test_unicode_emoji_with_zero_id(self) -> None:
        """Test that 0 emoji_id is treated as falsy."""
        result = format_emoji_display("👍", 0)
        assert result == "👍"

    def test_custom_emoji(self) -> None:
        """Test formatting custom emoji."""
        result = format_emoji_display("custom_emoji", 12345)
        assert result == "<:custom_emoji:12345>"

    def test_custom_emoji_large_id(self) -> None:
        """Test formatting custom emoji with large snowflake ID."""
        result = format_emoji_display("my_emoji", 123456789012345678)
        assert result == "<:my_emoji:123456789012345678>"


class TestBuildPanelEmbed:
    """Tests for build_panel_embed function."""

    def _create_mock_panel(
        self,
        name: str = "TestPanel",
        panel_type: str = PanelType.TOGGLE,
        role_mappings: list[dict[str, Any]] | None = None,
        embed_config: dict[str, Any] | None = None,
    ) -> MagicMock:
        """Create a mock ReactionPanel."""
        panel = MagicMock(spec=ReactionPanel)
        panel.name = name
        panel.panel_type = panel_type
        panel.role_mappings = role_mappings or []
        panel.embed_config = embed_config
        return panel

    def _create_mock_guild(self) -> MagicMock:
        """Create a mock Discord guild."""
        guild = MagicMock(spec=discord.Guild)
        return guild

    def test_basic_embed_with_defaults(self) -> None:
        """Test building embed with default values."""
        panel = self._create_mock_panel()
        guild = self._create_mock_guild()
        guild.get_role.return_value = None

        embed = build_panel_embed(panel, guild)

        assert embed.title == "TestPanel"
        assert embed.description is None  # No default description
        assert embed.color is not None and embed.color.value == 0x5865F2

    def test_embed_with_custom_config(self) -> None:
        """Test building embed with custom config."""
        panel = self._create_mock_panel(
            embed_config={
                "title": "Custom Title",
                "description": "Custom description",
                "color": 0xFF0000,
            }
        )
        guild = self._create_mock_guild()

        embed = build_panel_embed(panel, guild)

        assert embed.title == "Custom Title"
        assert embed.description == "Custom description"
        assert embed.color is not None and embed.color.value == 0xFF0000

    def test_embed_with_override_config(self) -> None:
        """Test that custom_config parameter overrides panel's config."""
        panel = self._create_mock_panel(
            embed_config={
                "title": "Panel Config",
                "color": 0x00FF00,
            }
        )
        guild = self._create_mock_guild()

        custom = {
            "title": "Override Title",
            "color": 0x0000FF,
        }

        embed = build_panel_embed(panel, guild, custom_config=custom)

        assert embed.title == "Override Title"
        assert embed.color is not None and embed.color.value == 0x0000FF

    def test_embed_with_role_mappings(self) -> None:
        """Test building embed with role mappings."""
        panel = self._create_mock_panel(
            role_mappings=[
                {"emoji": "👍", "role_id": 100},
                {"emoji": "👎", "role_id": 200},
            ]
        )
        guild = self._create_mock_guild()

        role1 = MagicMock()
        role1.name = "GoodRole"
        role2 = MagicMock()
        role2.name = "BadRole"

        guild.get_role.side_effect = lambda rid: {100: role1, 200: role2}.get(rid)

        embed = build_panel_embed(panel, guild)

        # Should have a Roles field
        assert len(embed.fields) == 1
        assert embed.fields[0].name == "Roles"
        field_value = embed.fields[0].value or ""
        assert "👍 - GoodRole" in field_value
        assert "👎 - BadRole" in field_value

    def test_embed_with_custom_display_name(self) -> None:
        """Test that display_name overrides role name."""
        panel = self._create_mock_panel(
            role_mappings=[
                {"emoji": "👍", "role_id": 100, "display_name": "Custom Name"},
            ]
        )
        guild = self._create_mock_guild()

        role = MagicMock()
        role.name = "ActualRoleName"
        guild.get_role.return_value = role

        embed = build_panel_embed(panel, guild)

        field_value = embed.fields[0].value or ""
        assert "Custom Name" in field_value
        assert "ActualRoleName" not in field_value

    def test_embed_with_unknown_role(self) -> None:
        """Test that unknown role shows 'Unknown Role'."""
        panel = self._create_mock_panel(
            role_mappings=[
                {"emoji": "👍", "role_id": 99999},
            ]
        )
        guild = self._create_mock_guild()
        guild.get_role.return_value = None

        embed = build_panel_embed(panel, guild)

        assert "Unknown Role" in (embed.fields[0].value or "")

    def test_embed_with_custom_emoji(self) -> None:
        """Test building embed with custom emoji in mappings."""
        panel = self._create_mock_panel(
            role_mappings=[
                {"emoji": "custom", "emoji_id": 12345, "role_id": 100},
            ]
        )
        guild = self._create_mock_guild()

        role = MagicMock()
        role.name = "TestRole"
        guild.get_role.return_value = role

        embed = build_panel_embed(panel, guild)

        assert "<:custom:12345>" in (embed.fields[0].value or "")

    def test_embed_footer_toggle(self) -> None:
        """Test footer text for toggle panel."""
        panel = self._create_mock_panel(panel_type="toggle")
        guild = self._create_mock_guild()

        embed = build_panel_embed(panel, guild)

        assert embed.footer is not None and "Toggle mode" in (embed.footer.text or "")

    def test_embed_footer_exclusive(self) -> None:
        """Test footer text for exclusive panel."""
        panel = self._create_mock_panel(panel_type="exclusive")
        guild = self._create_mock_guild()

        embed = build_panel_embed(panel, guild)

        assert embed.footer is not None and "Exclusive mode" in (embed.footer.text or "")

    def test_embed_footer_verify(self) -> None:
        """Test footer text for verify panel."""
        panel = self._create_mock_panel(panel_type="verify")
        guild = self._create_mock_guild()

        embed = build_panel_embed(panel, guild)

        assert embed.footer is not None and "Verify mode" in (embed.footer.text or "")

    def test_embed_empty_mappings_no_field(self) -> None:
        """Test that empty mappings don't add a field."""
        panel = self._create_mock_panel(role_mappings=[])
        guild = self._create_mock_guild()

        embed = build_panel_embed(panel, guild)

        assert len(embed.fields) == 0


class TestBuildPanelPlaceholderData:
    """Tests for build_panel_placeholder_data function."""

    def _create_mock_panel(self) -> MagicMock:
        """Create a mock ReactionPanel."""
        panel = MagicMock(spec=ReactionPanel)
        panel.name = "TestPanel"
        panel.panel_type = "toggle"
        panel.channel_id = 456
        panel.required_roles = []
        panel.created_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        return panel

    def _create_mock_guild(self) -> MagicMock:
        """Create a mock Discord guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"

        channel = MagicMock()
        channel.mention = "<#456>"
        guild.get_channel.return_value = channel
        guild.get_role.return_value = None

        return guild

    def test_basic_placeholder_data(self) -> None:
        """Test basic placeholder data generation."""
        panel = self._create_mock_panel()
        guild = self._create_mock_guild()

        data = build_panel_placeholder_data(panel, guild)

        assert data["panel_name"] == "TestPanel"
        assert data["panel_type"] == "toggle"
        assert data["channel_mention"] == "<#456>"
        assert data["guild_name"] == "Test Guild"
        assert "created_at" in data
        assert "created_at_relative" in data

    def test_placeholder_data_with_user(self) -> None:
        """Test placeholder data with user provided."""
        panel = self._create_mock_panel()
        guild = self._create_mock_guild()

        user = MagicMock(spec=discord.Member)
        user.display_name = "TestUser"
        user.mention = "<@12345>"

        data = build_panel_placeholder_data(panel, guild, user)

        assert data["user_name"] == "TestUser"
        assert data["user_mention"] == "<@12345>"

    def test_placeholder_data_without_channel(self) -> None:
        """Test placeholder data when channel not found."""
        panel = self._create_mock_panel()
        guild = self._create_mock_guild()
        guild.get_channel.return_value = None

        data = build_panel_placeholder_data(panel, guild)

        assert data["channel_mention"] == "<#456>"

    def test_placeholder_data_with_required_roles(self) -> None:
        """Test placeholder data with required roles."""
        panel = self._create_mock_panel()
        panel.required_roles = [100, 200]

        guild = self._create_mock_guild()
        role1 = MagicMock()
        role1.name = "Admin"
        role2 = MagicMock()
        role2.name = "Mod"
        guild.get_role.side_effect = lambda rid: {100: role1, 200: role2}.get(rid)

        data = build_panel_placeholder_data(panel, guild)

        assert "Admin" in data["required_roles"]
        assert "Mod" in data["required_roles"]

    def test_placeholder_data_with_unknown_required_role(self) -> None:
        """Test placeholder data with unknown required role."""
        panel = self._create_mock_panel()
        panel.required_roles = [99999]

        guild = self._create_mock_guild()
        guild.get_role.return_value = None

        data = build_panel_placeholder_data(panel, guild)

        assert "Unknown(99999)" in data["required_roles"]

    def test_placeholder_data_no_required_roles(self) -> None:
        """Test placeholder data when no required roles."""
        panel = self._create_mock_panel()
        panel.required_roles = []
        guild = self._create_mock_guild()

        data = build_panel_placeholder_data(panel, guild)

        assert data["required_roles"] == "None"

    def test_created_at_relative_format(self) -> None:
        """Test that created_at_relative uses Discord timestamp format."""
        panel = self._create_mock_panel()
        guild = self._create_mock_guild()

        data = build_panel_placeholder_data(panel, guild)

        # datetime(2024, 1, 15, 10, 30, tzinfo=UTC) -> 1705314600
        assert "<t:1705314600:R>" in data["created_at_relative"]


class TestBuildRoleChangePlaceholderData:
    """Tests for build_role_change_placeholder_data function."""

    def _create_mock_panel(self) -> MagicMock:
        """Create a mock ReactionPanel."""
        panel = MagicMock(spec=ReactionPanel)
        panel.name = "TestPanel"
        panel.panel_type = "toggle"
        panel.channel_id = 456
        panel.required_roles = []
        panel.created_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        return panel

    def _create_mock_guild(self) -> MagicMock:
        """Create a mock Discord guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"

        channel = MagicMock()
        channel.mention = "<#456>"
        guild.get_channel.return_value = channel
        guild.get_role.return_value = None

        return guild

    def test_role_change_data(self) -> None:
        """Test role change placeholder data generation."""
        panel = self._create_mock_panel()
        guild = self._create_mock_guild()

        user = MagicMock(spec=discord.Member)
        user.display_name = "TestUser"
        user.mention = "<@12345>"

        role = MagicMock(spec=discord.Role)
        role.name = "TestRole"
        role.mention = "<@&100>"

        data = build_role_change_placeholder_data(panel, guild, user, role)

        assert data["user_name"] == "TestUser"
        assert data["user_mention"] == "<@12345>"
        assert data["role_name"] == "TestRole"
        assert data["role_mention"] == "<@&100>"
        assert data["panel_name"] == "TestPanel"


class TestFormatMappingsDisplay:
    """Tests for format_mappings_display function."""

    def _create_mock_guild(self) -> MagicMock:
        """Create a mock Discord guild."""
        guild = MagicMock(spec=discord.Guild)
        return guild

    def test_empty_mappings(self) -> None:
        """Test formatting empty mappings."""
        guild = self._create_mock_guild()
        result = format_mappings_display([], guild)
        assert result == "No mappings configured"

    def test_single_mapping_with_role(self) -> None:
        """Test formatting single mapping with known role."""
        guild = self._create_mock_guild()

        role = MagicMock()
        role.name = "TestRole"
        role.mention = "<@&100>"
        guild.get_role.return_value = role

        mappings = [{"emoji": "👍", "role_id": 100}]
        result = format_mappings_display(mappings, guild)

        assert "👍 -> <@&100> (TestRole)" in result

    def test_multiple_mappings(self) -> None:
        """Test formatting multiple mappings."""
        guild = self._create_mock_guild()

        role1 = MagicMock()
        role1.name = "Role1"
        role1.mention = "<@&100>"

        role2 = MagicMock()
        role2.name = "Role2"
        role2.mention = "<@&200>"

        guild.get_role.side_effect = lambda rid: {100: role1, 200: role2}.get(rid)

        mappings = [
            {"emoji": "👍", "role_id": 100},
            {"emoji": "👎", "role_id": 200},
        ]
        result = format_mappings_display(mappings, guild)

        assert "👍 -> <@&100> (Role1)" in result
        assert "👎 -> <@&200> (Role2)" in result

    def test_mapping_with_display_name(self) -> None:
        """Test formatting mapping with custom display name."""
        guild = self._create_mock_guild()

        role = MagicMock()
        role.name = "ActualName"
        role.mention = "<@&100>"
        guild.get_role.return_value = role

        mappings = [{"emoji": "👍", "role_id": 100, "display_name": "Custom Name"}]
        result = format_mappings_display(mappings, guild)

        assert "(Custom Name)" in result
        assert "ActualName" not in result

    def test_mapping_with_unknown_role(self) -> None:
        """Test formatting mapping with unknown role."""
        guild = self._create_mock_guild()
        guild.get_role.return_value = None

        mappings = [{"emoji": "👍", "role_id": 99999}]
        result = format_mappings_display(mappings, guild)

        assert "<@&99999>" in result
        assert "Unknown Role" in result

    def test_mapping_with_custom_emoji(self) -> None:
        """Test formatting mapping with custom emoji."""
        guild = self._create_mock_guild()

        role = MagicMock()
        role.name = "TestRole"
        role.mention = "<@&100>"
        guild.get_role.return_value = role

        mappings = [{"emoji": "custom", "emoji_id": 12345, "role_id": 100}]
        result = format_mappings_display(mappings, guild)

        assert "<:custom:12345>" in result
