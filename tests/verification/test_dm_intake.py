"""Tests for the pure helpers behind handle_dm_screenshots."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from discord_bot.verification.api_client import MAX_IMAGE_BYTES
from discord_bot.verification.enums import ConfigKey
from discord_bot.verification.handlers.dm_intake import (
    IntakeContext,
    _reply,
    _send_not_found,
    ack_key,
    image_attachments_of,
    reminder_key,
    requirements_met,
)


def _attachment(content_type: str | None, size: int = 1024) -> MagicMock:
    """Build an attachment mock.

    Args:
        content_type (str | None): Attachment content type.
        size (int): Attachment size in bytes. Defaults to 1024.

    Returns:
        MagicMock: Attachment mock.
    """
    attachment = MagicMock()
    attachment.content_type = content_type
    attachment.size = size
    return attachment


def _request(screenshot_1: str | None, screenshot_2: str | None, steam: str | None) -> MagicMock:
    """Build a verification request mock.

    Args:
        screenshot_1 (str | None): First screenshot URL.
        screenshot_2 (str | None): Second screenshot URL.
        steam (str | None): Steam profile URL.

    Returns:
        MagicMock: Request mock.
    """
    request = MagicMock()
    request.screenshot_1_url = screenshot_1
    request.screenshot_2_url = screenshot_2
    request.steam_profile_url = steam
    return request


class TestImageAttachmentsOf:
    """Only image attachments are considered screenshots."""

    def test_filters_non_images_and_missing_content_type(self) -> None:
        """PNG/JPEG attachments are kept; text files and untyped ones are dropped."""
        png = _attachment("image/png")
        jpeg = _attachment("image/jpeg")
        message = MagicMock()
        message.attachments = [png, _attachment("text/plain"), jpeg, _attachment(None)]

        assert image_attachments_of(message) == [png, jpeg]

    def test_drops_images_larger_than_the_api_limit(self) -> None:
        """An oversized screenshot would be rejected after downloading it whole."""
        small = _attachment("image/png")
        huge = _attachment("image/png", size=MAX_IMAGE_BYTES + 1)
        at_limit = _attachment("image/jpeg", size=MAX_IMAGE_BYTES)
        message = MagicMock()
        message.attachments = [huge, small, at_limit]

        assert image_attachments_of(message) == [small, at_limit]


class TestReminderKey:
    """Reminder when the DM contained nothing new."""

    def test_missing_screenshots_reminds_images(self) -> None:
        """Without screenshots the images message is used."""
        assert (
            reminder_key(screenshots_saved=False, steam_required=True, steam_saved=False)
            == ConfigKey.WRONG_IMAGES_MESSAGE
        )

    def test_missing_steam_reminds_steam(self) -> None:
        """With screenshots but a pending Steam URL the Steam message is used."""
        assert (
            reminder_key(screenshots_saved=True, steam_required=True, steam_saved=False)
            == ConfigKey.STEAM_URL_RECEIVED_MESSAGE
        )

    def test_nothing_pending_returns_none(self) -> None:
        """When everything is already saved there is nothing to remind."""
        assert reminder_key(screenshots_saved=True, steam_required=False, steam_saved=False) is None
        assert reminder_key(screenshots_saved=True, steam_required=True, steam_saved=True) is None


class TestAckKey:
    """Acknowledgment for a partial submission."""

    def test_screenshots_first_awaits_steam(self) -> None:
        """Screenshots received first → awaiting Steam URL message."""
        assert (
            ack_key(completed_screenshots=True)
            == ConfigKey.SCREENSHOTS_RECEIVED_AWAITING_STEAM_MESSAGE
        )

    def test_steam_first_acknowledges_url(self) -> None:
        """Steam URL received first → Steam URL received message."""
        assert ack_key(completed_screenshots=False) == ConfigKey.STEAM_URL_RECEIVED_MESSAGE


class TestRequirementsMet:
    """Both screenshots, plus the Steam URL when required."""

    def test_screenshots_only_when_steam_not_required(self) -> None:
        """Two screenshots suffice when Steam is optional."""
        assert requirements_met(request=_request("a", "b", None), steam_required=False)
        assert not requirements_met(request=_request("a", None, None), steam_required=False)

    def test_steam_needed_when_required(self) -> None:
        """Steam URL is mandatory when configured as required."""
        assert not requirements_met(request=_request("a", "b", None), steam_required=True)
        assert requirements_met(request=_request("a", "b", "https://s"), steam_required=True)


def _intake_ctx(config: dict[str, Any]) -> IntakeContext:
    """Build an intake context with a mocked DM channel.

    Args:
        config (dict[str, Any]): Cog configuration.

    Returns:
        IntakeContext: Context whose ``message.channel.send`` is an AsyncMock.
    """
    message = MagicMock()
    message.author.name = "TestUser"
    message.channel.send = AsyncMock()
    return IntakeContext(
        cog=MagicMock(),
        message=message,
        guild=MagicMock(),
        guild_name="Test Guild",
        config=config,
        session=MagicMock(),
        verification_service=MagicMock(),
        config_service=MagicMock(),
    )


class TestReplySkipsEmptyMessages:
    """Cleared dashboard messages must not crash the intake with empty sends."""

    async def test_cleared_reply_message_sends_nothing(self) -> None:
        """A message cleared in the dashboard (stored as "") is not sent."""
        ctx = _intake_ctx(config={ConfigKey.SCREENSHOTS_RECEIVED_MESSAGE: ""})

        await _reply(ctx=ctx, key=ConfigKey.SCREENSHOTS_RECEIVED_MESSAGE, server_name="Test Guild")

        ctx.message.channel.send.assert_not_called()

    async def test_configured_reply_message_is_sent(self) -> None:
        """A configured message is formatted and sent."""
        ctx = _intake_ctx(config={ConfigKey.SCREENSHOTS_RECEIVED_MESSAGE: "Thanks {username}!"})

        await _reply(ctx=ctx, key=ConfigKey.SCREENSHOTS_RECEIVED_MESSAGE)

        ctx.message.channel.send.assert_awaited_once_with(content="Thanks TestUser!")

    async def test_cleared_not_found_message_sends_nothing(self) -> None:
        """A cleared (or missing) not-found message is not sent."""
        ctx = _intake_ctx(config={ConfigKey.REQUEST_NOT_FOUND_MESSAGE: ""})

        await _send_not_found(ctx)

        ctx.message.channel.send.assert_not_called()

    async def test_configured_not_found_message_is_sent(self) -> None:
        """A configured not-found message is sent as-is."""
        ctx = _intake_ctx(config={ConfigKey.REQUEST_NOT_FOUND_MESSAGE: "Not found."})

        await _send_not_found(ctx)

        ctx.message.channel.send.assert_awaited_once_with(content="Not found.")
