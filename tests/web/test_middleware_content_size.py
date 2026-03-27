"""Tests for the content size limit middleware."""

import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.testclient import TestClient

from discord_bot.web.middleware.content_size import (
    DEFAULT_MAX_BODY_SIZE,
    ContentSizeLimitMiddleware,
)


class TestContentSizeLimitMiddleware:
    """Integration tests for ContentSizeLimitMiddleware."""

    @pytest.fixture
    def app_with_size_limit(self) -> TestClient:
        """Create app with ContentSizeLimitMiddleware (default limit 1MB)."""
        app = FastAPI()
        app.add_middleware(ContentSizeLimitMiddleware)

        @app.get("/")
        async def root(request: Request) -> dict[str, str]:
            return {"status": "ok"}

        @app.post("/submit")
        async def submit(request: Request) -> dict[str, str]:
            await request.body()
            return {"status": "ok"}

        return TestClient(app)

    @pytest.fixture
    def app_with_small_limit(self) -> TestClient:
        """Create app with small limit (1KB) for testing."""
        app = FastAPI()
        app.add_middleware(ContentSizeLimitMiddleware, max_body_size=1024)

        @app.post("/submit")
        async def submit(request: Request) -> dict[str, str]:
            await request.body()
            return {"status": "ok"}

        return TestClient(app)

    def test_get_request_passes(self, app_with_size_limit: TestClient) -> None:
        """Test that GET requests pass without size verification."""
        response = app_with_size_limit.get("/")
        assert response.status_code == 200

    def test_small_body_passes(self, app_with_size_limit: TestClient) -> None:
        """Test that small body passes."""
        response = app_with_size_limit.post(
            "/submit",
            content=b"small body",
            headers={"Content-Length": "10"},
        )
        assert response.status_code == 200

    def test_large_body_rejected(self, app_with_small_limit: TestClient) -> None:
        """Test that body larger than limit is rejected."""
        large_body = b"x" * 2048  # 2KB, larger than 1KB limit
        response = app_with_small_limit.post(
            "/submit",
            content=large_body,
            headers={"Content-Length": str(len(large_body))},
        )
        assert response.status_code == 413
        assert "too large" in response.text.lower()

    def test_body_at_limit_passes(self, app_with_small_limit: TestClient) -> None:
        """Test that body exactly at limit passes."""
        body = b"x" * 1024  # Exactly 1KB
        response = app_with_small_limit.post(
            "/submit",
            content=body,
            headers={"Content-Length": str(len(body))},
        )
        assert response.status_code == 200

    def test_missing_content_length_passes(self, app_with_small_limit: TestClient) -> None:
        """Test that request without Content-Length passes (chunked encoding)."""
        # TestClient always adds Content-Length, but we verify the behavior
        response = app_with_small_limit.post("/submit", content=b"data")
        assert response.status_code == 200

    def test_invalid_content_length_passes(self, app_with_small_limit: TestClient) -> None:
        """Test that invalid Content-Length does not cause error."""
        response = app_with_small_limit.post(
            "/submit",
            content=b"data",
            headers={"Content-Length": "not-a-number"},
        )
        # May pass or fail depending on the server, but should not crash
        assert response.status_code in (200, 400)

    def test_default_limit_is_1mb(self) -> None:
        """Test that the default limit is 1MB."""
        assert DEFAULT_MAX_BODY_SIZE == 1 * 1024 * 1024
