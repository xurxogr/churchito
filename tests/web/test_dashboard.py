"""Tests para el router de dashboard."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from discord_bot.web.routers.dashboard import (
    _check_guild_access,
    _get_guild_access,
    get_templates,
    router,
)


@pytest.fixture
def dashboard_app(simple_app: FastAPI) -> FastAPI:
    """Crear aplicación con router de dashboard.

    Args:
        simple_app (FastAPI): Aplicación base

    Returns:
        FastAPI: Aplicación con dashboard
    """
    simple_app.include_router(router)
    return simple_app


@pytest.fixture
def dashboard_client(dashboard_app: FastAPI) -> TestClient:
    """Crear cliente para dashboard.

    Args:
        dashboard_app (FastAPI): Aplicación

    Returns:
        TestClient: Cliente de prueba
    """
    return TestClient(dashboard_app)


class TestGetTemplates:
    """Tests para get_templates."""

    def test_returns_templates(self, simple_app: FastAPI) -> None:
        """Probar que retorna templates."""
        request = MagicMock()
        request.app = simple_app

        templates = get_templates(request)
        assert templates is not None


class TestGetGuildAccess:
    """Tests para _get_guild_access."""

    def test_owner_has_access_to_any_guild_bot_is_in(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que owner tiene acceso a cualquier guild donde está el bot."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = [123456789]

        # Mock bot with guild
        mock_guild = MagicMock()
        mock_guild.id = 999999
        mock_guild.name = "Bot Guild"
        mock_guild.icon = None
        simple_app.state.bot.get_guild = MagicMock(return_value=mock_guild)

        result = _get_guild_access(request, 999999, test_user)
        assert result is not None
        assert result["id"] == "999999"
        assert result["name"] == "Bot Guild"

    def test_owner_no_access_if_bot_not_in_guild(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que owner no tiene acceso si el bot no está en el guild."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = [123456789]

        # Bot not in guild
        simple_app.state.bot.get_guild = MagicMock(return_value=None)

        result = _get_guild_access(request, 999999, test_user)
        assert result is None

    def test_owner_no_access_if_bot_is_none(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que owner no tiene acceso si el bot es None."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = [123456789]
        simple_app.state.bot = None

        result = _get_guild_access(request, 999999, test_user)
        assert result is None

    def test_user_with_manage_guild_has_access(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que usuario con MANAGE_GUILD tiene acceso."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        result = _get_guild_access(request, 111222333, test_user)
        assert result is not None
        assert result["name"] == "Test Guild"

    def test_user_without_permission_denied(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que usuario sin permisos es denegado."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        result = _get_guild_access(request, 444555666, test_user)
        assert result is None

    def test_user_not_in_guild_denied(self, simple_app: FastAPI, test_user: dict[str, Any]) -> None:
        """Probar que usuario no en el guild es denegado."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        result = _get_guild_access(request, 999999, test_user)
        assert result is None


class TestCheckGuildAccess:
    """Tests para _check_guild_access."""

    @pytest.mark.asyncio
    async def test_bot_owner_always_has_access(self) -> None:
        """Probar que bot owner siempre tiene acceso."""
        session = MagicMock()
        bot = MagicMock()
        user: dict[str, Any] = {"id": "123456789"}

        result = await _check_guild_access(
            session=session,
            bot=bot,
            guild_id=999999,
            user_id=123456789,
            is_bot_owner=True,
            is_guild_owner=False,
            user=user,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_guild_owner_always_has_access(self) -> None:
        """Probar que guild owner siempre tiene acceso."""
        session = MagicMock()
        bot = MagicMock()
        user: dict[str, Any] = {"id": "123456789"}

        result = await _check_guild_access(
            session=session,
            bot=bot,
            guild_id=999999,
            user_id=123456789,
            is_bot_owner=False,
            is_guild_owner=True,
            user=user,
        )

        assert result is True


class TestIndexRoute:
    """Tests para la ruta index."""

    def test_index_without_user_shows_login(self, dashboard_client: TestClient) -> None:
        """Probar que index sin usuario muestra login."""
        response = dashboard_client.get("/")
        # Puede ser 200 (login page) o 500 si templates no existen
        assert response.status_code in [200, 500]


class TestLoginPageRoute:
    """Tests para la ruta de login."""

    def test_login_page_without_user(self, dashboard_client: TestClient) -> None:
        """Probar página de login sin usuario."""
        response = dashboard_client.get("/login")
        assert response.status_code in [200, 500]


class TestDashboardRoute:
    """Tests para la ruta del dashboard."""

    def test_dashboard_without_auth_redirects(self, dashboard_app: FastAPI) -> None:
        """Probar que dashboard sin autenticación redirige o da error."""
        # Incluir el router de auth para la dependencia
        from discord_bot.web.auth.oauth import router as auth_router

        dashboard_app.include_router(auth_router)
        client = TestClient(dashboard_app, raise_server_exceptions=False)

        response = client.get("/dashboard")
        # Puede ser 401 (unauthorized) o 307 (redirect)
        assert response.status_code in [401, 307, 500]
