"""Fixtures for web module tests."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from discord_bot.common.core import AppSettings
from discord_bot.common.core.settings.web import WebSettings
from discord_bot.common.services import DatabaseService


@pytest.fixture
def web_settings() -> WebSettings:
    """Create test web settings.

    Returns:
        WebSettings: Web settings
    """
    return WebSettings(
        enabled=True,
        host="127.0.0.1",
        port=8000,
        secret_key="test_secret_key_for_testing",
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="http://localhost:8000/auth/callback",
        owner_ids=[123456789012345678],  # Valid Discord snowflake
    )


@pytest.fixture
def test_app_settings(test_settings: AppSettings, web_settings: WebSettings) -> AppSettings:
    """Create application settings with web enabled.

    Args:
        test_settings (AppSettings): Base settings
        web_settings (WebSettings): Web settings

    Returns:
        AppSettings: Complete settings
    """
    test_settings.web = web_settings
    return test_settings


@pytest.fixture
def mock_db_service() -> MagicMock:
    """Create mock database service.

    Returns:
        MagicMock: Mock of the database service
    """
    service = MagicMock(spec=DatabaseService)
    session_mock = AsyncMock()
    session_mock.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_mock.__aexit__ = AsyncMock(return_value=None)
    service.session.return_value = session_mock
    return service


@pytest.fixture
def mock_bot() -> MagicMock:
    """Create mock bot.

    Returns:
        MagicMock: Mock of the bot
    """
    bot = MagicMock()
    bot.guilds = []
    bot.user = MagicMock()
    bot.user.name = "TestBot"
    bot.user.avatar = None
    bot.get_guild = MagicMock(return_value=None)
    return bot


@pytest.fixture
def test_user() -> dict[str, Any]:
    """Create test user.

    Returns:
        dict[str, Any]: User data (no guilds - stored in bot cache)
    """
    return {
        "id": "123456789012345678",  # Valid Discord snowflake
        "username": "testuser",
        "avatar": None,
    }


@pytest.fixture
def simple_app(
    test_app_settings: AppSettings,
    mock_db_service: MagicMock,
    mock_bot: MagicMock,
) -> FastAPI:
    """Create simple FastAPI application for tests.

    Args:
        test_app_settings (AppSettings): Settings
        mock_db_service (MagicMock): Mock of the database service
        mock_bot (MagicMock): Mock of the bot

    Returns:
        FastAPI: Application for tests
    """
    from pathlib import Path

    from fastapi.templating import Jinja2Templates

    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="test_secret",
        session_cookie="test_session",
    )

    app.state.settings = test_app_settings
    app.state.db_service = mock_db_service
    app.state.bot = mock_bot

    # Mock templates
    templates_dir = Path(__file__).parent.parent.parent / "discord_bot" / "web" / "templates"
    if templates_dir.exists():
        app.state.templates = Jinja2Templates(directory=str(templates_dir))
        # Register i18n globals for templates
        from discord_bot.i18n import get_i18n_service

        i18n = get_i18n_service()
        app.state.templates.env.globals["_"] = i18n.translate
        app.state.templates.env.globals["LANGUAGES"] = i18n.SUPPORTED_LANGUAGES
        app.state.i18n = i18n
    else:
        app.state.templates = MagicMock()

    return app


@pytest.fixture
def client(simple_app: FastAPI) -> TestClient:
    """Create test client.

    Args:
        simple_app (FastAPI): Application

    Returns:
        TestClient: Test client
    """
    return TestClient(simple_app)
