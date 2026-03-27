"""Tests for OAuth."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from discord_bot.web.auth.oauth import router


@pytest.fixture
def oauth_app(simple_app: FastAPI) -> FastAPI:
    """Create application with OAuth router.

    Args:
        simple_app (FastAPI): Base application

    Returns:
        FastAPI: Application with OAuth
    """
    simple_app.include_router(router)
    return simple_app


@pytest.fixture
def oauth_client(oauth_app: FastAPI) -> TestClient:
    """Create client for OAuth.

    Args:
        oauth_app (FastAPI): Application

    Returns:
        TestClient: Test client
    """
    return TestClient(oauth_app)


class TestLogin:
    """Tests for the login endpoint."""

    def test_login_redirects_to_discord(self, oauth_client: TestClient) -> None:
        """Test that login redirects to Discord."""
        response = oauth_client.get("/auth/login", follow_redirects=False)

        assert response.status_code == 307
        assert "discord.com" in response.headers["location"]

    def test_login_without_client_id_fails(
        self, oauth_app: FastAPI, oauth_client: TestClient
    ) -> None:
        """Test that login fails without client_id."""
        oauth_app.state.settings.web.client_id = None

        response = oauth_client.get("/auth/login")
        assert response.status_code == 500


class TestCallback:
    """Tests for the callback endpoint."""

    def test_callback_with_error_redirects(self, oauth_client: TestClient) -> None:
        """Test that callback with error redirects to login."""
        response = oauth_client.get("/auth/callback?error=access_denied", follow_redirects=False)

        assert response.status_code == 307
        assert "error=oauth_denied" in response.headers["location"]

    def test_callback_without_code_redirects(self, oauth_client: TestClient) -> None:
        """Test that callback without code redirects to login."""
        response = oauth_client.get("/auth/callback", follow_redirects=False)

        assert response.status_code == 307
        assert "error=no_code" in response.headers["location"]

    def test_callback_with_invalid_state_redirects(self, oauth_client: TestClient) -> None:
        """Test that callback with invalid state redirects to login."""
        response = oauth_client.get(
            "/auth/callback?code=test&state=invalid", follow_redirects=False
        )

        assert response.status_code == 307
        assert "error=invalid_state" in response.headers["location"]


class TestLogout:
    """Tests for the logout endpoint."""

    def test_logout_clears_session(self, oauth_client: TestClient) -> None:
        """Test that logout clears the session."""
        response = oauth_client.get("/auth/logout", follow_redirects=False)

        assert response.status_code == 307
        assert response.headers["location"] == "/"


class TestCallbackStateValidation:
    """Tests for state validation in callback."""

    def test_callback_validates_state(self, oauth_client: TestClient) -> None:
        """Test that callback validates the state correctly."""
        # Without previous state in session, any state is invalid
        response = oauth_client.get(
            "/auth/callback?code=test&state=any_state", follow_redirects=False
        )
        assert response.status_code == 307
        assert "error=invalid_state" in response.headers["location"]

    def test_callback_missing_state_fails(self, oauth_client: TestClient) -> None:
        """Test that callback without state fails."""
        response = oauth_client.get("/auth/callback?code=test", follow_redirects=False)
        assert response.status_code == 307
        assert "error=invalid_state" in response.headers["location"]
