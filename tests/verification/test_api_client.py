"""Tests for discord_bot/verification/api_client.py."""

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from discord_bot.verification import api_client
from discord_bot.verification.api_client import call_verification_api
from discord_bot.verification.models import VerificationAPIResponse


class TestVerificationAPIResponse:
    """Tests for VerificationAPIResponse."""

    def test_model_validate_all_fields(self) -> None:
        """Test creation from dictionary with all fields."""
        data = {
            "name": "TestPlayer",
            "level": 25,
            "regiment": "TestRegiment",
            "faction": "colonial",
            "shard": "ABLE",
            "ingame_time": "268, 07:41",
            "war_number": 100,
            "current_ingame_time": "278, 08:34",
        }

        response = VerificationAPIResponse.model_validate(data)

        assert response.name == "TestPlayer"
        assert response.level == 25
        assert response.regiment == "TestRegiment"
        assert response.faction == "colonial"
        assert response.shard == "ABLE"
        assert response.ingame_time == "268, 07:41"
        assert response.war_number == 100
        assert response.current_ingame_time == "278, 08:34"

    def test_model_validate_missing_fields(self) -> None:
        """Test creation from dictionary with missing fields."""
        data = {
            "name": "TestPlayer",
        }

        response = VerificationAPIResponse.model_validate(data)

        assert response.name == "TestPlayer"
        assert response.level == 0
        assert response.regiment == ""
        assert response.faction == ""
        assert response.shard == ""
        assert response.ingame_time == ""
        assert response.war_number == 0
        assert response.current_ingame_time == ""

    def test_model_validate_empty(self) -> None:
        """Test creation from empty dictionary."""
        data: dict[str, object] = {}

        response = VerificationAPIResponse.model_validate(data)

        assert response.name == ""
        assert response.level == 0
        assert response.regiment == ""
        assert response.faction == ""
        assert response.shard == ""
        assert response.ingame_time == ""
        assert response.war_number == 0
        assert response.current_ingame_time == ""

    def test_model_validate_null_string_fields(self) -> None:
        """Test creation from dictionary with null string fields.

        The API may return null for string fields like regiment when
        the OCR could not extract the value. These should be coerced
        to empty strings.
        """
        data = {
            "name": None,
            "level": 10,
            "regiment": None,
            "faction": None,
            "shard": "ABLE",
            "ingame_time": None,
            "war_number": 100,
            "current_ingame_time": None,
        }

        response = VerificationAPIResponse.model_validate(data)

        assert response.name == ""
        assert response.level == 10
        assert response.regiment == ""
        assert response.faction == ""
        assert response.shard == "ABLE"
        assert response.ingame_time == ""
        assert response.war_number == 100
        assert response.current_ingame_time == ""


class CountingStream(httpx.AsyncByteStream):
    """Response body stream that counts how many bytes were actually served."""

    def __init__(self, total: int, chunk: int) -> None:
        """Initialize the stream.

        Args:
            total (int): Total body size in bytes.
            chunk (int): Chunk size per iteration.
        """
        self.total = total
        self.chunk = chunk
        self.sent = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """Yield chunks while counting the bytes handed to the client."""
        while self.sent < self.total:
            size = min(self.chunk, self.total - self.sent)
            self.sent += size
            yield b"x" * size


class TestCallVerificationApi:
    """Tests for call_verification_api."""

    @pytest.fixture(autouse=True)
    def _reset_shared_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Start each test without a cached shared client."""
        monkeypatch.setattr(api_client._shared_client, "_client", None)

    @pytest.mark.asyncio
    async def test_oversized_image_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that an image above the size cap fails without calling the API."""
        monkeypatch.setattr(api_client, "MAX_IMAGE_BYTES", 10)
        api_called = False

        def handler(request: httpx.Request) -> httpx.Response:
            """Serve an oversized image; the OCR API must not be hit."""
            nonlocal api_called
            if request.url.path.endswith(".png"):
                return httpx.Response(200, content=b"x" * 11)
            api_called = True
            return httpx.Response(200, json={"name": "X"})

        real_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=real_client
        ):
            result = await call_verification_api(
                url="https://api.example.com/verify",
                api_key=None,
                image1_url="https://cdn.discordapp.com/1.png",
                image2_url="https://cdn.discordapp.com/2.png",
            )

        assert result.success is False
        assert result.error_message is not None
        assert "too large" in result.error_message.lower()
        assert api_called is False

    @pytest.mark.asyncio
    async def test_oversized_body_is_not_fully_buffered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that a body past the size cap stops downloading at the limit.

        The whole point of the cap is memory: the download must abort as the
        limit is crossed instead of buffering the full body and only then
        measuring it.
        """
        monkeypatch.setattr(api_client, "MAX_IMAGE_BYTES", 1000)
        stream1 = CountingStream(total=100_000, chunk=100)
        stream2 = CountingStream(total=100_000, chunk=100)

        def handler(request: httpx.Request) -> httpx.Response:
            """Serve the two counting image bodies; the OCR API must not be hit."""
            if request.url.path == "/1.png":
                return httpx.Response(200, stream=stream1)
            if request.url.path == "/2.png":
                return httpx.Response(200, stream=stream2)
            raise AssertionError("API must not be called")

        real_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=real_client
        ):
            result = await call_verification_api(
                url="https://api.example.com/verify",
                api_key=None,
                image1_url="https://cdn.discordapp.com/1.png",
                image2_url="https://cdn.discordapp.com/2.png",
            )

        assert result.success is False
        assert result.error_message is not None
        assert "too large" in result.error_message.lower()
        # Each download must stop within a chunk of the cap, not read 100KB
        assert stream1.sent <= 2000
        assert stream2.sent <= 2000

    @pytest.mark.asyncio
    async def test_call_runs_under_semaphore(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that downloads and the API call happen while the semaphore is held."""
        monkeypatch.setattr(api_client, "_API_SEMAPHORE", asyncio.Semaphore(1))
        held: list[bool] = []

        def handler(request: httpx.Request) -> httpx.Response:
            """Record whether the semaphore is held while each image downloads."""
            if request.url.path.endswith(".png"):
                held.append(api_client._API_SEMAPHORE.locked())
                return httpx.Response(200, content=b"img")
            return httpx.Response(200, json={"name": "X"})

        real_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=real_client
        ):
            result = await call_verification_api(
                url="https://api.example.com/verify",
                api_key=None,
                image1_url="https://cdn.discordapp.com/1.png",
                image2_url="https://cdn.discordapp.com/2.png",
            )

        assert result.success is True
        assert held == [True, True]

    @pytest.mark.asyncio
    async def test_client_reused_across_calls(self) -> None:
        """Test that consecutive calls share one httpx client."""

        def handler(request: httpx.Request) -> httpx.Response:
            """Serve images and a minimal OCR API response."""
            if request.url.path.endswith(".png"):
                return httpx.Response(200, content=b"img")
            return httpx.Response(200, json={"name": "X"})

        real_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=real_client
        ) as constructor:
            for _ in range(2):
                await call_verification_api(
                    url="https://api.example.com/verify",
                    api_key=None,
                    image1_url="https://cdn.discordapp.com/1.png",
                    image2_url="https://cdn.discordapp.com/2.png",
                )

        assert constructor.call_count == 1

    @pytest.mark.asyncio
    async def test_close_client_closes_shared_client(self) -> None:
        """Test that close_client closes and clears the shared client."""
        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        api_client._shared_client._client = mock_client

        await api_client.close_client()

        mock_client.aclose.assert_awaited_once()
        assert not api_client._shared_client.is_open

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """Test successful API call."""

        def handler(request: httpx.Request) -> httpx.Response:
            """Serve both images and a full OCR API response."""
            if request.url.path.endswith(".png"):
                return httpx.Response(200, content=b"fake image data")
            return httpx.Response(
                200,
                json={
                    "name": "TestPlayer",
                    "level": 10,
                    "regiment": "",
                    "faction": "colonial",
                    "shard": "ABLE",
                    "ingame_time": "100, 00:00",
                    "war_number": 100,
                    "current_ingame_time": "100, 01:00",
                },
            )

        real_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=real_client
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

        def handler(request: httpx.Request) -> httpx.Response:
            """Fail the first image download with a 404."""
            if request.url.path == "/1.png":
                return httpx.Response(404)
            return httpx.Response(200, content=b"fake image data")

        real_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=real_client
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

        def handler(request: httpx.Request) -> httpx.Response:
            """Fail the second image download with a 403."""
            if request.url.path == "/2.png":
                return httpx.Response(403)
            return httpx.Response(200, content=b"fake image data")

        real_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=real_client
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

        def handler(request: httpx.Request) -> httpx.Response:
            """Serve the images but fail the OCR API call with a 422."""
            if request.url.path.endswith(".png"):
                return httpx.Response(200, content=b"fake image data")
            return httpx.Response(422, text="Invalid images")

        real_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=real_client
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

        def handler(request: httpx.Request) -> httpx.Response:
            """Simulate a network failure on every request."""
            raise httpx.ConnectError("Connection failed")

        real_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=real_client
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

        def handler(request: httpx.Request) -> httpx.Response:
            """Raise an unexpected error on every request."""
            raise ValueError("Unexpected error")

        real_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch(
            "discord_bot.verification.api_client.httpx.AsyncClient", return_value=real_client
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
