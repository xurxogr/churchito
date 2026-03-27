"""Tests for the dashboard routes."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from discord_bot.web.routers.dashboard import _check_guild_access, dashboard, index, login_page


class TestDashboardRoutes:
    """Tests for dashboard routes."""

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
        """Create mock request with user.

        Args:
            simple_app (FastAPI): Application
            test_user (dict[str, Any]): Test user

        Returns:
            MagicMock: Mock request
        """
        request = MagicMock(spec=Request)
        request.app = simple_app
        request.session = {"user": test_user}
        request.query_params = {}
        request.scope = {"root_path": ""}
        return request

    @pytest.fixture
    def mock_request_without_user(self, simple_app: FastAPI) -> MagicMock:
        """Create mock request without user.

        Args:
            simple_app (FastAPI): Application

        Returns:
            MagicMock: Mock request
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
        """Test that index with user redirects to dashboard."""
        response = await index(mock_request_with_user, test_user)
        assert response.status_code == 307
        assert response.headers["location"] == "/dashboard"

    async def test_index_without_user_shows_login(
        self, mock_request_without_user: MagicMock
    ) -> None:
        """Test that index without user shows login."""
        # Need real or mock templates
        mock_request_without_user.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request_without_user.app.state.templates.TemplateResponse.return_value = mock_response

        response = await index(mock_request_without_user, None)

        mock_request_without_user.app.state.templates.TemplateResponse.assert_called_once()
        assert response == mock_response

    async def test_login_page_with_user_redirects(
        self, mock_request_with_user: MagicMock, test_user: dict[str, Any]
    ) -> None:
        """Test that login_page with user redirects to dashboard."""
        response = await login_page(mock_request_with_user, test_user)
        assert response.status_code == 307
        assert response.headers["location"] == "/dashboard"

    async def test_login_page_without_user_shows_login(
        self, mock_request_without_user: MagicMock
    ) -> None:
        """Test that login_page without user shows login."""
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
        """Test that dashboard shows user's guilds."""
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

        # Verify TemplateResponse was called
        mock_request_with_user.app.state.templates.TemplateResponse.assert_called_once()
        call_kwargs = mock_request_with_user.app.state.templates.TemplateResponse.call_args.kwargs

        # Verify context
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
        """Test dashboard for bot owner."""
        # Setup owner
        mock_request_with_user.app.state.settings.web.owner_ids = [123456789012345678]

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
        """Test dashboard when bot is in user's guild."""
        # Setup mock templates
        mock_request_with_user.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request_with_user.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock bot with guild
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

        # Verify guild has bot_present=True
        guilds = context["guilds"]
        guild_with_bot = next((g for g in guilds if g["id"] == "111222333"), None)
        assert guild_with_bot is not None
        assert guild_with_bot["bot_present"] is True

    async def test_dashboard_non_owner_with_bot_in_guild(
        self,
        mock_request_with_user: MagicMock,
        mock_session: AsyncMock,
    ) -> None:
        """Test dashboard for non-owner when bot is in guild."""
        # User is NOT a bot owner but IS a guild owner
        mock_request_with_user.app.state.settings.web.owner_ids = []

        # Session no longer stores guilds - only user info
        non_owner_user = {
            "id": "999888777",
            "username": "non_owner",
            "avatar": None,
        }

        # Setup mock templates
        mock_request_with_user.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request_with_user.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock bot with guild where user is owner
        mock_guild = MagicMock()
        mock_guild.id = 111222333
        mock_guild.name = "Test Guild"
        mock_guild.icon = None
        mock_guild.owner_id = 999888777  # User is guild owner
        mock_request_with_user.app.state.bot = MagicMock()
        mock_request_with_user.app.state.bot.guilds = [mock_guild]
        mock_request_with_user.app.state.bot.get_guild.return_value = mock_guild
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
        """Test that non-owner doesn't see guild without access."""
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
    """Tests for _check_guild_access."""

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
        mock_guild = MagicMock()
        mock_guild.owner_id = 0  # Default: user is not owner
        bot.get_guild.return_value = mock_guild
        return bot

    async def test_guild_owner_has_access(
        self,
        mock_session: AsyncMock,
        mock_bot: MagicMock,
    ) -> None:
        """Test that guild owner has access."""
        # User is guild owner
        mock_bot.get_guild.return_value.owner_id = 123456789012345678

        result = await _check_guild_access(
            session=mock_session,
            bot=mock_bot,
            guild_id=111222333,
            user_id=123456789012345678,
            is_bot_owner=False,
        )

        assert result is True
        # Should not make DB queries
        mock_session.execute.assert_not_called()

    async def test_invited_by_has_access(
        self,
        mock_session: AsyncMock,
        mock_bot: MagicMock,
    ) -> None:
        """Test that user who invited the bot has access."""
        # Mock Guild with invited_by_id
        mock_guild_record = MagicMock()
        mock_guild_record.invited_by_id = 123456789012345678  # User invited the bot

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_guild_record
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await _check_guild_access(
            session=mock_session,
            bot=mock_bot,
            guild_id=111222333,
            user_id=123456789012345678,
            is_bot_owner=False,
        )

        assert result is True

    async def test_admin_role_has_access(
        self,
        mock_session: AsyncMock,
        mock_bot: MagicMock,
    ) -> None:
        """Test that user with admin role has access."""
        # Mock Guild record without invited_by
        mock_guild_record = MagicMock()
        mock_guild_record.invited_by_id = None

        # Mock admin_roles config
        mock_guild_result = MagicMock()
        mock_guild_result.scalar_one_or_none.return_value = mock_guild_record

        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = [999888777]  # admin role ID

        # Two calls to execute: Guild and GuildConfig
        mock_session.execute = AsyncMock(side_effect=[mock_guild_result, mock_config_result])

        # Mock Discord guild with member that has the role
        mock_role = MagicMock()
        mock_role.id = 999888777

        mock_member = MagicMock()
        mock_member.roles = [mock_role]

        mock_discord_guild = MagicMock()
        mock_discord_guild.owner_id = 0  # User is not owner
        mock_discord_guild.get_member.return_value = mock_member

        mock_bot.get_guild.return_value = mock_discord_guild

        result = await _check_guild_access(
            session=mock_session,
            bot=mock_bot,
            guild_id=111222333,
            user_id=123456789012345678,
            is_bot_owner=False,
        )

        assert result is True

    async def test_no_access_returns_false(
        self,
        mock_session: AsyncMock,
        mock_bot: MagicMock,
    ) -> None:
        """Test that user without access returns False."""
        # Mock Guild record without invited_by
        mock_guild_record = MagicMock()
        mock_guild_record.invited_by_id = 999  # Another user invited

        mock_guild_result = MagicMock()
        mock_guild_result.scalar_one_or_none.return_value = mock_guild_record

        # No admin roles configured
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(side_effect=[mock_guild_result, mock_config_result])

        result = await _check_guild_access(
            session=mock_session,
            bot=mock_bot,
            guild_id=111222333,
            user_id=123456789012345678,
            is_bot_owner=False,
        )

        assert result is False

    async def test_member_not_in_guild(
        self,
        mock_session: AsyncMock,
        mock_bot: MagicMock,
    ) -> None:
        """Test when user is not in the Discord guild."""
        # Mock Guild record without invited_by
        mock_guild_record = MagicMock()
        mock_guild_record.invited_by_id = None

        mock_guild_result = MagicMock()
        mock_guild_result.scalar_one_or_none.return_value = mock_guild_record

        # Admin roles configured
        mock_config_result = MagicMock()
        mock_config_result.scalar_one_or_none.return_value = [999888777]

        mock_session.execute = AsyncMock(side_effect=[mock_guild_result, mock_config_result])

        # Discord guild exists but user is not a member
        mock_discord_guild = MagicMock()
        mock_discord_guild.owner_id = 0
        mock_discord_guild.get_member.return_value = None
        mock_discord_guild.fetch_member = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Member not found")
        )

        mock_bot.get_guild.return_value = mock_discord_guild

        result = await _check_guild_access(
            session=mock_session,
            bot=mock_bot,
            guild_id=111222333,
            user_id=123456789012345678,
            is_bot_owner=False,
        )

        assert result is False

    async def test_discord_guild_not_found(
        self,
        mock_session: AsyncMock,
        mock_bot: MagicMock,
    ) -> None:
        """Test when bot is not in the guild."""
        # Bot is not in the guild
        mock_bot.get_guild.return_value = None

        result = await _check_guild_access(
            session=mock_session,
            bot=mock_bot,
            guild_id=111222333,
            user_id=123456789012345678,
            is_bot_owner=False,
        )

        assert result is False
        # Should not make DB queries if bot is not in the guild
        mock_session.execute.assert_not_called()
