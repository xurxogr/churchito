"""Tests for discord_bot/verification/steam_client.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from discord_bot.verification.steam_client import (
    check_steam_profile_private,
    is_valid_steam_profile_url,
)


class TestIsValidSteamProfileUrl:
    """Tests for is_valid_steam_profile_url."""

    def test_valid_id_url(self) -> None:
        """Test valid vanity /id/ URL."""
        assert is_valid_steam_profile_url("https://steamcommunity.com/id/someuser") is True

    def test_valid_id_url_trailing_slash(self) -> None:
        """Test valid vanity /id/ URL with trailing slash."""
        assert is_valid_steam_profile_url("https://steamcommunity.com/id/someuser/") is True

    def test_valid_profiles_url(self) -> None:
        """Test valid /profiles/<id64> URL."""
        assert (
            is_valid_steam_profile_url("https://steamcommunity.com/profiles/76561198000000000")
            is True
        )

    def test_empty_url(self) -> None:
        """Test empty URL is rejected."""
        assert is_valid_steam_profile_url("") is False

    def test_http_not_https(self) -> None:
        """Test plain http is rejected."""
        assert is_valid_steam_profile_url("http://steamcommunity.com/id/someuser") is False

    def test_wrong_domain(self) -> None:
        """Test wrong domain is rejected."""
        assert is_valid_steam_profile_url("https://evil.com/id/someuser") is False

    def test_subdomain_trick(self) -> None:
        """Test subdomain trick is rejected."""
        assert (
            is_valid_steam_profile_url("https://steamcommunity.com.evil.com/id/someuser") is False
        )

    def test_userinfo_trick(self) -> None:
        """Test userinfo trick is rejected."""
        assert (
            is_valid_steam_profile_url("https://steamcommunity.com@evil.com/id/someuser") is False
        )

    def test_profiles_short_id(self) -> None:
        """Test profiles path requires a 17-digit id64."""
        assert is_valid_steam_profile_url("https://steamcommunity.com/profiles/123") is False

    def test_other_path(self) -> None:
        """Test unrelated paths are rejected."""
        assert is_valid_steam_profile_url("https://steamcommunity.com/groups/somegroup") is False


class TestCheckSteamProfilePrivate:
    """Tests for check_steam_profile_private."""

    @pytest.mark.asyncio
    async def test_invalid_url_rejected(self) -> None:
        """Test invalid URLs are rejected without making a request."""
        result = await check_steam_profile_private(url="https://evil.com/id/someuser")

        assert result.success is False
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_public_profile(self) -> None:
        """Test public profile detection."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<profile><privacyState>public</privacyState></profile>"
        mock_response.url = MagicMock()
        mock_response.url.host = "steamcommunity.com"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.steam_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await check_steam_profile_private(url="https://steamcommunity.com/id/someuser")

        assert result.success is True
        assert result.is_private is False

    @pytest.mark.asyncio
    async def test_private_profile(self) -> None:
        """Test private profile detection."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<profile><privacyState>private</privacyState></profile>"
        mock_response.url = MagicMock()
        mock_response.url.host = "steamcommunity.com"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.steam_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await check_steam_profile_private(url="https://steamcommunity.com/id/someuser")

        assert result.success is True
        assert result.is_private is True

    @pytest.mark.asyncio
    async def test_redirect_off_domain_rejected(self) -> None:
        """Test that a redirect landing off the allowed domain is rejected."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<profile><privacyState>public</privacyState></profile>"
        mock_response.url = MagicMock()
        mock_response.url.host = "evil.com"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.steam_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await check_steam_profile_private(url="https://steamcommunity.com/id/someuser")

        assert result.success is False
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_redirect_to_off_domain_never_followed(self) -> None:
        """Test a redirect Location header pointing off-domain is rejected before following it."""
        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.url = httpx.URL("https://steamcommunity.com/id/someuser/?xml=1")
        redirect_response.headers = {"location": "https://evil.com/internal"}

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=redirect_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.steam_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await check_steam_profile_private(url="https://steamcommunity.com/id/someuser")

        assert result.success is False
        assert result.error_message is not None
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_too_many_redirects_rejected(self) -> None:
        """Test that exceeding the redirect limit is rejected."""
        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.url = httpx.URL("https://steamcommunity.com/id/someuser/?xml=1")
        redirect_response.headers = {"location": "https://steamcommunity.com/id/someuser/?xml=1"}

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=redirect_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.steam_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await check_steam_profile_private(url="https://steamcommunity.com/id/someuser")

        assert result.success is False
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_malformed_response(self) -> None:
        """Test malformed response without privacyState."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<profile></profile>"
        mock_response.url = MagicMock()
        mock_response.url.host = "steamcommunity.com"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.steam_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await check_steam_profile_private(url="https://steamcommunity.com/id/someuser")

        assert result.success is False
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_http_status_error(self) -> None:
        """Test non-200 HTTP response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.url = MagicMock()
        mock_response.url.host = "steamcommunity.com"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.steam_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await check_steam_profile_private(url="https://steamcommunity.com/id/someuser")

        assert result.success is False
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_http_error(self) -> None:
        """Test HTTPError handling."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.steam_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await check_steam_profile_private(url="https://steamcommunity.com/id/someuser")

        assert result.success is False
        assert result.error_message is not None
        assert "Connection failed" in result.error_message

    @pytest.mark.asyncio
    async def test_unexpected_error(self) -> None:
        """Test unexpected error handling."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ValueError("Unexpected error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.steam_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await check_steam_profile_private(url="https://steamcommunity.com/id/someuser")

        assert result.success is False
        assert result.error_message is not None
        assert "Unexpected error" in result.error_message
