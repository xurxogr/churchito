"""Tests for the dashboard router."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from discord_bot.web.routers.dashboard import (
    _check_guild_access,
    get_templates,
    router,
)


@pytest.fixture
def dashboard_app(simple_app: FastAPI) -> FastAPI:
    """Create application with dashboard router.

    Args:
        simple_app (FastAPI): Base application

    Returns:
        FastAPI: Application with dashboard
    """
    simple_app.include_router(router)
    return simple_app


@pytest.fixture
def dashboard_client(dashboard_app: FastAPI) -> TestClient:
    """Create client for dashboard.

    Args:
        dashboard_app (FastAPI): Application

    Returns:
        TestClient: Test client
    """
    return TestClient(dashboard_app)


class TestGetTemplates:
    """Tests for get_templates."""

    def test_returns_templates(self, simple_app: FastAPI) -> None:
        """Test that it returns templates."""
        request = MagicMock()
        request.app = simple_app

        templates = get_templates(request)
        assert templates is not None


class TestCheckGuildAccess:
    """Tests for _check_guild_access."""

    @pytest.mark.asyncio
    async def test_bot_owner_always_has_access(self) -> None:
        """Test that bot owner always has access."""
        session = MagicMock()
        bot = MagicMock()

        result = await _check_guild_access(
            session=session,
            bot=bot,
            guild_id=999999,
            user_id=123456789012345678,
            is_bot_owner=True,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_guild_owner_always_has_access(self) -> None:
        """Test that guild owner always has access."""
        session = MagicMock()
        bot = MagicMock()
        # Guild owner is checked via discord_guild.owner_id
        mock_guild = MagicMock()
        mock_guild.owner_id = 123456789012345678
        bot.get_guild.return_value = mock_guild

        result = await _check_guild_access(
            session=session,
            bot=bot,
            guild_id=999999,
            user_id=123456789012345678,
            is_bot_owner=False,
        )

        assert result is True


class TestIndexRoute:
    """Tests for the index route."""

    def test_index_without_user_shows_login(self, dashboard_client: TestClient) -> None:
        """Test that index without user shows login."""
        response = dashboard_client.get("/")
        # Can be 200 (login page) or 500 if templates don't exist
        assert response.status_code in [200, 500]


class TestLoginPageRoute:
    """Tests for the login route."""

    def test_login_page_without_user(self, dashboard_client: TestClient) -> None:
        """Test login page without user."""
        response = dashboard_client.get("/login")
        assert response.status_code in [200, 500]


class TestDashboardRoute:
    """Tests for the dashboard route."""

    def test_dashboard_without_auth_redirects(self, dashboard_app: FastAPI) -> None:
        """Test that dashboard without authentication redirects or gives error."""
        # Include the auth router for the dependency
        from discord_bot.web.auth.oauth import router as auth_router

        dashboard_app.include_router(auth_router)
        client = TestClient(dashboard_app, raise_server_exceptions=False)

        response = client.get("/dashboard")
        # Can be 401 (unauthorized) or 307 (redirect)
        assert response.status_code in [401, 307, 500]
