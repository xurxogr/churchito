"""Tests para las dependencias web."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException

from discord_bot.web.dependencies import (
    NotAuthenticatedException,
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
        with pytest.raises(NotAuthenticatedException):
            await require_auth(None)


class TestRequireGuildAccess:
    """Tests para require_guild_access."""

    def _setup_db_mock(self, simple_app: FastAPI, guild: Any = None, config: Any = None) -> None:
        """Configurar mock de base de datos para tests."""
        mock_session = AsyncMock()

        # Mock para Guild query
        guild_result = MagicMock()
        guild_result.scalar_one_or_none.return_value = guild

        # Mock para GuildConfig query
        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = config

        # execute returns different results based on call order
        mock_session.execute = AsyncMock(side_effect=[guild_result, config_result])

        # Setup async context manager
        simple_app.state.db_service.session.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        simple_app.state.db_service.session.return_value.__aexit__ = AsyncMock()

    async def test_owner_has_access(self, simple_app: FastAPI, test_user: dict[str, Any]) -> None:
        """Probar que el owner tiene acceso a cualquier guild."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = [123456789]

        result = await require_guild_access(request, 999999, test_user)
        assert result == test_user

    async def test_user_who_invited_bot_has_access(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que el usuario que invitó al bot tiene acceso."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        # Mock discord guild (bot is in guild)
        mock_discord_guild = MagicMock()
        mock_discord_guild.owner_id = 0  # User is not guild owner
        simple_app.state.bot.get_guild.return_value = mock_discord_guild

        # Mock DB guild with invited_by_id matching the user
        mock_db_guild = MagicMock()
        mock_db_guild.invited_by_id = 123456789  # Same as test_user id
        self._setup_db_mock(simple_app, guild=mock_db_guild)

        result = await require_guild_access(request, 111222333, test_user)
        assert result == test_user

    async def test_guild_owner_has_access(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que el owner del guild tiene acceso."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        # Mock discord guild where user is owner
        mock_discord_guild = MagicMock()
        mock_discord_guild.owner_id = 123456789  # User is guild owner
        simple_app.state.bot.get_guild.return_value = mock_discord_guild

        result = await require_guild_access(request, 111222333, test_user)
        assert result == test_user

    async def test_user_with_admin_role_has_access(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que usuario con rol de admin tiene acceso."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        # Mock guild and admin_roles config
        self._setup_db_mock(simple_app, guild=None, config=[999888777])

        # Mock bot to return member with matching role
        mock_member = MagicMock()
        mock_role = MagicMock()
        mock_role.id = 999888777
        mock_member.roles = [mock_role]

        mock_guild = MagicMock()
        mock_guild.owner_id = 0  # User is not guild owner
        mock_guild.get_member.return_value = mock_member

        simple_app.state.bot.get_guild.return_value = mock_guild

        result = await require_guild_access(request, 111222333, test_user)
        assert result == test_user

    async def test_user_without_permission_denied(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Probar que usuario sin permisos es denegado."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        # Mock empty database results
        self._setup_db_mock(simple_app, guild=None, config=None)
        simple_app.state.bot.get_guild.return_value = None

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
