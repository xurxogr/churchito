"""Tests for the security headers middleware."""

import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.testclient import TestClient

from discord_bot.web.middleware.security_headers import (
    DEFAULT_CSP,
    DEFAULT_HSTS,
    SecurityHeadersMiddleware,
)


class TestSecurityHeadersMiddleware:
    """Integration tests for SecurityHeadersMiddleware."""

    @pytest.fixture
    def app_with_security_headers(self) -> TestClient:
        """Create app with SecurityHeadersMiddleware (https_only=True)."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, https_only=True)

        @app.get("/")
        async def root(request: Request) -> dict[str, str]:
            return {"status": "ok"}

        @app.post("/submit")
        async def submit() -> dict[str, str]:
            return {"status": "ok"}

        return TestClient(app)

    @pytest.fixture
    def app_without_hsts(self) -> TestClient:
        """Create app with SecurityHeadersMiddleware (https_only=False)."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, https_only=False)

        @app.get("/")
        async def root(request: Request) -> dict[str, str]:
            return {"status": "ok"}

        return TestClient(app)

    def test_x_frame_options_header(self, app_with_security_headers: TestClient) -> None:
        """Test that X-Frame-Options is present."""
        response = app_with_security_headers.get("/")
        assert response.status_code == 200
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_x_content_type_options_header(self, app_with_security_headers: TestClient) -> None:
        """Test that X-Content-Type-Options is present."""
        response = app_with_security_headers.get("/")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_referrer_policy_header(self, app_with_security_headers: TestClient) -> None:
        """Test that Referrer-Policy is present."""
        response = app_with_security_headers.get("/")
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_content_security_policy_header(self, app_with_security_headers: TestClient) -> None:
        """Test that Content-Security-Policy is present."""
        response = app_with_security_headers.get("/")
        assert response.headers.get("Content-Security-Policy") == DEFAULT_CSP

    def test_hsts_header_when_https_only(self, app_with_security_headers: TestClient) -> None:
        """Test that HSTS is present when https_only=True."""
        response = app_with_security_headers.get("/")
        assert response.headers.get("Strict-Transport-Security") == DEFAULT_HSTS

    def test_no_hsts_header_when_not_https_only(self, app_without_hsts: TestClient) -> None:
        """Test that HSTS is not present when https_only=False."""
        response = app_without_hsts.get("/")
        assert response.headers.get("Strict-Transport-Security") is None

    def test_headers_present_on_post(self, app_with_security_headers: TestClient) -> None:
        """Test that headers are present in POST responses."""
        response = app_with_security_headers.post("/submit")
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("Content-Security-Policy") == DEFAULT_CSP

    def test_csp_allows_all_images(self, app_with_security_headers: TestClient) -> None:
        """Test that CSP allows images from any source (img-src *)."""
        response = app_with_security_headers.get("/")
        csp = response.headers.get("Content-Security-Policy", "")
        assert "img-src *" in csp

    def test_csp_prevents_framing(self, app_with_security_headers: TestClient) -> None:
        """Test that CSP prevents framing."""
        response = app_with_security_headers.get("/")
        csp = response.headers.get("Content-Security-Policy", "")
        assert "frame-ancestors 'none'" in csp
