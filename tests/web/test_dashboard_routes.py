"""Tests para las rutas del dashboard."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from discord_bot.web.routers.dashboard import _check_guild_access, dashboard, index, login_page


class TestDashboardRoutes:
    """Tests para rutas del dashboard."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        # Mock execute to return empty results by default
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)
        return session

    @pytest.fixture
    def mock_request_with_user(self, simple_app: FastAPI, test_user: dict[str, Any]) -> MagicMock:
        """Crear request mock con usuario.

        Args:
            simple_app (FastAPI): Aplicación
            test_user (dict[str, Any]): Usuario de prueba

        Returns:
            MagicMock: Request mock
        """
        request = MagicMock(spec=Request)
        request.app = simple_app
        request.session = {"user": test_user}
        request.query_params = {}
        request.scope = {"root_path": ""}
        return request

    @pytest.fixture
    def mock_request_without_user(self, simple_app: FastAPI) -> MagicMock:
        """Crear request mock sin usuario.

        Args:
            simple_app (FastAPI): Aplicación

        Returns:
            MagicMock: Request mock
        """
        request = MagicMock(spec=Request)
        request.app = simple_app
        request.session = {}
        request.query_params = {"error": None}
        request.scope = {"root_path": ""}
        return request

    async def test_index_with_user_redirects(
        self, mock_request_with_user: MagicMock, test_user: dict[str, Any]
    ) -> None:
        """Probar que index con usuario redirige al dashboard."""
        response = await index(mock_request_with_user, test_user)
        assert response.status_code == 307
        assert response.headers["location"] == "/dashboard"

    async def test_index_without_user_shows_login(
        self, mock_request_without_user: MagicMock
    ) -> None:
        """Probar que index sin usuario muestra login."""
        # Necesitamos templates reales o mock
        mock_request_without_user.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request_without_user.app.state.templates.TemplateResponse.return_value = mock_response

        response = await index(mock_request_without_user, None)

        mock_request_without_user.app.state.templates.TemplateResponse.assert_called_once()
        assert response == mock_response

    async def test_login_page_with_user_redirects(
        self, mock_request_with_user: MagicMock, test_user: dict[str, Any]
    ) -> None:
        """Probar que login_page con usuario redirige al dashboard."""
        response = await login_page(mock_request_with_user, test_user)
        assert response.status_code == 307
        assert response.headers["location"] == "/dashboard"

    async def test_login_page_without_user_shows_login(
        self, mock_request_without_user: MagicMock
    ) -> None:
        """Probar que login_page sin usuario muestra login."""
        mock_request_without_user.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request_without_user.app.state.templates.TemplateResponse.return_value = mock_response

        response = await login_page(mock_request_without_user, None)

        mock_request_without_user.app.state.templates.TemplateResponse.assert_called_once()
        assert response == mock_response

    async def test_dashboard_shows_guilds(
        self,
        mock_request_with_user: MagicMock,
        test_user: dict[str, Any],
        mock_session: AsyncMock,
    ) -> None:
        """Probar que dashboard muestra los guilds del usuario."""
        # Setup mock templates
        mock_request_with_user.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request_with_user.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock bot
        mock_request_with_user.app.state.bot = MagicMock()
        mock_request_with_user.app.state.bot.guilds = []
        mock_request_with_user.app.state.bot.user = MagicMock()
        mock_request_with_user.app.state.bot.user.name = "TestBot"
        mock_request_with_user.app.state.bot.user.avatar = None

        await dashboard(request=mock_request_with_user, user=test_user, session=mock_session)

        # Verificar que se llamó a TemplateResponse
        mock_request_with_user.app.state.templates.TemplateResponse.assert_called_once()
        call_kwargs = mock_request_with_user.app.state.templates.TemplateResponse.call_args.kwargs

        # Verificar contexto
        context = call_kwargs["context"]
        assert "user" in context
        assert "guilds" in context
        assert "bot" in context

    async def test_dashboard_for_owner(
        self,
        mock_request_with_user: MagicMock,
        test_user: dict[str, Any],
        mock_session: AsyncMock,
    ) -> None:
        """Probar dashboard para owner del bot."""
        # Setup owner
        mock_request_with_user.app.state.settings.web.owner_ids = [123456789]

        # Setup mock templates
        mock_request_with_user.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request_with_user.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock bot
        mock_request_with_user.app.state.bot = MagicMock()
        mock_request_with_user.app.state.bot.guilds = []
        mock_request_with_user.app.state.bot.user = None

        await dashboard(request=mock_request_with_user, user=test_user, session=mock_session)

        call_kwargs = mock_request_with_user.app.state.templates.TemplateResponse.call_args.kwargs
        context = call_kwargs["context"]
        assert context["is_owner"] is True

    async def test_dashboard_with_bot_in_guild(
        self,
        mock_request_with_user: MagicMock,
        test_user: dict[str, Any],
        mock_session: AsyncMock,
    ) -> None:
        """Probar dashboard cuando el bot está en el guild del usuario."""
        # Setup mock templates
        mock_request_with_user.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request_with_user.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock bot con guild
        mock_guild = MagicMock()
        mock_guild.id = 111222333
        mock_request_with_user.app.state.bot = MagicMock()
        mock_request_with_user.app.state.bot.guilds = [mock_guild]
        mock_request_with_user.app.state.bot.user = MagicMock()
        mock_request_with_user.app.state.bot.user.name = "TestBot"
        mock_request_with_user.app.state.bot.user.avatar = MagicMock()
        mock_request_with_user.app.state.bot.user.avatar.url = "http://example.com/avatar.png"

        await dashboard(request=mock_request_with_user, user=test_user, session=mock_session)

        call_kwargs = mock_request_with_user.app.state.templates.TemplateResponse.call_args.kwargs
        context = call_kwargs["context"]

        # Verificar que el guild tiene bot_present=True
        guilds = context["guilds"]
        guild_with_bot = next((g for g in guilds if g["id"] == "111222333"), None)
        assert guild_with_bot is not None
        assert guild_with_bot["bot_present"] is True

    async def test_dashboard_non_owner_with_bot_in_guild(
        self,
        mock_request_with_user: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        """Probar dashboard para non-owner cuando el bot está en el guild."""
        # User is NOT a bot owner but IS a guild owner
        mock_request_with_user.app.state.settings.web.owner_ids = []

        # User is guild owner (so _check_guild_access returns True)
        non_owner_user = {
            "id": "999888777",
            "username": "non_owner",
            "avatar": None,
            "guilds": [
                {
                    "id": "111222333",
                    "name": "Test Guild",
                    "icon": None,
                    "permissions": str(0x20),
                    "owner": True,  # Guild owner
                },
            ],
        }

        # Setup mock templates
        mock_request_with_user.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request_with_user.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock bot con guild
        mock_guild = MagicMock()
        mock_guild.id = 111222333
        mock_request_with_user.app.state.bot = MagicMock()
        mock_request_with_user.app.state.bot.guilds = [mock_guild]
        mock_request_with_user.app.state.bot.user = MagicMock()
        mock_request_with_user.app.state.bot.user.name = "TestBot"
        mock_request_with_user.app.state.bot.user.avatar = None

        await dashboard(request=mock_request_with_user, user=non_owner_user, session=mock_session)

        call_kwargs = mock_request_with_user.app.state.templates.TemplateResponse.call_args.kwargs
        context = call_kwargs["context"]

        # Non-owner should not be flagged as owner
        assert context["is_owner"] is False
        # Guild should be in the list with access
        guilds = context["guilds"]
        assert len(guilds) == 1
        assert guilds[0]["id"] == "111222333"
        assert guilds[0]["has_access"] is True

    async def test_dashboard_non_owner_guild_not_shown_without_access(
        self,
        mock_request_with_user: MagicMock,
        test_user: dict[str, Any],
        mock_session: AsyncMock,
    ) -> None:
        """Probar que non-owner no ve guild sin acceso."""
        # User is NOT an owner
        mock_request_with_user.app.state.settings.web.owner_ids = []

        # Setup mock templates
        mock_request_with_user.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request_with_user.app.state.templates.TemplateResponse.return_value = mock_response

        # Bot not in guild
        mock_request_with_user.app.state.bot = MagicMock()
        mock_request_with_user.app.state.bot.guilds = []
        mock_request_with_user.app.state.bot.user = None

        await dashboard(request=mock_request_with_user, user=test_user, session=mock_session)

        call_kwargs = mock_request_with_user.app.state.templates.TemplateResponse.call_args.kwargs
        context = call_kwargs["context"]

        # No guilds should be shown (bot not in any of user's guilds)
        assert context["guilds"] == []


class TestCheckGuildAccess:
    """Tests para _check_guild_access."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)
        return session

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Create mock bot."""
        bot = MagicMock()
        bot.get_guild.return_value = None
        return bot

    @pytest.fixture
    def test_user_data(self) -> dict[str, Any]:
        """Create test user data."""
        return {"id": "123456789", "username": "testuser"}

    async def test_guild_owner_has_access(
        self,
        mock_session: AsyncMock,
        mock_bot: MagicMock,
        test_user_data: dict[str, Any],
    ) -> None:
        """Probar que el owner del guild tiene acceso."""
        result = await _check_guild_access(
            session=mock_session,
            bot=mock_bot,
            guild_id=111222333,
            user_id=123456789,
            is_bot_owner=False,
            is_guild_owner=True,  # Es owner del guild
            user=test_user_data,
        )

        assert result is True
        # No debería hacer consultas a la DB
        mock_session.execute.assert_not_called()

    async def test_invited_by_has_access(
        self,
        mock_session: AsyncMock,
        mock_bot: MagicMock,
        test_user_data: dict[str, Any],
    ) -> None:
        """Probar que quien invitó al bot tiene acceso."""
        # Mock Guild con invited_by_id
        mock_guild_record = MagicMock()
        mock_guild_record.invited_by_id = 123456789  # El usuario invitó al bot

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_guild_record
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await _check_guild_access(
            session=mock_session,
            bot=mock_bot,
            guild_id=111222333,
            user_id=123456789,
            is_bot_owner=False,
            is_guild_owner=False,
            user=test_user_data,
        )

        assert result is True

    async def test_admin_role_has_access(
        self,
        mock_session: AsyncMock,
        mock_bot: MagicMock,
        test_user_data: dict[str, Any],
    ) -> None:
        """Probar que un usuario con rol admin tiene acceso."""
        # Mock Guild record sin invited_by
        mock_guild_record = MagicMock()
        mock_guild_record.invited_by_id = None

        # Mock admin_roles config
        mock_guild_result = MagicMock()
        mock_guild_result.scalar_one_or_none.return_value = mock_guild_record

        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = [999888777]  # admin role ID

        # Dos llamadas a execute: Guild y GuildConfig
        mock_session.execute = AsyncMock(side_effect=[mock_guild_result, mock_config_result])

        # Mock Discord guild con miembro que tiene el rol
        mock_role = MagicMock()
        mock_role.id = 999888777

        mock_member = MagicMock()
        mock_member.roles = [mock_role]

        mock_discord_guild = MagicMock()
        mock_discord_guild.get_member.return_value = mock_member

        mock_bot.get_guild.return_value = mock_discord_guild

        result = await _check_guild_access(
            session=mock_session,
            bot=mock_bot,
            guild_id=111222333,
            user_id=123456789,
            is_bot_owner=False,
            is_guild_owner=False,
            user=test_user_data,
        )

        assert result is True

    async def test_no_access_returns_false(
        self,
        mock_session: AsyncMock,
        mock_bot: MagicMock,
        test_user_data: dict[str, Any],
    ) -> None:
        """Probar que usuario sin acceso retorna False."""
        # Mock Guild record sin invited_by
        mock_guild_record = MagicMock()
        mock_guild_record.invited_by_id = 999  # Otro usuario invitó

        mock_guild_result = MagicMock()
        mock_guild_result.scalar_one_or_none.return_value = mock_guild_record

        # Sin admin roles configurados
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[mock_guild_result, mock_config_result])

        result = await _check_guild_access(
            session=mock_session,
            bot=mock_bot,
            guild_id=111222333,
            user_id=123456789,
            is_bot_owner=False,
            is_guild_owner=False,
            user=test_user_data,
        )

        assert result is False

    async def test_member_not_in_guild(
        self,
        mock_session: AsyncMock,
        mock_bot: MagicMock,
        test_user_data: dict[str, Any],
    ) -> None:
        """Probar cuando el usuario no está en el guild de Discord."""
        # Mock Guild record sin invited_by
        mock_guild_record = MagicMock()
        mock_guild_record.invited_by_id = None

        mock_guild_result = MagicMock()
        mock_guild_result.scalar_one_or_none.return_value = mock_guild_record

        # Admin roles configurados
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = [999888777]

        mock_session.execute = AsyncMock(side_effect=[mock_guild_result, mock_config_result])

        # Discord guild existe pero el usuario no es miembro
        mock_discord_guild = MagicMock()
        mock_discord_guild.get_member.return_value = None

        mock_bot.get_guild.return_value = mock_discord_guild

        result = await _check_guild_access(
            session=mock_session,
            bot=mock_bot,
            guild_id=111222333,
            user_id=123456789,
            is_bot_owner=False,
            is_guild_owner=False,
            user=test_user_data,
        )

        assert result is False

    async def test_discord_guild_not_found(
        self,
        mock_session: AsyncMock,
        mock_bot: MagicMock,
        test_user_data: dict[str, Any],
    ) -> None:
        """Probar cuando el bot no está en el guild."""
        # Mock Guild record sin invited_by
        mock_guild_record = MagicMock()
        mock_guild_record.invited_by_id = None

        mock_guild_result = MagicMock()
        mock_guild_result.scalar_one_or_none.return_value = mock_guild_record

        # Admin roles configurados
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = [999888777]

        mock_session.execute = AsyncMock(side_effect=[mock_guild_result, mock_config_result])

        # Bot no está en el guild
        mock_bot.get_guild.return_value = None

        result = await _check_guild_access(
            session=mock_session,
            bot=mock_bot,
            guild_id=111222333,
            user_id=123456789,
            is_bot_owner=False,
            is_guild_owner=False,
            user=test_user_data,
        )

        assert result is False
