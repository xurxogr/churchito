"""Tests for the pure helpers behind handle_dm_screenshots."""

from unittest.mock import MagicMock

from discord_bot.verification.enums import ConfigKey
from discord_bot.verification.handlers.dm_intake import (
    ack_key,
    image_attachments_of,
    reminder_key,
    requirements_met,
)


def _attachment(content_type: str | None) -> MagicMock:
    """Build an attachment mock.

    Args:
        content_type (str | None): Attachment content type.

    Returns:
        MagicMock: Attachment mock.
    """
    attachment = MagicMock()
    attachment.content_type = content_type
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
