"""Tests for web dependencies."""

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
    """Tests for get_db_session."""

    async def test_yields_session(self, simple_app: FastAPI) -> None:
        """Test that it yields a session."""
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
    """Tests for get_current_user."""

    async def test_returns_user_from_session(self, test_user: dict[str, Any]) -> None:
        """Test that it returns the user from session."""
        request = MagicMock()
        request.session = {"user": test_user}

        user = await get_current_user(request)
        assert user == test_user

    async def test_returns_none_when_no_user(self) -> None:
        """Test that it returns None when there is no user."""
        request = MagicMock()
        request.session = {}

        user = await get_current_user(request)
        assert user is None


class TestRequireAuth:
    """Tests for require_auth."""

    async def test_returns_user_when_authenticated(self, test_user: dict[str, Any]) -> None:
        """Test that it returns the user when authenticated."""
        user = await require_auth(test_user)
        assert user == test_user

    async def test_raises_when_not_authenticated(self) -> None:
        """Test that it raises exception when not authenticated."""
        with pytest.raises(NotAuthenticatedException):
            await require_auth(None)


class TestRequireGuildAccess:
    """Tests for require_guild_access."""

    def _setup_db_mock(self, simple_app: FastAPI, guild: Any = None, config: Any = None) -> None:
        """Configure database mock for tests."""
        mock_session = AsyncMock()

        # Mock for Guild query
        guild_result = MagicMock()
        guild_result.scalar_one_or_none.return_value = guild

        # Mock for GuildConfig query
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
        """Test that owner has access to any guild."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = [123456789012345678]

        result = await require_guild_access(request, 999999, test_user)
        assert result == test_user

    async def test_user_who_invited_bot_has_access(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Test that user who invited the bot has access."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        # Mock discord guild (bot is in guild)
        mock_discord_guild = MagicMock()
        mock_discord_guild.owner_id = 0  # User is not guild owner
        simple_app.state.bot.get_guild.return_value = mock_discord_guild

        # Mock DB guild with invited_by_id matching the user
        mock_db_guild = MagicMock()
        mock_db_guild.invited_by_id = 123456789012345678  # Same as test_user id
        self._setup_db_mock(simple_app, guild=mock_db_guild)

        result = await require_guild_access(request, 111222333, test_user)
        assert result == test_user

    async def test_guild_owner_has_access(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Test that guild owner has access."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        # Mock discord guild where user is owner
        mock_discord_guild = MagicMock()
        mock_discord_guild.owner_id = 123456789012345678  # User is guild owner
        simple_app.state.bot.get_guild.return_value = mock_discord_guild

        result = await require_guild_access(request, 111222333, test_user)
        assert result == test_user

    async def test_user_with_admin_role_has_access(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Test that user with admin role has access."""
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
        """Test that user without permissions is denied."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        # Mock empty database results
        self._setup_db_mock(simple_app, guild=None, config=None)
        simple_app.state.bot.get_guild.return_value = None

        # User does not have permissions for guild 444555666
        with pytest.raises(HTTPException) as exc_info:
            await require_guild_access(request, 444555666, test_user)
        assert exc_info.value.status_code == 403

    async def test_user_not_in_guild_denied(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Test that user not in guild is denied."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = []

        with pytest.raises(HTTPException) as exc_info:
            await require_guild_access(request, 999999999, test_user)
        assert exc_info.value.status_code == 403
