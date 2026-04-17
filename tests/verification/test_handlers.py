"""Tests for verification handlers."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_bot.common.utils import is_valid_discord_cdn_url
from discord_bot.verification.enums import ConfigKey, VerificationStatus, VerificationType
from discord_bot.verification.handlers import (
    update_mod_message_cancelled,
    update_mod_message_for_manual_review,
    update_tracker_message,
)
from discord_bot.verification.handlers.auto_processing import send_mod_ping_message
from discord_bot.verification.handlers.utils import (
    calculate_expires_timestamp,
    create_screenshot_embeds,
    get_api_error_message,
)
from discord_bot.verification.models import VerificationRequest


class TestCalculateExpiresTimestamp:
    """Tests for calculate_expires_timestamp."""

    def test_returns_empty_string_when_timeout_is_zero(self) -> None:
        """Test that returns empty string when timeout is 0."""
        created_at = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
        result = calculate_expires_timestamp(created_at, 0)
        assert result == ""

    def test_returns_empty_string_when_timeout_is_negative(self) -> None:
        """Test that returns empty string when timeout is negative."""
        created_at = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
        result = calculate_expires_timestamp(created_at, -5)
        assert result == ""

    def test_returns_relative_timestamp_format(self) -> None:
        """Test that returns Discord relative timestamp format."""
        created_at = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
        result = calculate_expires_timestamp(created_at, 60)

        # Verify it has the correct format <t:TIMESTAMP:R>
        assert result.startswith("<t:")
        assert result.endswith(":R>")

    def test_calculates_correct_expiration_time(self) -> None:
        """Test that calculates correct expiration time."""
        created_at = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
        timeout_minutes = 60

        result = calculate_expires_timestamp(created_at, timeout_minutes)

        # Extract timestamp from result
        timestamp_str = result[3:-3]  # Remove "<t:" and ":R>"
        timestamp = int(timestamp_str)

        # Calculate expected timestamp (created_at + 60 minutes)
        expected_timestamp = int(created_at.timestamp()) + (60 * 60)

        assert timestamp == expected_timestamp

    def test_works_with_different_timeout_values(self) -> None:
        """Test with different timeout values."""
        created_at = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
        base_timestamp = int(created_at.timestamp())

        # 5 minutes
        result_5 = calculate_expires_timestamp(created_at, 5)
        timestamp_5 = int(result_5[3:-3])
        assert timestamp_5 == base_timestamp + (5 * 60)

        # 30 minutes
        result_30 = calculate_expires_timestamp(created_at, 30)
        timestamp_30 = int(result_30[3:-3])
        assert timestamp_30 == base_timestamp + (30 * 60)

        # 1440 minutes (24 hours)
        result_1440 = calculate_expires_timestamp(created_at, 1440)
        timestamp_1440 = int(result_1440[3:-3])
        assert timestamp_1440 == base_timestamp + (1440 * 60)


class TestIsValidDiscordUrl:
    """Tests for is_valid_discord_cdn_url."""

    def test_valid_cdn_url(self) -> None:
        """Test valid cdn.discordapp.com URL."""
        url = "https://cdn.discordapp.com/attachments/123/456/image.png"
        assert is_valid_discord_cdn_url(url) is True

    def test_valid_media_url(self) -> None:
        """Test valid media.discordapp.net URL."""
        url = "https://media.discordapp.net/attachments/123/456/image.png"
        assert is_valid_discord_cdn_url(url) is True

    def test_empty_url(self) -> None:
        """Test that empty URL returns False."""
        assert is_valid_discord_cdn_url("") is False

    def test_http_url(self) -> None:
        """Test that HTTP URL (not HTTPS) returns False."""
        url = "http://cdn.discordapp.com/attachments/123/456/image.png"
        assert is_valid_discord_cdn_url(url) is False

    def test_wrong_domain(self) -> None:
        """Test that wrong domain returns False."""
        url = "https://example.com/image.png"
        assert is_valid_discord_cdn_url(url) is False

    def test_malicious_url(self) -> None:
        """Test that malicious URL returns False."""
        url = "https://evil.com/cdn.discordapp.com/image.png"
        assert is_valid_discord_cdn_url(url) is False

    def test_subdomain_attack(self) -> None:
        """Test that malicious subdomain returns False."""
        url = "https://cdn.discordapp.com.evil.com/image.png"
        assert is_valid_discord_cdn_url(url) is False

    def test_url_with_query_params(self) -> None:
        """Test valid URL with query params."""
        url = "https://cdn.discordapp.com/attachments/123/456/image.png?size=128"
        assert is_valid_discord_cdn_url(url) is True

    def test_url_too_short_for_parsing(self) -> None:
        """Test URL too short that could cause IndexError."""
        # URL that starts with https:// but has no domain
        url = "https://"
        assert is_valid_discord_cdn_url(url) is False

    def test_url_with_only_domain(self) -> None:
        """Test URL with only domain, no path."""
        url = "https://cdn.discordapp.com"
        assert is_valid_discord_cdn_url(url) is True


class TestCreateScreenshotEmbeds:
    """Tests for create_screenshot_embeds."""

    def test_creates_two_embeds_for_two_urls(self) -> None:
        """Test that creates two embeds for two URLs."""
        url1 = "https://cdn.discordapp.com/attachments/123/456/1.png"
        url2 = "https://cdn.discordapp.com/attachments/123/456/2.png"

        embeds = create_screenshot_embeds(url1=url1, url2=url2)

        assert len(embeds) == 2
        assert embeds[0].image.url == url1
        assert embeds[1].image.url == url2

    def test_creates_one_embed_for_one_url(self) -> None:
        """Test that creates one embed if there is only one URL."""
        url1 = "https://cdn.discordapp.com/attachments/123/456/1.png"

        embeds = create_screenshot_embeds(url1=url1, url2=None)

        assert len(embeds) == 1
        assert embeds[0].image.url == url1

    def test_creates_empty_list_for_no_urls(self) -> None:
        """Test that returns empty list if there are no URLs."""
        embeds = create_screenshot_embeds(url1=None, url2=None)

        assert len(embeds) == 0

    def test_skips_none_url(self) -> None:
        """Test that skips None URL."""
        url2 = "https://cdn.discordapp.com/attachments/123/456/2.png"

        embeds = create_screenshot_embeds(url1=None, url2=url2)

        assert len(embeds) == 1
        assert embeds[0].image.url == url2


class TestGetApiErrorMessage:
    """Tests for get_api_error_message."""

    def test_401_unauthorized(self) -> None:
        """Test message for 401."""
        result = get_api_error_message(401)
        assert result == "API key required or invalid"

    def test_413_too_large(self) -> None:
        """Test message for 413."""
        result = get_api_error_message(413)
        assert result == "Image exceeds maximum upload size"

    def test_422_not_in_error_messages(self) -> None:
        """Test that 422 is not in API_ERROR_MESSAGES (handled separately)."""
        # 422 is handled separately as "invalid images", not as an API error
        result = get_api_error_message(422)
        assert result == "API Error (code: 422)"

    def test_429_rate_limit(self) -> None:
        """Test message for 429."""
        result = get_api_error_message(429)
        assert result == "Rate limit exceeded"

    def test_500_internal_error(self) -> None:
        """Test message for 500."""
        result = get_api_error_message(500)
        assert result == "Internal processing error"

    def test_unknown_status_code(self) -> None:
        """Test message for unknown status code."""
        result = get_api_error_message(418)
        assert result == "API Error (code: 418)"


class TestUpdateModMessageForReview:
    """Tests for update_mod_message_for_manual_review."""

    def _create_mock_request(self) -> MagicMock:
        """Create a mock request with required attributes."""
        mock_request = MagicMock()
        mock_request.mod_message_id = 999
        mock_request.rejection_reason = "Test rejection"
        mock_request.verification_type = VerificationType.REGULAR
        return mock_request

    def _create_config(self) -> dict[str, Any]:
        """Create a config with required keys."""
        return {
            "mod_notification_channel": 888,
            "status_rejected": "❌ Rejected by {moderator}: {reason}",
            "status_pending_review": "⏳ Pending review",
        }

    @pytest.mark.asyncio
    async def test_returns_early_when_no_mod_message_id(self) -> None:
        """Test that returns if there is no mod_message_id."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_request = self._create_mock_request()
        mock_request.mod_message_id = None

        config = self._create_config()

        # Should not fail, just return
        await update_mod_message_for_manual_review(mock_guild, mock_request, config, "abc123")

    @pytest.mark.asyncio
    async def test_returns_early_when_no_mod_channel_id(self) -> None:
        """Test that returns if there is no moderation channel configured."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_request = self._create_mock_request()

        config = self._create_config()
        config["mod_notification_channel"] = None

        await update_mod_message_for_manual_review(mock_guild, mock_request, config, "abc123")

    @pytest.mark.asyncio
    async def test_returns_early_when_channel_not_found(self) -> None:
        """Test that returns if channel does not exist."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=None)

        mock_request = self._create_mock_request()
        config = self._create_config()

        await update_mod_message_for_manual_review(mock_guild, mock_request, config, "abc123")

    @pytest.mark.asyncio
    async def test_returns_early_when_channel_wrong_type(self) -> None:
        """Test that returns if channel is not TextChannel."""
        mock_channel = MagicMock(spec=discord.VoiceChannel)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        mock_request = self._create_mock_request()
        config = self._create_config()

        await update_mod_message_for_manual_review(mock_guild, mock_request, config, "abc123")

    @pytest.mark.asyncio
    async def test_handles_message_not_found(self) -> None:
        """Test that handles NotFound when searching for message."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        mock_request = self._create_mock_request()
        config = self._create_config()

        # Should not fail
        await update_mod_message_for_manual_review(mock_guild, mock_request, config, "abc123")


class TestUpdateModMessageCancelled:
    """Tests for update_mod_message_cancelled."""

    @pytest.mark.asyncio
    async def test_returns_early_if_no_mod_message_id(self) -> None:
        """Test that returns if there is no mod_message_id."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_request = MagicMock(spec=VerificationRequest)
        mock_request.mod_message_id = None

        # Should not do anything
        await update_mod_message_cancelled(
            guild=mock_guild,
            request=mock_request,
            config={},
            previous_statuses=["⏳ Pending"],
        )

        mock_guild.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_no_mod_channel_config(self) -> None:
        """Test that returns if there is no moderation channel configured."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_request = MagicMock(spec=VerificationRequest)
        mock_request.mod_message_id = 123

        await update_mod_message_cancelled(
            guild=mock_guild,
            request=mock_request,
            config={},
            previous_statuses=["⏳ Pending"],
        )

        mock_guild.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_channel_not_found(self) -> None:
        """Test that returns if channel does not exist."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_request = MagicMock(spec=VerificationRequest)
        mock_request.mod_message_id = 123

        config = {"mod_notification_channel": 456}

        await update_mod_message_cancelled(
            guild=mock_guild,
            request=mock_request,
            config=config,
            previous_statuses=["⏳ Pending"],
        )

        mock_guild.get_channel.assert_called_once_with(456)

    @pytest.mark.asyncio
    async def test_deletes_message_if_configured(self) -> None:
        """Test that deletes message if DELETE_PROCESSED_MESSAGES is active."""
        mock_message = MagicMock(spec=discord.Message)
        mock_message.delete = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        mock_request = MagicMock(spec=VerificationRequest)
        mock_request.mod_message_id = 123

        config = {
            "mod_notification_channel": 456,
            "delete_processed_messages": True,
        }

        await update_mod_message_cancelled(
            guild=mock_guild,
            request=mock_request,
            config=config,
            previous_statuses=["⏳ Pending"],
        )

        mock_message.delete.assert_called_once()
        mock_message.edit.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_message_with_cancelled_status(self) -> None:
        """Test that updates message with cancelled status."""
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.description = "User: Test\n\n⏳ Waiting for screenshots..."
        mock_embed.title = None
        mock_embed.fields = []
        mock_embed.copy = MagicMock(return_value=mock_embed)

        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [mock_embed]
        mock_message.edit = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        mock_request = MagicMock(spec=VerificationRequest)
        mock_request.mod_message_id = 123
        mock_request.username = "TestUser"
        mock_request.user_id = 789
        mock_request.verification_type = VerificationType.REGULAR

        config = {
            "mod_notification_channel": 456,
            "delete_processed_messages": False,
            "status_awaiting_screenshots": "⏳ Waiting for screenshots...",
            "status_cancelled": "🚫 Cancelled",
        }

        await update_mod_message_cancelled(
            guild=mock_guild,
            request=mock_request,
            config=config,
            previous_statuses=["⏳ Waiting for screenshots..."],
        )

        mock_message.edit.assert_called_once()
        call_kwargs = mock_message.edit.call_args[1]
        assert call_kwargs["view"] is None
        assert len(call_kwargs["embeds"]) >= 1

    @pytest.mark.asyncio
    async def test_handles_message_not_found(self) -> None:
        """Test that handles when message does not exist."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        mock_request = MagicMock(spec=VerificationRequest)
        mock_request.mod_message_id = 123

        config = {"mod_notification_channel": 456}

        # Should not raise exception
        await update_mod_message_cancelled(
            guild=mock_guild,
            request=mock_request,
            config=config,
            previous_statuses=["⏳ Pending"],
        )


class TestSendModPingMessage:
    """Tests for send_mod_ping_message."""

    @pytest.mark.asyncio
    async def test_sends_ping_message_with_roles(self) -> None:
        """Test that sends message with role mentions."""
        mock_role = MagicMock(spec=discord.Role)
        mock_role.mention = "<@&123>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.guild = mock_guild
        mock_channel.send = AsyncMock()

        config = {
            "mod_ping_message": "{roles} - New verification",
            "mod_roles": [123],
        }

        await send_mod_ping_message(mock_channel, config)

        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args
        assert "<@&123> - New verification" in call_args.kwargs["content"]

    @pytest.mark.asyncio
    async def test_does_not_send_when_no_template(self) -> None:
        """Test that does not send if no template is configured."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()

        config: dict[str, Any] = {
            "mod_ping_message": "",
            "mod_roles": [123],
        }

        await send_mod_ping_message(mock_channel, config)

        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_send_when_no_roles(self) -> None:
        """Test that does not send if no roles are configured."""
        mock_guild = MagicMock(spec=discord.Guild)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.guild = mock_guild
        mock_channel.send = AsyncMock()

        config = {
            "mod_ping_message": "{roles} - New verification",
            "mod_roles": [],
        }

        await send_mod_ping_message(mock_channel, config)

        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_send_when_roles_not_found(self) -> None:
        """Test that does not send if roles do not exist in guild."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_role = MagicMock(return_value=None)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.guild = mock_guild
        mock_channel.send = AsyncMock()

        config = {
            "mod_ping_message": "{roles} - New verification",
            "mod_roles": [999],
        }

        await send_mod_ping_message(mock_channel, config)

        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_with_multiple_roles(self) -> None:
        """Test that sends with multiple roles."""
        mock_role1 = MagicMock(spec=discord.Role)
        mock_role1.mention = "<@&111>"
        mock_role2 = MagicMock(spec=discord.Role)
        mock_role2.mention = "<@&222>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_role = MagicMock(side_effect=[mock_role1, mock_role2])

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.guild = mock_guild
        mock_channel.send = AsyncMock()

        config = {
            "mod_ping_message": "{roles} - Pending",
            "mod_roles": [111, 222],
        }

        await send_mod_ping_message(mock_channel, config)

        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args
        assert "<@&111>" in call_args.kwargs["content"]
        assert "<@&222>" in call_args.kwargs["content"]


class AsyncIteratorMock:
    """Mock for async iterators like channel.history()."""

    def __init__(self, items: list[Any]) -> None:  # noqa: D107
        self.items = items

    def __aiter__(self) -> "AsyncIteratorMock":  # noqa: D105
        self._index = 0
        return self

    async def __anext__(self) -> Any:  # noqa: D105
        if self._index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self._index]
        self._index += 1
        return item


class TestUpdateTrackerMessage:
    """Tests for update_tracker_message."""

    async def test_returns_early_when_channel_not_text_channel(self) -> None:
        """Test that returns early if channel is not TextChannel."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        # Return a VoiceChannel instead of TextChannel
        mock_voice_channel = MagicMock(spec=discord.VoiceChannel)
        mock_guild.get_channel = MagicMock(return_value=mock_voice_channel)

        mock_verification_service = MagicMock()
        mock_config_service = MagicMock()

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Pending Verifications",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
        }

        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

        # Should not call any service methods
        mock_verification_service.get_pending_for_guild.assert_not_called()

    async def test_fetches_existing_tracker_and_handles_not_found(self) -> None:
        """Test that handles NotFound when fetching existing tracker message."""
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([]))
        mock_tracker_msg = MagicMock()
        mock_tracker_msg.id = 9999
        mock_mod_channel.send = AsyncMock(return_value=mock_tracker_msg)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_request = MagicMock()
        mock_request.username = "TestUser"
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.mod_message_id = 12345
        mock_request.created_at = MagicMock()
        mock_request.created_at.timestamp = MagicMock(return_value=1234567890)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[mock_request])

        mock_config_service = MagicMock()
        mock_config_service.set_value = AsyncMock(return_value=(True, None))

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Pending Verifications",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,  # Existing tracker ID
        }

        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

        # Should have called set_value to clear the old tracker ID
        assert mock_config_service.set_value.call_count >= 1

    async def test_deletes_tracker_when_no_pending_requests(self) -> None:
        """Test that deletes tracker when there are no pending requests."""
        mock_tracker_message = MagicMock()
        mock_tracker_message.delete = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_tracker_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[])

        mock_config_service = MagicMock()
        mock_config_service.set_value = AsyncMock(return_value=(True, None))

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Pending Verifications",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,
        }

        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

        mock_tracker_message.delete.assert_called_once()

    async def test_handles_not_found_when_deleting_tracker(self) -> None:
        """Test that handles NotFound when deleting tracker."""
        mock_tracker_message = MagicMock()
        mock_tracker_message.delete = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_tracker_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[])

        mock_config_service = MagicMock()
        mock_config_service.set_value = AsyncMock(return_value=(True, None))

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Pending Verifications",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,
        }

        # Should not raise
        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

    async def test_repositions_tracker_when_not_last_message(self) -> None:
        """Test that repositions tracker when it is not the last message."""
        mock_tracker_message = MagicMock()
        mock_tracker_message.id = 888
        mock_tracker_message.delete = AsyncMock()

        # Last message is different from tracker
        mock_last_message = MagicMock()
        mock_last_message.id = 999

        mock_new_tracker = MagicMock()
        mock_new_tracker.id = 1000

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_tracker_message)
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([mock_last_message]))
        mock_mod_channel.send = AsyncMock(return_value=mock_new_tracker)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_request = MagicMock()
        mock_request.username = "TestUser"
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.mod_message_id = 12345
        mock_request.created_at = MagicMock()
        mock_request.created_at.timestamp = MagicMock(return_value=1234567890)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[mock_request])

        mock_config_service = MagicMock()
        mock_config_service.set_value = AsyncMock(return_value=(True, None))

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Pending Verifications",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,
        }

        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

        # Should delete old tracker and send new one
        mock_tracker_message.delete.assert_called_once()
        mock_mod_channel.send.assert_called_once()

    async def test_edits_existing_tracker_when_last_message(self) -> None:
        """Test that edits existing tracker when it is the last message."""
        mock_tracker_message = MagicMock()
        mock_tracker_message.id = 888
        mock_tracker_message.edit = AsyncMock()

        # Tracker is the last message
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_tracker_message)
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([mock_tracker_message]))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_request = MagicMock()
        mock_request.username = "TestUser"
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.mod_message_id = 12345
        mock_request.created_at = MagicMock()
        mock_request.created_at.timestamp = MagicMock(return_value=1234567890)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[mock_request])

        mock_config_service = MagicMock()

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Pending Verifications",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,
        }

        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

        mock_tracker_message.edit.assert_called_once()

    async def test_handles_not_found_when_editing_tracker(self) -> None:
        """Test that handles NotFound when editing tracker and creates a new one."""
        mock_tracker_message = MagicMock()
        mock_tracker_message.id = 888
        mock_tracker_message.edit = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        mock_new_tracker = MagicMock()
        mock_new_tracker.id = 1000

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_tracker_message)
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([mock_tracker_message]))
        mock_mod_channel.send = AsyncMock(return_value=mock_new_tracker)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_request = MagicMock()
        mock_request.username = "TestUser"
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.mod_message_id = 12345
        mock_request.created_at = MagicMock()
        mock_request.created_at.timestamp = MagicMock(return_value=1234567890)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[mock_request])

        mock_config_service = MagicMock()
        mock_config_service.set_value = AsyncMock(return_value=(True, None))

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Pending Verifications",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,
        }

        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

        # Should send new message after edit fails
        mock_mod_channel.send.assert_called_once()

    async def test_handles_forbidden_when_sending_tracker(self) -> None:
        """Test that handles Forbidden when sending new tracker."""
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.name = "mod-channel"
        mock_mod_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([]))
        mock_mod_channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_request = MagicMock()
        mock_request.username = "TestUser"
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.mod_message_id = 12345
        mock_request.created_at = MagicMock()
        mock_request.created_at.timestamp = MagicMock(return_value=1234567890)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[mock_request])

        mock_config_service = MagicMock()
        mock_config_service.set_value = AsyncMock(return_value=(True, None))

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Pending Verifications",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,
        }

        # Should not raise
        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )
