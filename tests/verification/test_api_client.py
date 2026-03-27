"""Tests for discord_bot/verification/api_client.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from discord_bot.verification.api_client import (
    VerificationAPIResponse,
    call_verification_api,
)


class TestVerificationAPIResponse:
    """Tests for VerificationAPIResponse."""

    def test_from_dict_all_fields(self) -> None:
        """Test creation from dictionary with all fields."""
        data = {
            "name": "TestPlayer",
            "level": 25,
            "regiment": "TestRegiment",
            "faction": "colonial",
            "shard": "ABLE",
            "ingame_time": "268, 07:41",
            "war": 100,
            "current_ingame_time": "278, 08:34",
        }

        response = VerificationAPIResponse.from_dict(data)

        assert response.name == "TestPlayer"
        assert response.level == 25
        assert response.regiment == "TestRegiment"
        assert response.faction == "colonial"
        assert response.shard == "ABLE"
        assert response.ingame_time == "268, 07:41"
        assert response.war == 100
        assert response.current_ingame_time == "278, 08:34"

    def test_from_dict_missing_fields(self) -> None:
        """Test creation from dictionary with missing fields."""
        data = {
            "name": "TestPlayer",
        }

        response = VerificationAPIResponse.from_dict(data)

        assert response.name == "TestPlayer"
        assert response.level == 0
        assert response.regiment == ""
        assert response.faction == ""
        assert response.shard == ""
        assert response.ingame_time == ""
        assert response.war == 0
        assert response.current_ingame_time == ""

    def test_from_dict_empty(self) -> None:
        """Test creation from empty dictionary."""
        data: dict[str, object] = {}

        response = VerificationAPIResponse.from_dict(data)

        assert response.name == ""
        assert response.level == 0
        assert response.regiment == ""
        assert response.faction == ""
        assert response.shard == ""
        assert response.ingame_time == ""
        assert response.war == 0
        assert response.current_ingame_time == ""


class TestCallVerificationApi:
    """Tests for call_verification_api."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """Test successful API call."""
        mock_img_response = MagicMock()
        mock_img_response.status_code = 200
        mock_img_response.content = b"fake image data"

        mock_api_response = MagicMock()
        mock_api_response.status_code = 200
        mock_api_response.json.return_value = {
            "name": "TestPlayer",
            "level": 10,
            "regiment": "",
            "faction": "colonial",
            "shard": "ABLE",
            "ingame_time": "100, 00:00",
            "war": 100,
            "current_ingame_time": "100, 01:00",
        }

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_img_response)
        mock_client.post = AsyncMock(return_value=mock_api_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await call_verification_api(
                url="https://api.example.com/verify",
                api_key="test-key",
                image1_url="https://cdn.discordapp.com/1.png",
                image2_url="https://cdn.discordapp.com/2.png",
            )

        assert result.success is True
        assert result.status_code == 200
        assert result.response is not None
        assert result.response.name == "TestPlayer"

    @pytest.mark.asyncio
    async def test_image1_download_fails(self) -> None:
        """Test failure downloading image 1."""
        mock_img1_response = MagicMock()
        mock_img1_response.status_code = 404

        mock_img2_response = MagicMock()
        mock_img2_response.status_code = 200
        mock_img2_response.content = b"fake image data"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[mock_img1_response, mock_img2_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await call_verification_api(
                url="https://api.example.com/verify",
                api_key=None,
                image1_url="https://cdn.discordapp.com/1.png",
                image2_url="https://cdn.discordapp.com/2.png",
            )

        assert result.success is False
        assert result.status_code == 404
        assert result.error_message is not None
        assert "image 1" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_image2_download_fails(self) -> None:
        """Test failure downloading image 2."""
        mock_img1_response = MagicMock()
        mock_img1_response.status_code = 200
        mock_img1_response.content = b"fake image data"

        mock_img2_response = MagicMock()
        mock_img2_response.status_code = 403

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[mock_img1_response, mock_img2_response])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await call_verification_api(
                url="https://api.example.com/verify",
                api_key=None,
                image1_url="https://cdn.discordapp.com/1.png",
                image2_url="https://cdn.discordapp.com/2.png",
            )

        assert result.success is False
        assert result.status_code == 403
        assert result.error_message is not None
        assert "image 2" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_api_error_response(self) -> None:
        """Test API error response."""
        mock_img_response = MagicMock()
        mock_img_response.status_code = 200
        mock_img_response.content = b"fake image data"

        mock_api_response = MagicMock()
        mock_api_response.status_code = 422
        mock_api_response.text = "Invalid images"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_img_response)
        mock_client.post = AsyncMock(return_value=mock_api_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await call_verification_api(
                url="https://api.example.com/verify",
                api_key="test-key",
                image1_url="https://cdn.discordapp.com/1.png",
                image2_url="https://cdn.discordapp.com/2.png",
            )

        assert result.success is False
        assert result.status_code == 422
        assert result.error_message == "Invalid images"

    @pytest.mark.asyncio
    async def test_http_error(self) -> None:
        """Test HTTPError handling."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await call_verification_api(
                url="https://api.example.com/verify",
                api_key=None,
                image1_url="https://cdn.discordapp.com/1.png",
                image2_url="https://cdn.discordapp.com/2.png",
            )

        assert result.success is False
        assert result.status_code == 0
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
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=mock_client
        ):
            result = await call_verification_api(
                url="https://api.example.com/verify",
                api_key=None,
                image1_url="https://cdn.discordapp.com/1.png",
                image2_url="https://cdn.discordapp.com/2.png",
            )

        assert result.success is False
        assert result.status_code == 0
        assert result.error_message is not None
        assert "Unexpected error" in result.error_message
