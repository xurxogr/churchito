"""Tests para las dependencias web."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException

from discord_bot.web.dependencies import (
    get_current_user,
    get_db_session,
    require_auth,
    require_guild_access,
)


class TestGetDbSession:
    """Tests para get_db_session."""

    async def test_yields_session(self, simple_app: FastAPI) -> None:
        """Probar que yield una sesión."""
        request = MagicMock()
        request.app = simple_app

        mock_session = AsyncMock()
        simple_app.state.db_service.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        simple_app.state.db_service.session.return_value.__aexit__ = AsyncMock()

        async for session in get_db_session(request):
            assert session == mock_session


class TestGetCurrentUser:
    """Tests para get_current_user."""

    async def test_returns_user_from_session(self, test_user: dict[str, Any]) -> None:
        """Probar que retorna el usuario de la sesión."""
        request = MagicMock()
        request.session = {"user": test_user}

        user = await get_current_user(request)
        assert user == test_user

    async def test_returns_none_when_no_user(self) -> None:
        """Probar que retorna None cuando no hay usuario."""
        request = MagicMock()
        request.session = {}

        user = await get_current_user(request)
        assert user is None


class TestRequireAuth:
    """Tests para require_auth."""

    async def test_returns_user_when_authenticated(self, test_user: dict[str, Any]) -> None:
        """Probar que retorna el usuario cuando está autenticado."""
        user = await require_auth(test_user)
        assert user == test_user

    async def test_raises_when_not_authenticated(self) -> None:
        """Probar que lanza excepción cuando no está autenticado."""
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(None)
        assert exc_info.value.status_code == 401


class TestRequireGuildAccess:
    """Tests para require_guild_access."""

    async def test_owner_has_access(self, simple_app: FastAPI, test_user: dict[str, Any]) -> None:
        """Probar que el owner tiene acceso a cualquier guild."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = [123456789]

        result = await require_guild_access(request, 999999, test_user)
        assert result == test_user

    async def test_user_with_manage_guild_has_access(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que usuario con MANAGE_GUILD tiene acceso."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        # El usuario tiene MANAGE_GUILD (0x20) para guild 111222333
        result = await require_guild_access(request, 111222333, test_user)
        assert result == test_user

    async def test_user_without_permission_denied(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que usuario sin permisos es denegado."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        # El usuario no tiene permisos para guild 444555666
        with pytest.raises(HTTPException) as exc_info:
            await require_guild_access(request, 444555666, test_user)
        assert exc_info.value.status_code == 403

    async def test_user_not_in_guild_denied(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que usuario no en el guild es denegado."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        with pytest.raises(HTTPException) as exc_info:
            await require_guild_access(request, 999999999, test_user)
        assert exc_info.value.status_code == 403
