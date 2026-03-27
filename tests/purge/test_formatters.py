"""Tests for discord_bot/purge/formatters.py."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import discord
import pytest

from discord_bot.purge.enums import ConfigKey, PurgeStatus, PurgeType
from discord_bot.purge.formatters import (
    format_authorized_by,
    format_message,
    format_roles,
    get_button_style,
    get_mod_message_content,
)


@pytest.fixture
def mock_guild() -> MagicMock:
    """Create mock of a guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.name = "Test Guild"
    guild.get_member = MagicMock(return_value=None)
    guild.get_role = MagicMock(return_value=None)
    return guild


@pytest.fixture
def mock_purge_record() -> MagicMock:
    """Create mock of a purge record."""
    record = MagicMock()
    record.id = 1
    record.guild_id = 123456789
    record.purge_type = PurgeType.WAR_END
    record.status = PurgeStatus.PENDING
    record.initiated_by = 111222333
    record.authorized_by = [111222333]
    record.cancelled_by = []
    record.confirmed_by = []
    record.scheduled_for = datetime.now(UTC) + timedelta(days=3)
    record.expires_at = datetime.now(UTC) + timedelta(hours=1)
    record.config_snapshot = {}
    return record


class TestFormatMessage:
    """Tests for format_message."""

    def test_format_all_placeholders(self) -> None:
        """Test replacement of all placeholders."""
        template = "Status: {status}, Day: {day}"

        result = format_message(
            template,
            status="Pending",
            day="2024-01-01",
        )

        assert result == "Status: Pending, Day: 2024-01-01"

    def test_format_empty_placeholders(self) -> None:
        """Test with placeholder passed as None."""
        template = "User: {username}"
        result = format_message(template, username=None)
        assert result == "User: "

    def test_format_unmatched_placeholder(self) -> None:
        """Test that unpassed placeholders are preserved."""
        template = "User: {username}"
        result = format_message(template)
        assert result == "User: {username}"

    def test_format_no_placeholders(self) -> None:
        """Test message without placeholders."""
        template = "Simple message without placeholders"
        result = format_message(template)
        assert result == template

    def test_format_none_template(self) -> None:
        """Test with None template."""
        result = format_message(None, status="Test")
        assert result == ""


class TestGetButtonStyle:
    """Tests for get_button_style."""

    def test_blurple(self) -> None:
        """Test blurple style."""
        result = get_button_style("blurple")
        assert result == discord.ButtonStyle.primary

    def test_grey(self) -> None:
        """Test grey style."""
        result = get_button_style("grey")
        assert result == discord.ButtonStyle.secondary

    def test_green(self) -> None:
        """Test green style."""
        result = get_button_style("green")
        assert result == discord.ButtonStyle.success

    def test_red(self) -> None:
        """Test red style."""
        result = get_button_style("red")
        assert result == discord.ButtonStyle.danger

    def test_unknown_defaults_to_success(self) -> None:
        """Test that unknown color returns success."""
        result = get_button_style("unknown")
        assert result == discord.ButtonStyle.success


class TestFormatAuthorizedBy:
    """Tests for format_authorized_by."""

    def test_empty_list(self, mock_guild: MagicMock) -> None:
        """Test with empty list."""
        result = format_authorized_by(mock_guild, [])
        assert result == "None"

    def test_with_found_members(self, mock_guild: MagicMock) -> None:
        """Test with found members."""
        member1 = MagicMock(spec=discord.Member)
        member1.display_name = "User1"
        member2 = MagicMock(spec=discord.Member)
        member2.display_name = "User2"

        mock_guild.get_member = MagicMock(
            side_effect=lambda uid: member1 if uid == 111 else member2 if uid == 222 else None
        )

        result = format_authorized_by(mock_guild, [111, 222])
        assert result == "User1, User2"

    def test_with_not_found_members(self, mock_guild: MagicMock) -> None:
        """Test with members not found."""
        mock_guild.get_member = MagicMock(return_value=None)

        result = format_authorized_by(mock_guild, [111, 222])
        assert result == "<@111>, <@222>"

    def test_mixed_members(self, mock_guild: MagicMock) -> None:
        """Test with mix of found and not found members."""
        member1 = MagicMock(spec=discord.Member)
        member1.display_name = "User1"

        mock_guild.get_member = MagicMock(side_effect=lambda uid: member1 if uid == 111 else None)

        result = format_authorized_by(mock_guild, [111, 222])
        assert result == "User1, <@222>"


class TestFormatRoles:
    """Tests for format_roles."""

    def test_empty_list(self, mock_guild: MagicMock) -> None:
        """Test with empty list."""
        result = format_roles(mock_guild, [])
        assert result == "None"

    def test_with_found_roles(self, mock_guild: MagicMock) -> None:
        """Test with found roles."""
        role1 = MagicMock(spec=discord.Role)
        role1.mention = "@Role1"
        role2 = MagicMock(spec=discord.Role)
        role2.mention = "@Role2"

        mock_guild.get_role = MagicMock(
            side_effect=lambda rid: role1 if rid == 100 else role2 if rid == 200 else None
        )

        result = format_roles(mock_guild, [100, 200])
        assert result == "@Role1, @Role2"

    def test_with_not_found_roles(self, mock_guild: MagicMock) -> None:
        """Test with roles not found."""
        mock_guild.get_role = MagicMock(return_value=None)

        result = format_roles(mock_guild, [100, 200])
        assert result == "<@&100>, <@&200>"


class TestGetModMessageContent:
    """Tests for get_mod_message_content."""

    def test_pending_status(
        self,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test content with pending status."""
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Status: {status}",
            ConfigKey.MOD_STATUS_PENDING: "Pending",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purge_record, config=config)

        assert "Pending" in result

    def test_authorized_status(
        self,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test content with authorized status."""
        mock_purge_record.status = PurgeStatus.AUTHORIZED
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Status: {status}",
            ConfigKey.MOD_STATUS_AUTHORIZED: "Authorized",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purge_record, config=config)

        assert "Authorized" in result

    def test_with_execution_logs(
        self,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test content with execution logs."""
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Base message",
            ConfigKey.MOD_STATUS_PENDING: "Pending",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }
        logs = ["Log line 1", "Log line 2"]

        result = get_mod_message_content(
            guild=mock_guild,
            record=mock_purge_record,
            config=config,
            execution_logs=logs,
        )

        assert "**Logs:**" in result
        assert "Log line 1" in result
        assert "Log line 2" in result

    def test_without_execution_logs(
        self,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test content without execution logs."""
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Base message",
            ConfigKey.MOD_STATUS_PENDING: "Pending",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purge_record, config=config)

        assert "**Logs:**" not in result

    def test_war_purge_type(
        self,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test that it shows war purge type."""
        mock_purge_record.purge_type = PurgeType.WAR_END
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "{purge_type}",
            ConfigKey.MOD_STATUS_PENDING: "Pending",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purge_record, config=config)

        assert "war end" in result.lower()

    def test_all_status_messages(
        self,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test all possible statuses."""
        statuses = [
            (PurgeStatus.PENDING, ConfigKey.MOD_STATUS_PENDING, "Pending"),
            (PurgeStatus.AUTHORIZED, ConfigKey.MOD_STATUS_AUTHORIZED, "Authorized"),
            (PurgeStatus.EXPIRED, ConfigKey.MOD_STATUS_EXPIRED, "Expired"),
            (
                PurgeStatus.CANCEL_PENDING,
                ConfigKey.MOD_STATUS_CANCEL_PENDING,
                "Cancel pending",
            ),
            (PurgeStatus.CANCELLED, ConfigKey.MOD_STATUS_CANCELLED, "Cancelled"),
            (PurgeStatus.EXECUTED, ConfigKey.MOD_STATUS_EXECUTED, "Executed"),
        ]

        for status, config_key, expected_text in statuses:
            mock_purge_record.status = status
            config: dict[str, Any] = {
                ConfigKey.MOD_MESSAGE_TEMPLATE: "Status: {status}",
                config_key: expected_text,
                ConfigKey.MOD_REQUIRED_REACTIONS: 2,
            }

            result = get_mod_message_content(
                guild=mock_guild, record=mock_purge_record, config=config
            )

            assert expected_text in result, f"Failed for status {status}"

    def test_failed_status(
        self,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test that FAILED status has default text."""
        mock_purge_record.status = PurgeStatus.FAILED
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Status: {status}",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purge_record, config=config)

        assert "Failed" in result

    def test_scheduled_for_date_formatting(
        self,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test execution date formatting."""
        mock_purge_record.scheduled_for = datetime(2024, 6, 15, 18, 0, 0, tzinfo=UTC)
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Date: {dia}",
            ConfigKey.MOD_STATUS_PENDING: "Pending",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purge_record, config=config)

        assert "2024-06-15 18:00 UTC" in result

    def test_no_scheduled_for(
        self,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test when no scheduled date."""
        mock_purge_record.scheduled_for = None
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Date: {dia}",
            ConfigKey.MOD_STATUS_PENDING: "Pending",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purge_record, config=config)

        assert "Not scheduled" in result

    def test_war_purge_custom_display_name(
        self,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test custom name for war purge."""
        mock_purge_record.purge_type = PurgeType.WAR_END
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "{purge_type}",
            ConfigKey.MOD_STATUS_PENDING: "Pending",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
            ConfigKey.WAR_DISPLAY_NAME: "End of war",
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purge_record, config=config)

        assert "End of war" in result

    def test_global_purge_type(
        self,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test global purge type with default name."""
        mock_purge_record.purge_type = PurgeType.GLOBAL
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "{purge_type}",
            ConfigKey.MOD_STATUS_PENDING: "Pending",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purge_record, config=config)

        assert "global" in result.lower()

    def test_global_purge_custom_display_name(
        self,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test custom name for global purge."""
        mock_purge_record.purge_type = PurgeType.GLOBAL
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "{purge_type}",
            ConfigKey.MOD_STATUS_PENDING: "Pending",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
            ConfigKey.GLOBAL_DISPLAY_NAME: "General cleanup",
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purge_record, config=config)

        assert "General cleanup" in result
