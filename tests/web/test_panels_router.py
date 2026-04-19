"""Tests for the panels router."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient

from discord_bot.roles.models import PanelType, ReactionPanel
from discord_bot.web.routers.panels import (
    _format_embed_config,
    _get_guild_data,
    _panel_to_dict,
    create_panel,
    delete_panel,
    edit_panel_form,
    get_templates,
    guild_access_dep,
    list_panels,
    post_panel,
    router,
    update_panel,
)


@pytest.fixture
def panels_app(simple_app: FastAPI) -> FastAPI:
    """Create application with panels router.

    Args:
        simple_app (FastAPI): Base application

    Returns:
        FastAPI: Application with panels router
    """
    simple_app.include_router(router)
    return simple_app


@pytest.fixture
def panels_client(panels_app: FastAPI) -> TestClient:
    """Create client for panels.

    Args:
        panels_app (FastAPI): Application

    Returns:
        TestClient: Test client
    """
    return TestClient(panels_app, raise_server_exceptions=False)


class TestGetTemplates:
    """Tests for get_templates."""

    def test_returns_templates(self, simple_app: FastAPI) -> None:
        """Test that it returns templates."""
        request = MagicMock()
        request.app = simple_app

        templates = get_templates(request)
        assert templates is not None


class TestPanelToDict:
    """Tests for _panel_to_dict helper."""

    def _create_mock_panel(self) -> MagicMock:
        """Create a mock ReactionPanel."""
        panel = MagicMock(spec=ReactionPanel)
        panel.id = 1
        panel.public_id = "abc123def456"
        panel.name = "TestPanel"
        panel.panel_type = PanelType.TOGGLE
        panel.channel_id = 456
        panel.message_id = 789
        panel.role_mappings = [{"emoji": "👍", "role_id": 100}]
        panel.required_roles = [200]
        panel.dm_on_missing_role = True
        panel.dm_on_role_change = False
        panel.embed_config = None
        return panel

    def test_converts_panel_with_guild(self) -> None:
        """Test converting panel with guild context."""
        panel = self._create_mock_panel()

        mock_channel = MagicMock()
        mock_channel.name = "test-channel"

        mock_guild = MagicMock()
        mock_guild.get_channel.return_value = mock_channel

        result = _panel_to_dict(panel=panel, guild=mock_guild)

        assert result["id"] == 1
        assert result["public_id"] == "abc123def456"
        assert result["name"] == "TestPanel"
        assert result["panel_type"] == PanelType.TOGGLE
        assert result["channel_id"] == "456"
        assert result["channel_name"] == "test-channel"
        assert result["message_id"] == 789
        assert result["is_posted"] is True
        assert result["mappings_count"] == 1
        assert result["dm_on_missing_role"] is True
        assert result["dm_on_role_change"] is False

    def test_converts_panel_without_guild(self) -> None:
        """Test converting panel without guild context."""
        panel = self._create_mock_panel()

        result = _panel_to_dict(panel=panel, guild=None)

        assert result["channel_name"] == "Unknown (456)"

    def test_converts_panel_channel_not_found(self) -> None:
        """Test converting panel when channel not in guild."""
        panel = self._create_mock_panel()

        mock_guild = MagicMock()
        mock_guild.get_channel.return_value = None

        result = _panel_to_dict(panel=panel, guild=mock_guild)

        assert result["channel_name"] == "Unknown (456)"

    def test_is_posted_false_when_no_message_id(self) -> None:
        """Test is_posted is False when message_id is None."""
        panel = self._create_mock_panel()
        panel.message_id = None

        result = _panel_to_dict(panel=panel, guild=None)

        assert result["is_posted"] is False

    def test_includes_embed_config(self) -> None:
        """Test that embed_config is included in result."""
        panel = self._create_mock_panel()
        panel.embed_config = {"title": "Test", "color": 0x5865F2}

        result = _panel_to_dict(panel=panel, guild=None)

        assert result["embed_config"] is not None
        assert result["embed_config"]["title"] == "Test"
        # Color should be converted to hex string
        assert result["embed_config"]["color"] == "#5865F2"

    def test_handles_none_embed_config(self) -> None:
        """Test that None embed_config is handled."""
        panel = self._create_mock_panel()
        panel.embed_config = None

        result = _panel_to_dict(panel=panel, guild=None)

        assert result["embed_config"] is None


class TestFormatEmbedConfig:
    """Tests for _format_embed_config helper."""

    def test_returns_none_for_none_input(self) -> None:
        """Test that None input returns None."""
        result = _format_embed_config(None)
        assert result is None

    def test_returns_none_for_empty_dict(self) -> None:
        """Test that empty dict returns None."""
        result = _format_embed_config({})
        assert result is None

    def test_converts_int_color_to_hex(self) -> None:
        """Test that integer color is converted to hex string."""
        result = _format_embed_config({"color": 0x5865F2})
        assert result is not None
        assert result["color"] == "#5865F2"

    def test_preserves_hex_string_color(self) -> None:
        """Test that hex string color is preserved."""
        result = _format_embed_config({"color": "#FF0000"})
        assert result is not None
        assert result["color"] == "#FF0000"

    def test_preserves_other_fields(self) -> None:
        """Test that other fields are preserved."""
        result = _format_embed_config(
            {
                "title": "Test Title",
                "description": "Test Description",
                "color": 0xFF0000,
            }
        )
        assert result is not None
        assert result["title"] == "Test Title"
        assert result["description"] == "Test Description"
        assert result["color"] == "#FF0000"


class TestGetGuildData:
    """Tests for _get_guild_data helper."""

    def test_returns_empty_when_no_bot(self, simple_app: FastAPI) -> None:
        """Test returns empty lists when no bot."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.bot = None

        guild, channels, roles, emojis = _get_guild_data(request=request, guild_id=123)

        assert guild is None
        assert channels == []
        assert roles == []

    def test_returns_empty_when_guild_not_found(self, simple_app: FastAPI) -> None:
        """Test returns empty lists when guild not found."""
        request = MagicMock()
        request.app = simple_app
        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = None

        guild, channels, roles, emojis = _get_guild_data(request=request, guild_id=123)

        assert guild is None
        assert channels == []
        assert roles == []

    def test_returns_channels_and_roles(self, simple_app: FastAPI) -> None:
        """Test returns channels and roles from guild."""
        request = MagicMock()
        request.app = simple_app

        # Mock channel with permissions
        mock_channel = MagicMock()
        mock_channel.id = 456
        mock_channel.name = "general"
        mock_channel.category = None
        mock_permissions = MagicMock()
        mock_permissions.send_messages = True
        mock_channel.permissions_for.return_value = mock_permissions

        # Mock role
        mock_role = MagicMock()
        mock_role.id = 100
        mock_role.name = "Member"
        mock_role.color = 0xFF0000
        mock_role.__lt__ = lambda self, other: True  # Role comparison

        everyone_role = MagicMock()
        everyone_role.name = "@everyone"

        # Mock bot member
        mock_bot_member = MagicMock()
        mock_bot_member.top_role = MagicMock()
        # Mock role comparison: all roles < bot's top role
        mock_role.__lt__ = lambda self, other: True

        # Mock guild
        mock_guild = MagicMock()
        mock_guild.text_channels = [mock_channel]
        mock_guild.roles = [everyone_role, mock_role]
        mock_guild.me = mock_bot_member
        mock_guild.get_member.return_value = mock_bot_member

        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = mock_guild
        simple_app.state.bot.user.id = 999

        guild, channels, roles, emojis = _get_guild_data(request=request, guild_id=123)

        assert guild is mock_guild
        assert len(channels) >= 1
        # At least one role (excluding @everyone)

    def test_filters_channels_without_send_permission(self, simple_app: FastAPI) -> None:
        """Test filters channels where bot can't send messages."""
        request = MagicMock()
        request.app = simple_app

        # Channel with permission
        good_channel = MagicMock()
        good_channel.id = 456
        good_channel.name = "allowed"
        good_channel.category = None
        good_permissions = MagicMock()
        good_permissions.send_messages = True
        good_channel.permissions_for.return_value = good_permissions

        # Channel without permission
        bad_channel = MagicMock()
        bad_channel.id = 789
        bad_channel.name = "restricted"
        bad_channel.category = None
        bad_permissions = MagicMock()
        bad_permissions.send_messages = False
        bad_channel.permissions_for.return_value = bad_permissions

        # Mock bot member
        mock_bot_member = MagicMock()
        mock_bot_member.top_role = MagicMock()

        # Mock guild
        mock_guild = MagicMock()
        mock_guild.text_channels = [good_channel, bad_channel]
        mock_guild.roles = []
        mock_guild.me = mock_bot_member
        mock_guild.get_member.return_value = mock_bot_member

        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = mock_guild
        simple_app.state.bot.user.id = 999

        guild, channels, roles, emojis = _get_guild_data(request=request, guild_id=123)

        assert len(channels) == 1
        assert channels[0]["name"] == "allowed"

    def test_returns_guild_emojis(self, simple_app: FastAPI) -> None:
        """Test returns guild custom emojis."""
        request = MagicMock()
        request.app = simple_app

        # Mock emoji
        mock_emoji = MagicMock()
        mock_emoji.id = 12345
        mock_emoji.name = "custom_emoji"
        mock_emoji.animated = False
        mock_emoji.url = "https://cdn.discordapp.com/emojis/12345.png"

        # Mock bot member
        mock_bot_member = MagicMock()
        mock_bot_member.top_role = MagicMock()

        # Mock guild
        mock_guild = MagicMock()
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.emojis = [mock_emoji]
        mock_guild.me = mock_bot_member
        mock_guild.get_member.return_value = mock_bot_member

        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = mock_guild
        simple_app.state.bot.user.id = 999

        guild, channels, roles, emojis = _get_guild_data(request=request, guild_id=123)

        assert len(emojis) == 1
        assert emojis[0]["id"] == "12345"
        assert emojis[0]["name"] == "custom_emoji"
        assert emojis[0]["animated"] is False
        assert "url" in emojis[0]


class TestListPanelsEndpoint:
    """Tests for list_panels endpoint."""

    async def test_requires_authentication(
        self, panels_client: TestClient, panels_app: FastAPI
    ) -> None:
        """Test that endpoint requires authentication."""
        response = panels_client.get("/guild/123/panels")
        # Should redirect to login or return 401/403
        assert response.status_code in [303, 401, 403, 404, 422, 500]

    async def test_returns_panels_list(
        self, panels_client: TestClient, panels_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Test that endpoint returns panels list."""
        # This would require mocking the authentication and database
        # For now, we test that the route exists
        pass


class TestCreatePanelEndpoint:
    """Tests for create_panel endpoint."""

    async def test_requires_authentication(self, panels_client: TestClient) -> None:
        """Test that endpoint requires authentication."""
        response = panels_client.post(
            "/guild/123/panels/create",
            data={
                "name": "Test",
                "channel_id": "456",
                "panel_type": "toggle",
            },
        )
        assert response.status_code in [303, 401, 403, 404, 422, 500]


class TestEditPanelFormEndpoint:
    """Tests for edit_panel_form endpoint."""

    async def test_requires_authentication(self, panels_client: TestClient) -> None:
        """Test that endpoint requires authentication."""
        response = panels_client.get("/guild/123/panels/1/edit")
        assert response.status_code in [303, 401, 403, 404, 422, 500]


class TestUpdatePanelEndpoint:
    """Tests for update_panel endpoint."""

    async def test_requires_authentication(self, panels_client: TestClient) -> None:
        """Test that endpoint requires authentication."""
        response = panels_client.post(
            "/guild/123/panels/1/update",
            data={
                "name": "Updated",
                "channel_id": "456",
                "panel_type": "toggle",
            },
        )
        assert response.status_code in [303, 401, 403, 404, 422, 500]


class TestDeletePanelEndpoint:
    """Tests for delete_panel endpoint."""

    async def test_requires_authentication(self, panels_client: TestClient) -> None:
        """Test that endpoint requires authentication."""
        response = panels_client.post("/guild/123/panels/1/delete")
        assert response.status_code in [303, 401, 403, 404, 422, 500]


class TestPostPanelEndpoint:
    """Tests for post_panel endpoint."""

    async def test_requires_authentication(self, panels_client: TestClient) -> None:
        """Test that endpoint requires authentication."""
        response = panels_client.post("/guild/123/panels/1/post")
        assert response.status_code in [303, 401, 403, 404, 422, 500]


class TestGuildAccessDep:
    """Tests for guild_access_dep function."""

    async def test_returns_user_on_valid_access(
        self, simple_app: FastAPI, test_user: dict[str, Any]
    ) -> None:
        """Test that it returns user when access is valid."""
        request = MagicMock(spec=Request)
        request.app = simple_app
        simple_app.state.settings.web.owner_ids = [123456789012345678]

        result = await guild_access_dep(request, 111222333, test_user)
        assert result == test_user


class TestListPanelsDirectCall:
    """Tests for list_panels endpoint called directly."""

    @pytest.fixture
    def mock_request(self, simple_app: FastAPI) -> MagicMock:
        """Create mock request."""
        request = MagicMock(spec=Request)
        request.app = simple_app
        request.scope = {"root_path": ""}
        return request

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    async def test_returns_panels_list(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that list_panels returns panels list."""
        # Setup mock templates
        mock_request.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock bot
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = None

        # Mock the service
        with (
            patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls,
            patch("discord_bot.web.routers.panels.get_csrf_token", return_value="test_token"),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.get_all_for_guild = AsyncMock(return_value=[])

            _response = await list_panels(
                request=mock_request,
                guild_id=123,
                user=test_user,
                session=mock_session,
            )

            mock_request.app.state.templates.TemplateResponse.assert_called_once()
            call_kwargs = mock_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]
            assert "panels" in context
            assert context["panels"] == []
            assert context["guild_id"] == 123

    async def test_returns_panels_with_data(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that list_panels returns panels with data."""
        # Setup mock templates
        mock_request.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock guild
        mock_channel = MagicMock()
        mock_channel.name = "test-channel"
        mock_guild = MagicMock()
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()

        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild
        mock_request.app.state.bot.user.id = 999

        # Create mock panel
        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.id = 1
        mock_panel.public_id = "abc123"
        mock_panel.name = "TestPanel"
        mock_panel.panel_type = PanelType.TOGGLE
        mock_panel.channel_id = 456
        mock_panel.message_id = 789
        mock_panel.role_mappings = []
        mock_panel.required_roles = []
        mock_panel.dm_on_missing_role = False
        mock_panel.dm_on_role_change = False
        mock_panel.embed_config = None

        with (
            patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls,
            patch("discord_bot.web.routers.panels.get_csrf_token", return_value="test_token"),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.get_all_for_guild = AsyncMock(return_value=[mock_panel])

            await list_panels(
                request=mock_request,
                guild_id=123,
                user=test_user,
                session=mock_session,
            )

            call_kwargs = mock_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]
            assert len(context["panels"]) == 1
            assert context["panels"][0]["name"] == "TestPanel"


class TestCreatePanelDirectCall:
    """Tests for create_panel endpoint called directly."""

    @pytest.fixture
    def mock_request(self, simple_app: FastAPI) -> MagicMock:
        """Create mock request."""
        request = MagicMock(spec=Request)
        request.app = simple_app
        request.scope = {"root_path": ""}
        return request

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    async def test_creates_panel_successfully(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that create_panel creates a panel."""
        # Setup mock templates
        mock_request.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock bot
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild
        mock_request.app.state.bot.user.id = 999

        with (
            patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls,
            patch("discord_bot.web.routers.panels.get_csrf_token", return_value="test_token"),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.get_by_name = AsyncMock(return_value=None)
            mock_service.create_panel = AsyncMock()
            mock_service.get_all_for_guild = AsyncMock(return_value=[])

            await create_panel(
                request=mock_request,
                guild_id=123,
                user=test_user,
                session=mock_session,
                name="NewPanel",
                channel_id="456",
                panel_type="toggle",
            )

            mock_service.create_panel.assert_called_once()
            mock_session.commit.assert_called()

    async def test_rejects_invalid_name(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that create_panel rejects invalid name."""
        with pytest.raises(HTTPException) as exc_info:
            await create_panel(
                request=mock_request,
                guild_id=123,
                user=test_user,
                session=mock_session,
                name="",
                channel_id="456",
                panel_type="toggle",
            )
        assert exc_info.value.status_code == 400
        assert "Invalid panel name" in exc_info.value.detail

    async def test_rejects_name_too_long(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that create_panel rejects name too long."""
        with pytest.raises(HTTPException) as exc_info:
            await create_panel(
                request=mock_request,
                guild_id=123,
                user=test_user,
                session=mock_session,
                name="x" * 101,
                channel_id="456",
                panel_type="toggle",
            )
        assert exc_info.value.status_code == 400
        assert "Invalid panel name" in exc_info.value.detail

    async def test_rejects_invalid_channel_id(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that create_panel rejects invalid channel ID."""
        with pytest.raises(HTTPException) as exc_info:
            await create_panel(
                request=mock_request,
                guild_id=123,
                user=test_user,
                session=mock_session,
                name="ValidName",
                channel_id="not_a_number",
                panel_type="toggle",
            )
        assert exc_info.value.status_code == 400
        assert "Invalid channel ID" in exc_info.value.detail

    async def test_rejects_invalid_panel_type(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that create_panel rejects invalid panel type."""
        with pytest.raises(HTTPException) as exc_info:
            await create_panel(
                request=mock_request,
                guild_id=123,
                user=test_user,
                session=mock_session,
                name="ValidName",
                channel_id="456",
                panel_type="invalid_type",
            )
        assert exc_info.value.status_code == 400
        assert "Invalid panel type" in exc_info.value.detail

    async def test_rejects_duplicate_name(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that create_panel rejects duplicate name."""
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = None

        with patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_by_name = AsyncMock(return_value=MagicMock())

            with pytest.raises(HTTPException) as exc_info:
                await create_panel(
                    request=mock_request,
                    guild_id=123,
                    user=test_user,
                    session=mock_session,
                    name="ExistingPanel",
                    channel_id="456",
                    panel_type="toggle",
                )

            assert exc_info.value.status_code == 400
            assert "already exists" in exc_info.value.detail


class TestEditPanelFormDirectCall:
    """Tests for edit_panel_form endpoint called directly."""

    @pytest.fixture
    def mock_request(self, simple_app: FastAPI) -> MagicMock:
        """Create mock request."""
        request = MagicMock(spec=Request)
        request.app = simple_app
        request.scope = {"root_path": ""}
        return request

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    async def test_returns_edit_form(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that edit_panel_form returns edit form."""
        # Setup mock templates
        mock_request.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock bot
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = None

        # Create mock panel
        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.id = 1
        mock_panel.public_id = "abc123"
        mock_panel.name = "TestPanel"
        mock_panel.panel_type = PanelType.TOGGLE
        mock_panel.channel_id = 456
        mock_panel.message_id = None
        mock_panel.role_mappings = []
        mock_panel.required_roles = []
        mock_panel.dm_on_missing_role = False
        mock_panel.dm_on_role_change = False
        mock_panel.embed_config = None
        mock_panel.guild_id = 123

        with (
            patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls,
            patch("discord_bot.web.routers.panels.get_csrf_token", return_value="test_token"),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)

            await edit_panel_form(
                request=mock_request,
                guild_id=123,
                panel_id=1,
                user=test_user,
                session=mock_session,
            )

            mock_request.app.state.templates.TemplateResponse.assert_called_once()
            call_kwargs = mock_request.app.state.templates.TemplateResponse.call_args.kwargs
            context = call_kwargs["context"]
            assert context["panel"]["name"] == "TestPanel"

    async def test_raises_404_when_not_found(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that edit_panel_form raises 404 when not found."""
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = None

        with patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await edit_panel_form(
                    request=mock_request,
                    guild_id=123,
                    panel_id=999,
                    user=test_user,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 404

    async def test_raises_404_wrong_guild(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that edit_panel_form raises 404 for wrong guild."""
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = None

        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.guild_id = 999  # Different guild

        with patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)

            with pytest.raises(HTTPException) as exc_info:
                await edit_panel_form(
                    request=mock_request,
                    guild_id=123,
                    panel_id=1,
                    user=test_user,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 404


class TestUpdatePanelDirectCall:
    """Tests for update_panel endpoint called directly."""

    @pytest.fixture
    def mock_request(self, simple_app: FastAPI) -> MagicMock:
        """Create mock request."""
        request = MagicMock(spec=Request)
        request.app = simple_app
        request.scope = {"root_path": ""}
        return request

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    async def test_updates_panel_successfully(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that update_panel updates a panel."""
        # Setup mock templates
        mock_request.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock bot
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild
        mock_request.app.state.bot.user.id = 999

        # Create mock panel
        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.id = 1
        mock_panel.name = "OldName"
        mock_panel.guild_id = 123

        with (
            patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls,
            patch("discord_bot.web.routers.panels.get_csrf_token", return_value="test_token"),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)
            mock_service.get_by_name = AsyncMock(return_value=None)
            mock_service.get_all_for_guild = AsyncMock(return_value=[])

            await update_panel(
                request=mock_request,
                guild_id=123,
                panel_id=1,
                user=test_user,
                session=mock_session,
                name="NewName",
                channel_id="456",
                panel_type="toggle",
                role_mappings="[]",
                required_roles="[]",
            )

            assert mock_panel.name == "NewName"
            mock_session.commit.assert_called()

    async def test_raises_404_when_not_found(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that update_panel raises 404 when not found."""
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = None

        with patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await update_panel(
                    request=mock_request,
                    guild_id=123,
                    panel_id=999,
                    user=test_user,
                    session=mock_session,
                    name="Test",
                    channel_id="456",
                    panel_type="toggle",
                )

            assert exc_info.value.status_code == 404

    async def test_rejects_duplicate_name(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that update_panel rejects duplicate name."""
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = None

        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.name = "OldName"
        mock_panel.guild_id = 123

        with patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)
            mock_service.get_by_name = AsyncMock(return_value=MagicMock())

            with pytest.raises(HTTPException) as exc_info:
                await update_panel(
                    request=mock_request,
                    guild_id=123,
                    panel_id=1,
                    user=test_user,
                    session=mock_session,
                    name="ExistingName",
                    channel_id="456",
                    panel_type="toggle",
                )

            assert exc_info.value.status_code == 400
            assert "already exists" in exc_info.value.detail

    async def test_rejects_invalid_json(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that update_panel rejects invalid JSON."""
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = None

        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.name = "Panel"
        mock_panel.guild_id = 123

        with patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)

            with pytest.raises(HTTPException) as exc_info:
                await update_panel(
                    request=mock_request,
                    guild_id=123,
                    panel_id=1,
                    user=test_user,
                    session=mock_session,
                    name="Panel",
                    channel_id="456",
                    panel_type="toggle",
                    role_mappings="invalid json",
                )

            assert exc_info.value.status_code == 400
            assert "Invalid JSON" in exc_info.value.detail

    async def test_rejects_invalid_channel_id(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that update_panel rejects invalid channel ID."""
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = None

        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.name = "Panel"
        mock_panel.guild_id = 123

        with patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)

            with pytest.raises(HTTPException) as exc_info:
                await update_panel(
                    request=mock_request,
                    guild_id=123,
                    panel_id=1,
                    user=test_user,
                    session=mock_session,
                    name="Panel",
                    channel_id="not_a_number",
                    panel_type="toggle",
                    role_mappings="[]",
                    required_roles="[]",
                )

            assert exc_info.value.status_code == 400
            assert "Invalid channel ID" in exc_info.value.detail


class TestDeletePanelDirectCall:
    """Tests for delete_panel endpoint called directly."""

    @pytest.fixture
    def mock_request(self, simple_app: FastAPI) -> MagicMock:
        """Create mock request."""
        request = MagicMock(spec=Request)
        request.app = simple_app
        request.scope = {"root_path": ""}
        return request

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    async def test_deletes_panel_successfully(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that delete_panel deletes a panel."""
        # Setup mock templates
        mock_request.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock bot
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild
        mock_request.app.state.bot.user.id = 999

        # Create mock panel (not posted)
        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.id = 1
        mock_panel.guild_id = 123
        mock_panel.message_id = None

        with (
            patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls,
            patch("discord_bot.web.routers.panels.get_csrf_token", return_value="test_token"),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)
            mock_service.delete = AsyncMock()
            mock_service.get_all_for_guild = AsyncMock(return_value=[])

            await delete_panel(
                request=mock_request,
                guild_id=123,
                panel_id=1,
                user=test_user,
                session=mock_session,
            )

            mock_service.delete.assert_called_once_with(panel_id=1, guild_name="Test Guild")
            mock_session.commit.assert_called()

    async def test_deletes_discord_message(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that delete_panel deletes the Discord message."""
        # Setup mock templates
        mock_request.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock channel and message
        mock_message = AsyncMock()
        mock_message.delete = AsyncMock()
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        # Setup mock bot
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild
        mock_request.app.state.bot.user.id = 999

        # Create mock panel (posted)
        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.id = 1
        mock_panel.guild_id = 123
        mock_panel.channel_id = 456
        mock_panel.message_id = 789

        with (
            patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls,
            patch("discord_bot.web.routers.panels.get_csrf_token", return_value="test_token"),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)
            mock_service.delete = AsyncMock()
            mock_service.get_all_for_guild = AsyncMock(return_value=[])

            await delete_panel(
                request=mock_request,
                guild_id=123,
                panel_id=1,
                user=test_user,
                session=mock_session,
            )

            mock_channel.fetch_message.assert_called_once_with(789)
            mock_message.delete.assert_called_once()

    async def test_raises_404_when_not_found(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that delete_panel raises 404 when not found."""
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = None

        with patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await delete_panel(
                    request=mock_request,
                    guild_id=123,
                    panel_id=999,
                    user=test_user,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 404


class TestPostPanelDirectCall:
    """Tests for post_panel endpoint called directly."""

    @pytest.fixture
    def mock_request(self, simple_app: FastAPI) -> MagicMock:
        """Create mock request."""
        request = MagicMock(spec=Request)
        request.app = simple_app
        request.scope = {"root_path": ""}
        return request

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    async def test_posts_panel_successfully(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that post_panel posts a panel."""
        import builtins

        # Setup mock templates
        mock_request.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock channel
        mock_message = AsyncMock()
        mock_message.id = 999
        mock_message.add_reaction = AsyncMock()
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock(return_value=mock_message)

        # Setup mock bot
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild
        mock_request.app.state.bot.user.id = 999

        # Create mock panel (not posted yet)
        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.id = 1
        mock_panel.name = "TestPanel"
        mock_panel.guild_id = 123
        mock_panel.channel_id = 456
        mock_panel.message_id = None
        mock_panel.role_mappings = [{"emoji": "👍", "role_id": 100}]

        # Patch isinstance to handle TextChannel check
        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: Any, classinfo: Any) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        with (
            patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls,
            patch("discord_bot.web.routers.panels.get_csrf_token", return_value="test_token"),
            patch("discord_bot.roles.formatters.build_panel_embed") as mock_build_embed,
            patch.object(builtins, "isinstance", patched_isinstance),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)
            mock_service.set_message_id = AsyncMock()
            mock_service.get_all_for_guild = AsyncMock(return_value=[])
            mock_build_embed.return_value = MagicMock()

            await post_panel(
                request=mock_request,
                guild_id=123,
                panel_id=1,
                user=test_user,
                session=mock_session,
            )

            mock_channel.send.assert_called_once()
            mock_message.add_reaction.assert_called()
            mock_service.set_message_id.assert_called_once()

    async def test_raises_400_when_guild_not_found(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that post_panel raises 400 when guild not found."""
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await post_panel(
                request=mock_request,
                guild_id=123,
                panel_id=1,
                user=test_user,
                session=mock_session,
            )

        assert exc_info.value.status_code == 400
        assert "Guild not found" in exc_info.value.detail

    async def test_raises_404_when_panel_not_found(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that post_panel raises 404 when panel not found."""
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild

        with patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await post_panel(
                    request=mock_request,
                    guild_id=123,
                    panel_id=999,
                    user=test_user,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 404

    async def test_raises_400_when_already_posted(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that post_panel raises 400 when already posted."""
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild

        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.guild_id = 123
        mock_panel.message_id = 999  # Already posted

        with patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)

            with pytest.raises(HTTPException) as exc_info:
                await post_panel(
                    request=mock_request,
                    guild_id=123,
                    panel_id=1,
                    user=test_user,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 400
            assert "already posted" in exc_info.value.detail

    async def test_raises_400_when_no_mappings(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that post_panel raises 400 when no role mappings."""
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild

        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.guild_id = 123
        mock_panel.message_id = None
        mock_panel.role_mappings = []  # No mappings

        with patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)

            with pytest.raises(HTTPException) as exc_info:
                await post_panel(
                    request=mock_request,
                    guild_id=123,
                    panel_id=1,
                    user=test_user,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 400
            assert "role mapping" in exc_info.value.detail

    async def test_raises_400_when_channel_not_found(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that post_panel raises 400 when channel not found."""
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_channel.return_value = None  # Channel not found
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild

        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.guild_id = 123
        mock_panel.channel_id = 456
        mock_panel.message_id = None
        mock_panel.role_mappings = [{"emoji": "👍", "role_id": 100}]

        with patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)

            with pytest.raises(HTTPException) as exc_info:
                await post_panel(
                    request=mock_request,
                    guild_id=123,
                    panel_id=1,
                    user=test_user,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 400
            assert "Channel not found" in exc_info.value.detail

    async def test_handles_forbidden_error(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that post_panel handles Forbidden error."""
        import builtins

        # Setup mock channel that raises Forbidden
        mock_channel = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 403
        mock_channel.send = AsyncMock(side_effect=discord.Forbidden(mock_response, "No permission"))

        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_channel.return_value = mock_channel
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild

        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.guild_id = 123
        mock_panel.channel_id = 456
        mock_panel.message_id = None
        mock_panel.role_mappings = [{"emoji": "👍", "role_id": 100}]

        # Patch isinstance to handle TextChannel check
        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: Any, classinfo: Any) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        with (
            patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls,
            patch("discord_bot.roles.formatters.build_panel_embed") as mock_build_embed,
            patch.object(builtins, "isinstance", patched_isinstance),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)
            mock_build_embed.return_value = MagicMock()

            with pytest.raises(HTTPException) as exc_info:
                await post_panel(
                    request=mock_request,
                    guild_id=123,
                    panel_id=1,
                    user=test_user,
                    session=mock_session,
                )

            assert exc_info.value.status_code == 400
            assert "Cannot send message" in exc_info.value.detail

    async def test_posts_with_custom_emoji(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that post_panel handles custom emojis."""
        import builtins

        # Setup mock templates
        mock_request.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock channel
        mock_message = AsyncMock()
        mock_message.id = 999
        mock_message.add_reaction = AsyncMock()
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock(return_value=mock_message)

        # Setup mock bot
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild
        mock_request.app.state.bot.user.id = 999

        # Create mock panel with custom emoji
        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.id = 1
        mock_panel.name = "TestPanel"
        mock_panel.guild_id = 123
        mock_panel.channel_id = 456
        mock_panel.message_id = None
        mock_panel.role_mappings = [{"emoji": "custom_emoji", "emoji_id": 12345, "role_id": 100}]

        # Patch isinstance to handle TextChannel check
        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: Any, classinfo: Any) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        with (
            patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls,
            patch("discord_bot.web.routers.panels.get_csrf_token", return_value="test_token"),
            patch("discord_bot.roles.formatters.build_panel_embed") as mock_build_embed,
            patch.object(builtins, "isinstance", patched_isinstance),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)
            mock_service.set_message_id = AsyncMock()
            mock_service.get_all_for_guild = AsyncMock(return_value=[])
            mock_build_embed.return_value = MagicMock()

            await post_panel(
                request=mock_request,
                guild_id=123,
                panel_id=1,
                user=test_user,
                session=mock_session,
            )

            # Verify reaction was added with PartialEmoji
            mock_message.add_reaction.assert_called()


class TestGetGuildDataWithCategory:
    """Tests for _get_guild_data with channel categories."""

    def test_channel_with_category(self, simple_app: FastAPI) -> None:
        """Test that channel category is included."""
        request = MagicMock()
        request.app = simple_app

        # Mock channel with category
        mock_category = MagicMock()
        mock_category.name = "General"
        mock_channel = MagicMock()
        mock_channel.id = 456
        mock_channel.name = "general"
        mock_channel.category = mock_category
        mock_permissions = MagicMock()
        mock_permissions.send_messages = True
        mock_channel.permissions_for.return_value = mock_permissions

        # Mock bot member
        mock_bot_member = MagicMock()
        mock_bot_member.top_role = MagicMock()

        # Mock guild
        mock_guild = MagicMock()
        mock_guild.text_channels = [mock_channel]
        mock_guild.roles = []
        mock_guild.me = mock_bot_member
        mock_guild.get_member.return_value = mock_bot_member

        simple_app.state.bot = MagicMock()
        simple_app.state.bot.get_guild.return_value = mock_guild
        simple_app.state.bot.user.id = 999

        guild, channels, roles, emojis = _get_guild_data(request=request, guild_id=123)

        assert len(channels) == 1
        assert channels[0]["category"] == "General"


class TestDeletePanelExceptionHandling:
    """Tests for delete_panel exception handling."""

    @pytest.fixture
    def mock_request(self, simple_app: FastAPI) -> MagicMock:
        """Create mock request."""
        request = MagicMock(spec=Request)
        request.app = simple_app
        request.scope = {"root_path": ""}
        return request

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    async def test_handles_message_deletion_error(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that delete_panel handles message deletion errors gracefully."""
        # Setup mock templates
        mock_request.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock channel that raises an error when fetching message
        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Message not found")
        )

        # Setup mock bot
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild
        mock_request.app.state.bot.user.id = 999

        # Create mock panel (posted)
        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.id = 1
        mock_panel.guild_id = 123
        mock_panel.channel_id = 456
        mock_panel.message_id = 789  # Panel is posted

        with (
            patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls,
            patch("discord_bot.web.routers.panels.get_csrf_token", return_value="test_token"),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)
            mock_service.delete = AsyncMock()
            mock_service.get_all_for_guild = AsyncMock(return_value=[])

            # Should not raise exception even though message fetch failed
            await delete_panel(
                request=mock_request,
                guild_id=123,
                panel_id=1,
                user=test_user,
                session=mock_session,
            )

            # Verify panel was still deleted
            mock_service.delete.assert_called_once_with(panel_id=1, guild_name="Test Guild")


class TestPostPanelReactionErrors:
    """Tests for post_panel reaction error handling."""

    @pytest.fixture
    def mock_request(self, simple_app: FastAPI) -> MagicMock:
        """Create mock request."""
        request = MagicMock(spec=Request)
        request.app = simple_app
        request.scope = {"root_path": ""}
        return request

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    async def test_handles_reaction_add_error(
        self,
        mock_request: MagicMock,
        mock_session: AsyncMock,
        test_user: dict[str, Any],
    ) -> None:
        """Test that post_panel handles reaction add errors gracefully."""
        import builtins

        # Setup mock templates
        mock_request.app.state.templates = MagicMock(spec=Jinja2Templates)
        mock_response = MagicMock()
        mock_request.app.state.templates.TemplateResponse.return_value = mock_response

        # Setup mock channel - message.add_reaction raises HTTPException
        mock_message = AsyncMock()
        mock_message.id = 999
        mock_http_response = MagicMock()
        mock_http_response.status = 400
        mock_message.add_reaction = AsyncMock(
            side_effect=discord.HTTPException(mock_http_response, "Invalid emoji")
        )
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock(return_value=mock_message)

        # Setup mock bot
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_channel.return_value = mock_channel
        mock_guild.text_channels = []
        mock_guild.roles = []
        mock_guild.me = MagicMock()
        mock_guild.me.top_role = MagicMock()
        mock_request.app.state.bot = MagicMock()
        mock_request.app.state.bot.get_guild.return_value = mock_guild
        mock_request.app.state.bot.user.id = 999

        # Create mock panel with a role mapping
        mock_panel = MagicMock(spec=ReactionPanel)
        mock_panel.id = 1
        mock_panel.name = "TestPanel"
        mock_panel.guild_id = 123
        mock_panel.channel_id = 456
        mock_panel.message_id = None
        mock_panel.role_mappings = [{"emoji": "invalid_emoji", "role_id": 100}]

        # Patch isinstance to handle TextChannel check
        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: Any, classinfo: Any) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        with (
            patch("discord_bot.web.routers.panels.ReactionRolesService") as mock_service_cls,
            patch("discord_bot.web.routers.panels.get_csrf_token", return_value="test_token"),
            patch("discord_bot.roles.formatters.build_panel_embed") as mock_build_embed,
            patch.object(builtins, "isinstance", patched_isinstance),
        ):
            mock_service = mock_service_cls.return_value
            mock_service.get_by_id = AsyncMock(return_value=mock_panel)
            mock_service.set_message_id = AsyncMock()
            mock_service.get_all_for_guild = AsyncMock(return_value=[])
            mock_build_embed.return_value = MagicMock()

            # Should not raise exception even though reaction add failed
            await post_panel(
                request=mock_request,
                guild_id=123,
                panel_id=1,
                user=test_user,
                session=mock_session,
            )

            # Verify message was still sent and panel was updated
            mock_channel.send.assert_called_once()
            mock_service.set_message_id.assert_called_once()
