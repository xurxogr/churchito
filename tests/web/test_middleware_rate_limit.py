"""Tests for the rate limiting middleware."""

import time
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

from discord_bot.web.middleware.rate_limit import RateLimitMiddleware, RateLimitState


class TestRateLimitState:
    """Tests for RateLimitState."""

    def test_clean_old_requests(self) -> None:
        """Test cleaning old requests."""
        state = RateLimitState()
        now = time.time()

        # Add requests: some old, some new
        state.requests = [now - 120, now - 90, now - 30, now - 10]

        state.clean_old_requests(window_seconds=60)

        # Only requests from the last 60 seconds should remain
        assert len(state.requests) == 2

    def test_is_limited_under_limit(self) -> None:
        """Test that it is not limited when under the limit."""
        state = RateLimitState()
        now = time.time()
        state.requests = [now - 10, now - 5]

        assert state.is_limited(max_requests=5, window_seconds=60) is False

    def test_is_limited_at_limit(self) -> None:
        """Test that it is limited when reaching the limit."""
        state = RateLimitState()
        now = time.time()
        state.requests = [now - 10, now - 8, now - 6, now - 4, now - 2]

        assert state.is_limited(max_requests=5, window_seconds=60) is True

    def test_add_request(self) -> None:
        """Test that it adds a request."""
        state = RateLimitState()
        assert len(state.requests) == 0

        state.add_request()

        assert len(state.requests) == 1
        assert state.requests[0] <= time.time()


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware."""

    def test_get_client_ip_from_forwarded_for(self) -> None:
        """Test getting IP from X-Forwarded-For."""
        middleware = RateLimitMiddleware(MagicMock())
        request = MagicMock(spec=Request)
        request.headers = {"x-forwarded-for": "192.168.1.1, 10.0.0.1"}
        request.client = None

        ip = middleware._get_client_ip(request)

        assert ip == "192.168.1.1"

    def test_get_client_ip_from_real_ip(self) -> None:
        """Test getting IP from X-Real-IP."""
        middleware = RateLimitMiddleware(MagicMock())
        request = MagicMock(spec=Request)
        request.headers = {"x-real-ip": "192.168.1.2"}
        request.client = None

        ip = middleware._get_client_ip(request)

        assert ip == "192.168.1.2"

    def test_get_client_ip_from_client(self) -> None:
        """Test getting IP from client."""
        middleware = RateLimitMiddleware(MagicMock())
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.3"

        ip = middleware._get_client_ip(request)

        assert ip == "192.168.1.3"

    def test_get_client_ip_fallback(self) -> None:
        """Test fallback to 'unknown' when there is no IP."""
        middleware = RateLimitMiddleware(MagicMock())
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = None

        ip = middleware._get_client_ip(request)

        assert ip == "unknown"

    def test_get_path_pattern_normalizes_guild_routes(self) -> None:
        """Test normalization of guild routes."""
        middleware = RateLimitMiddleware(MagicMock())

        pattern = middleware._get_path_pattern("/guild/123/cog/test/toggle")

        assert pattern == "/guild/*/cog/*/toggle"

    def test_get_path_pattern_preserves_other_routes(self) -> None:
        """Test that other routes are not modified."""
        middleware = RateLimitMiddleware(MagicMock())

        pattern = middleware._get_path_pattern("/auth/login")

        assert pattern == "/auth/login"

    def test_get_limit_for_auth_login(self) -> None:
        """Test limit for /auth/login."""
        middleware = RateLimitMiddleware(MagicMock())

        limit = middleware._get_limit("/auth/login", "GET")

        assert limit == (10, 60)

    def test_get_limit_for_post_guild(self) -> None:
        """Test default limit for POST on guild."""
        middleware = RateLimitMiddleware(MagicMock())

        limit = middleware._get_limit("/guild/123/cog/test/toggle", "POST")

        assert limit == (30, 60)

    def test_get_limit_returns_none_for_unprotected(self) -> None:
        """Test that it returns None for routes without limit."""
        middleware = RateLimitMiddleware(MagicMock())

        limit = middleware._get_limit("/dashboard", "GET")

        assert limit is None

    def test_periodic_cleanup_removes_old_states(self) -> None:
        """Test that periodic cleanup removes old states."""
        middleware = RateLimitMiddleware(MagicMock())

        # Add state with old requests
        state = RateLimitState()
        state.requests = [time.time() - 700]  # More than 10 minutes
        middleware._state[("192.168.1.1", "/auth/login")] = state

        # Force cleanup by setting _last_cleanup more than 5 minutes ago
        middleware._last_cleanup = time.time() - 400

        middleware._periodic_cleanup()

        # The state should have been removed
        assert ("192.168.1.1", "/auth/login") not in middleware._state

    def test_periodic_cleanup_keeps_recent_states(self) -> None:
        """Test that periodic cleanup keeps recent states."""
        middleware = RateLimitMiddleware(MagicMock())

        # Add state with recent requests
        state = RateLimitState()
        state.requests = [time.time() - 30]  # 30 seconds
        middleware._state[("192.168.1.1", "/auth/login")] = state

        # Force cleanup
        middleware._last_cleanup = time.time() - 400

        middleware._periodic_cleanup()

        # The state should be kept
        assert ("192.168.1.1", "/auth/login") in middleware._state


class TestRateLimitMiddlewareIntegration:
    """Integration tests for RateLimitMiddleware."""

    @pytest.fixture
    def app_with_rate_limit(self) -> TestClient:
        """Create app with rate limit middleware for testing."""
        from fastapi import FastAPI

        from discord_bot.web.middleware.rate_limit import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware)

        @app.get("/auth/login")
        async def login() -> dict[str, str]:
            return {"status": "ok"}

        @app.post("/guild/123/cog/test/toggle")
        async def toggle() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/unprotected")
        async def unprotected() -> dict[str, str]:
            return {"status": "ok"}

        return TestClient(app)

    def test_allows_requests_under_limit(self, app_with_rate_limit: TestClient) -> None:
        """Test that it allows requests under the limit."""
        for _ in range(5):
            response = app_with_rate_limit.get("/auth/login")
            assert response.status_code == 200

    def test_blocks_requests_over_limit(self, app_with_rate_limit: TestClient) -> None:
        """Test that it blocks requests over the limit."""
        # Make 10 requests (the limit)
        for _ in range(10):
            app_with_rate_limit.get("/auth/login")

        # The next one should be blocked
        response = app_with_rate_limit.get("/auth/login")
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_unprotected_routes_not_limited(self, app_with_rate_limit: TestClient) -> None:
        """Test that routes without limit are not affected."""
        for _ in range(50):
            response = app_with_rate_limit.get("/unprotected")
            assert response.status_code == 200
