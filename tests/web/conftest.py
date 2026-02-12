"""Fixtures para tests del módulo web."""

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
    """Crear configuración web de prueba.

    Returns:
        WebSettings: Configuración web
    """
    return WebSettings(
        enabled=True,
        host="127.0.0.1",
        port=8000,
        secret_key="test_secret_key_for_testing",
        client_id="test_client_id",
        client_secret="test_client_secret",
        redirect_uri="http://localhost:8000/auth/callback",
        owner_ids=[123456789],
    )


@pytest.fixture
def test_app_settings(test_settings: AppSettings, web_settings: WebSettings) -> AppSettings:
    """Crear configuración de aplicación con web habilitado.

    Args:
        test_settings (AppSettings): Configuración base
        web_settings (WebSettings): Configuración web

    Returns:
        AppSettings: Configuración completa
    """
    test_settings.web = web_settings
    return test_settings


@pytest.fixture
def mock_db_service() -> MagicMock:
    """Crear servicio de base de datos mock.

    Returns:
        MagicMock: Mock del servicio de base de datos
    """
    service = MagicMock(spec=DatabaseService)
    session_mock = AsyncMock()
    session_mock.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_mock.__aexit__ = AsyncMock(return_value=None)
    service.session.return_value = session_mock
    return service


@pytest.fixture
def mock_bot() -> MagicMock:
    """Crear bot mock.

    Returns:
        MagicMock: Mock del bot
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
    """Crear usuario de prueba.

    Returns:
        dict[str, Any]: Datos del usuario
    """
    return {
        "id": "123456789",
        "username": "testuser",
        "avatar": None,
        "guilds": [
            {
                "id": "111222333",
                "name": "Test Guild",
                "icon": None,
                "permissions": str(0x20),  # MANAGE_GUILD
                "owner": False,
            },
            {
                "id": "444555666",
                "name": "Another Guild",
                "icon": None,
                "permissions": "0",
                "owner": False,
            },
        ],
    }


@pytest.fixture
def simple_app(
    test_app_settings: AppSettings,
    mock_db_service: MagicMock,
    mock_bot: MagicMock,
) -> FastAPI:
    """Crear aplicación FastAPI simple para tests.

    Args:
        test_app_settings (AppSettings): Configuración
        mock_db_service (MagicMock): Mock del servicio de base de datos
        mock_bot (MagicMock): Mock del bot

    Returns:
        FastAPI: Aplicación para tests
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
    else:
        app.state.templates = MagicMock()

    return app


@pytest.fixture
def client(simple_app: FastAPI) -> TestClient:
    """Crear cliente de prueba.

    Args:
        simple_app (FastAPI): Aplicación

    Returns:
        TestClient: Cliente de prueba
    """
    return TestClient(simple_app)
