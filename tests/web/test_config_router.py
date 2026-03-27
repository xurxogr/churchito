"""Tests for the configuration router."""

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.web.routers.config import (
    _convert_form_value,
    _format_relative_time,
    _get_guild_info,
    _validate_channel_permissions,
    get_templates,
    guild_access_dep,
    router,
)


@pytest.fixture
def config_app(simple_app: FastAPI) -> FastAPI:
    """Create application with config router.

    Args:
        simple_app (FastAPI): Base application

    Returns:
        FastAPI: Application with config router
    """
    simple_app.include_router(router)
    return simple_app


@pytest.fixture
def config_client(config_app: FastAPI) -> TestClient:
    """Create client for config.

    Args:
        config_app (FastAPI): Application

    Returns:
        TestClient: Test client
    """
    return TestClient(config_app)


class TestGetTemplates:
    """Tests for get_templates."""

    def test_returns_templates(self, simple_app: FastAPI) -> None:
        """Test that it returns templates."""
        request = MagicMock()
        request.app = simple_app

        templates = get_templates(request)
        assert templates is not None


class TestGetGuildInfo:
    """Tests for _get_guild_info."""

    def test_returns_guild_when_found(self) -> None:
        """Test that it returns guild info when found."""
        mock_bot = MagicMock()
        mock_guild = MagicMock()
        mock_guild.id = 111222333
        mock_guild.name = "Test Guild"
        mock_guild.icon = None
        mock_bot.get_guild.return_value = mock_guild

        result = _get_guild_info(mock_bot, 111222333)
        assert result["name"] == "Test Guild"

    def test_returns_default_when_not_found(self) -> None:
        """Test that it returns default info when not found."""
        mock_bot = MagicMock()
        mock_bot.get_guild.return_value = None

        result = _get_guild_info(mock_bot, 999999)
        assert result["id"] == "999999"
        assert "Server" in result["name"]


class TestConvertFormValue:
    """Tests for _convert_form_value."""

    def test_convert_empty_string_preserved(self) -> None:
        """Test that empty STRING is preserved (allows clearing config)."""
        result = _convert_form_value("", ConfigOptionType.STRING)
        assert result == ""

    def test_convert_empty_textarea_preserved(self) -> None:
        """Test that empty TEXTAREA is preserved."""
        result = _convert_form_value("", ConfigOptionType.TEXTAREA)
        assert result == ""

    def test_convert_empty_integer_returns_none(self) -> None:
        """Test that empty INTEGER returns None."""
        result = _convert_form_value("", ConfigOptionType.INTEGER)
        assert result is None

    def test_convert_integer(self) -> None:
        """Test integer conversion."""
        result = _convert_form_value("42", ConfigOptionType.INTEGER)
        assert result == 42

    def test_convert_boolean_true(self) -> None:
        """Test boolean True conversion."""
        for value in ["true", "1", "on", "yes"]:
            result = _convert_form_value(value, ConfigOptionType.BOOLEAN)
            assert result is True

    def test_convert_boolean_false(self) -> None:
        """Test boolean False conversion."""
        result = _convert_form_value("false", ConfigOptionType.BOOLEAN)
        assert result is False

    def test_convert_channel(self) -> None:
        """Test channel conversion."""
        result = _convert_form_value("123456789", ConfigOptionType.CHANNEL)
        assert result == 123456789

    def test_convert_role(self) -> None:
        """Test role conversion."""
        result = _convert_form_value("987654321", ConfigOptionType.ROLE)
        assert result == 987654321

    def test_convert_channel_list(self) -> None:
        """Test channel list conversion."""
        result = _convert_form_value("123,456,789", ConfigOptionType.CHANNEL_LIST)
        assert result == [123, 456, 789]

    def test_convert_channel_list_empty(self) -> None:
        """Test empty channel list conversion."""
        result = _convert_form_value("", ConfigOptionType.CHANNEL_LIST)
        assert result is None

    def test_convert_role_list(self) -> None:
        """Test role list conversion."""
        result = _convert_form_value("111,222,333", ConfigOptionType.ROLE_LIST)
        assert result == [111, 222, 333]

    def test_convert_string(self) -> None:
        """Test string conversion."""
        result = _convert_form_value("hello world", ConfigOptionType.STRING)
        assert result == "hello world"

    def test_convert_text_choice(self) -> None:
        """Test text choice conversion."""
        result = _convert_form_value("option_a", ConfigOptionType.TEXT_CHOICE)
        assert result == "option_a"


class TestValidateChannelPermissions:
    """Tests for _validate_channel_permissions."""

    def test_returns_none_when_no_bot(self, simple_app: FastAPI) -> None:
        """Test that it returns None when there is no bot."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.bot = None

        result = _validate_channel_permissions(request, 123, 456)
        assert result is None

    def test_returns_none_when_guild_not_found(self, simple_app: FastAPI) -> None:
        """Test that it returns None when guild is not found."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = None

        result = _validate_channel_permissions(request, 123, 456)
        assert result is None

    def test_returns_error_when_channel_not_found(self, simple_app: FastAPI) -> None:
        """Test that it returns error when channel is not found."""
        request = MagicMock()
        request.app = simple_app
        mock_guild = MagicMock()
        mock_guild.get_channel.return_value = None
        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = mock_guild

        result = _validate_channel_permissions(request, 123, 456)
        assert result is not None
        assert "456" in result
        assert "not found" in result

    def test_returns_none_when_bot_member_not_found(self, simple_app: FastAPI) -> None:
        """Test that it returns None when bot member is not found."""
        request = MagicMock()
        request.app = simple_app
        mock_channel = MagicMock()
        mock_guild = MagicMock()
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.get_member.return_value = None
        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = mock_guild
        simple_app.state.bot.user.id = 12345

        result = _validate_channel_permissions(request, 123, 456)
        assert result is None

    def test_returns_error_when_no_send_permission(self, simple_app: FastAPI) -> None:
        """Test that it returns error when there is no send permission."""
        request = MagicMock()
        request.app = simple_app
        mock_permissions = MagicMock()
        mock_permissions.send_messages = False
        mock_channel = MagicMock()
        mock_channel.name = "test-channel"
        mock_channel.permissions_for.return_value = mock_permissions
        mock_bot_member = MagicMock()
        mock_guild = MagicMock()
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.get_member.return_value = mock_bot_member
        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = mock_guild
        simple_app.state.bot.user.id = 12345

        result = _validate_channel_permissions(request, 123, 456)
        assert result is not None
        assert "test-channel" in result
        assert "permission" in result.lower()

    def test_returns_none_when_has_permission(self, simple_app: FastAPI) -> None:
        """Test that it returns None when it has permission."""
        request = MagicMock()
        request.app = simple_app
        mock_permissions = MagicMock()
        mock_permissions.send_messages = True
        mock_channel = MagicMock()
        mock_channel.permissions_for.return_value = mock_permissions
        mock_bot_member = MagicMock()
        mock_guild = MagicMock()
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.get_member.return_value = mock_bot_member
        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = mock_guild
        simple_app.state.bot.user.id = 12345

        result = _validate_channel_permissions(request, 123, 456)
        assert result is None


class TestGuildAccessDep:
    """Tests for guild_access_dep."""

    async def test_returns_user_when_has_access(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Test that it returns user when they have access."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = [123456789012345678]

        result = await guild_access_dep(request, 111222333, test_user)
        assert result == test_user


class TestFormatRelativeTime:
    """Tests for _format_relative_time."""

    def test_seconds(self) -> None:
        """Test format for seconds."""
        result = _format_relative_time(timedelta(seconds=30))
        assert result == "a few seconds ago"

    def test_one_minute(self) -> None:
        """Test format for 1 minute."""
        result = _format_relative_time(timedelta(minutes=1))
        assert result == "1 minute ago"

    def test_multiple_minutes(self) -> None:
        """Test format for multiple minutes."""
        result = _format_relative_time(timedelta(minutes=45))
        assert result == "45 minutes ago"

    def test_one_hour(self) -> None:
        """Test format for 1 hour."""
        result = _format_relative_time(timedelta(hours=1))
        assert result == "1 hour ago"

    def test_multiple_hours(self) -> None:
        """Test format for multiple hours."""
        result = _format_relative_time(timedelta(hours=12))
        assert result == "12 hours ago"

    def test_one_day(self) -> None:
        """Test format for 1 day."""
        result = _format_relative_time(timedelta(days=1))
        assert result == "1 day ago"

    def test_multiple_days(self) -> None:
        """Test format for multiple days."""
        result = _format_relative_time(timedelta(days=15))
        assert result == "15 days ago"

    def test_one_month(self) -> None:
        """Test format for 1 month (~30 days)."""
        result = _format_relative_time(timedelta(days=30))
        assert result == "1 month ago"

    def test_multiple_months(self) -> None:
        """Test format for multiple months."""
        result = _format_relative_time(timedelta(days=180))
        assert result == "6 months ago"

    def test_one_year(self) -> None:
        """Test format for 1 year (~365 days)."""
        result = _format_relative_time(timedelta(days=365))
        assert result == "1 year ago"

    def test_multiple_years(self) -> None:
        """Test format for multiple years."""
        result = _format_relative_time(timedelta(days=730))
        assert result == "2 years ago"


class TestConvertFormValueEmbedSections:
    """Tests for _convert_form_value with EMBED_SECTIONS."""

    def test_valid_json_list(self) -> None:
        """Test conversion of valid JSON as list."""
        value = '[{"type": "text", "title": "Test", "content": "Hello"}]'
        result = _convert_form_value(value, ConfigOptionType.EMBED_SECTIONS)
        assert result == [{"type": "text", "title": "Test", "content": "Hello"}]

    def test_empty_list(self) -> None:
        """Test conversion of empty list."""
        result = _convert_form_value("[]", ConfigOptionType.EMBED_SECTIONS)
        assert result == []

    def test_invalid_json(self) -> None:
        """Test that invalid JSON returns None."""
        result = _convert_form_value("{invalid json}", ConfigOptionType.EMBED_SECTIONS)
        assert result is None

    def test_json_not_list(self) -> None:
        """Test that JSON that is not a list returns None."""
        result = _convert_form_value('{"key": "value"}', ConfigOptionType.EMBED_SECTIONS)
        assert result is None

    def test_json_too_large(self) -> None:
        """Test that JSON too large returns None."""
        # Create a JSON larger than 100KB
        large_value = "[" + ",".join(['"x"' * 1000] * 200) + "]"
        assert len(large_value) > 100_000
        result = _convert_form_value(large_value, ConfigOptionType.EMBED_SECTIONS)
        assert result is None
