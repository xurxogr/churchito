"""Tests for RolesCog."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from sqlalchemy import select

from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.database import DatabaseService
from discord_bot.common.utils.command_sync import CommandSyncError
from discord_bot.roles.cog import RolesCog
from discord_bot.roles.config import COG_NAME, ROLES_CONFIG_SCHEMA
from discord_bot.roles.enums import ConfigKey
from discord_bot.roles.models import PanelType, ReactionPanel
from discord_bot.roles.service import ReactionRolesService


async def enable_cog_for_guild(db: DatabaseService, guild_id: int) -> None:
    """Enable the roles cog for a guild."""
    async with db.session() as session:
        config_service = ConfigService(session)
        await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
        await session.commit()


@pytest.fixture
def mock_discord_bot(test_database: DatabaseService) -> Any:
    """Create mock of the bot with database."""
    bot: Any = MagicMock()
    bot.database = test_database
    bot.guilds = []
    bot.add_view = MagicMock()
    bot.get_guild = MagicMock(return_value=None)
    bot.get_cog = MagicMock(return_value=None)
    bot.wait_until_ready = AsyncMock()
    bot.tree = MagicMock()
    bot.tree.add_command = MagicMock()
    bot.tree.get_command = MagicMock(return_value=None)
    bot.tree.remove_command = MagicMock()
    bot.tree.sync = AsyncMock()
    return bot


@pytest.fixture
def roles_cog(mock_discord_bot: Any) -> RolesCog:
    """Create cog instance for tests."""
    # Register schema so defaults are available
    schema_service = get_config_schema_service()
    if not schema_service.get_schema(COG_NAME):
        schema_service.register_schema(ROLES_CONFIG_SCHEMA)
    return RolesCog(mock_discord_bot)


@pytest.fixture
def mock_guild() -> MagicMock:
    """Create mock of a guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.name = "Test Guild"
    guild.get_member = MagicMock(return_value=None)
    guild.get_role = MagicMock(return_value=None)
    guild.get_channel = MagicMock(return_value=None)
    return guild


@pytest.fixture
def mock_role() -> MagicMock:
    """Create mock of a Discord role."""
    role = MagicMock(spec=discord.Role)
    role.id = 100
    role.name = "TestRole"
    role.mention = "<@&100>"
    return role


@pytest.fixture
def mock_role2() -> MagicMock:
    """Create mock of a second Discord role."""
    role = MagicMock(spec=discord.Role)
    role.id = 200
    role.name = "TestRole2"
    role.mention = "<@&200>"
    return role


@pytest.fixture
def mock_member(mock_guild: MagicMock, mock_role: MagicMock) -> MagicMock:
    """Create mock of a Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 111222333
    member.bot = False
    member.display_name = "TestUser"
    member.mention = "<@111222333>"
    member.nick = None
    member.guild = mock_guild
    member.guild_permissions = MagicMock()
    member.guild_permissions.manage_guild = True
    member.roles = [mock_role]
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    member.send = AsyncMock()
    return member


@pytest.fixture
def mock_interaction(mock_guild: MagicMock, mock_member: MagicMock) -> MagicMock:
    """Create mock of a Discord interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = mock_guild
    interaction.user = mock_member
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.namespace = MagicMock()
    return interaction


# ===== COG METHOD TESTS =====


class TestGetLockedOptions:
    """Tests for get_locked_options."""

    def test_returns_empty_dict(self, roles_cog: RolesCog) -> None:
        """Test that returns empty dict."""
        result = roles_cog.get_locked_options()
        assert result == {}


class TestIsCogEnabled:
    """Tests for _is_cog_enabled."""

    async def test_cog_enabled(self, roles_cog: RolesCog, test_database: DatabaseService) -> None:
        """Test when cog is enabled."""
        guild_id = 123

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await session.commit()

        result = await roles_cog._is_cog_enabled(guild_id)
        assert result is True

    async def test_cog_disabled(self, roles_cog: RolesCog, test_database: DatabaseService) -> None:
        """Test when cog is disabled."""
        guild_id = 456

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name=COG_NAME, enabled=False
            )
            await session.commit()

        result = await roles_cog._is_cog_enabled(guild_id)
        assert result is False


class TestGetConfig:
    """Tests for _get_config."""

    async def test_returns_config_dict(
        self, roles_cog: RolesCog, test_database: DatabaseService
    ) -> None:
        """Test that returns a configuration dictionary."""
        guild_id = 123
        result = await roles_cog._get_config(guild_id)
        assert isinstance(result, dict)

    async def test_returns_saved_config(
        self, roles_cog: RolesCog, test_database: DatabaseService
    ) -> None:
        """Test that returns saved configuration."""
        guild_id = 789

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[100, 200],
            )
            await session.commit()

        result = await roles_cog._get_config(guild_id)
        assert result.get(ConfigKey.MANAGE_ROLES) == [100, 200]


# ===== AUTOCOMPLETE TESTS =====


class TestPanelAutocomplete:
    """Tests for panel_autocomplete."""

    async def test_returns_empty_without_guild(
        self, roles_cog: RolesCog, mock_interaction: MagicMock
    ) -> None:
        """Test that returns empty when not in guild."""
        mock_interaction.guild = None
        result = await roles_cog.panel_autocomplete(mock_interaction, "")
        assert result == []

    async def test_returns_panel_names(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns panel names for guild."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=guild_id,
                channel_id=456,
                name="ColorRoles",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await service.create_panel(
                guild_id=guild_id,
                channel_id=457,
                name="GameRoles",
                panel_type=PanelType.EXCLUSIVE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

        result = await roles_cog.panel_autocomplete(mock_interaction, "")
        assert len(result) == 2
        names = [c.name for c in result]
        assert "ColorRoles" in names
        assert "GameRoles" in names

    async def test_returns_matching_panels(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns only matching panel names."""
        guild_id = mock_interaction.guild.id

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=guild_id,
                channel_id=456,
                name="ColorRoles",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await service.create_panel(
                guild_id=guild_id,
                channel_id=457,
                name="GameRoles",
                panel_type=PanelType.EXCLUSIVE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

        result = await roles_cog.panel_autocomplete(mock_interaction, "Col")
        assert len(result) == 1
        assert result[0].name == "ColorRoles"


# ===== REACTION EVENT HANDLER TESTS =====


class TestOnRawReactionAdd:
    """Tests for on_raw_reaction_add event handler."""

    def _create_mock_payload(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        user_id: int,
        emoji_name: str = "👍",
        emoji_id: int | None = None,
    ) -> MagicMock:
        """Create a mock RawReactionActionEvent payload."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = guild_id
        payload.channel_id = channel_id
        payload.message_id = message_id
        payload.user_id = user_id

        emoji = MagicMock(spec=discord.PartialEmoji)
        emoji.name = emoji_name
        emoji.id = emoji_id
        emoji.is_custom_emoji.return_value = emoji_id is not None
        payload.emoji = emoji

        return payload

    async def test_ignores_dm_reactions(self, roles_cog: RolesCog) -> None:
        """Test that DM reactions (no guild_id) are ignored."""
        payload = self._create_mock_payload(
            guild_id=0,  # No guild
            channel_id=456,
            message_id=789,
            user_id=123,
        )
        payload.guild_id = None

        # Should not raise any errors
        await roles_cog.on_raw_reaction_add(payload)

    async def test_ignores_bot_user_reactions(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that reactions from the bot itself are ignored."""
        roles_cog.bot.user.id = 999888777  # Set bot user ID
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=789,
            user_id=999888777,  # Same as bot user ID
        )

        # Should not raise any errors - reaction from bot itself is ignored
        await roles_cog.on_raw_reaction_add(payload)

    async def test_ignores_bot_reactions(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that bot reactions are ignored."""
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)

        bot_member = MagicMock(spec=discord.Member)
        bot_member.bot = True
        mock_guild.get_member.return_value = bot_member

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=789,
            user_id=123,
        )

        # Should not raise any errors
        await roles_cog.on_raw_reaction_add(payload)

    async def test_ignores_non_panel_messages(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that reactions on non-panel messages are ignored."""
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        mock_guild.get_member.return_value = mock_member

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=99999,  # Not a panel
            user_id=mock_member.id,
        )

        # Should not raise any errors
        await roles_cog.on_raw_reaction_add(payload)
        # Member should not have role changes
        mock_member.add_roles.assert_not_called()

    async def test_toggle_panel_adds_role(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that reacting to toggle panel adds role."""
        # Setup bot
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777  # Bot user ID (different from member)
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role

        # Enable cog for this guild
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Create a panel with a mapping
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": mock_role.id}],
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        # Member doesn't have the role yet
        mock_member.roles = []

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=mock_member.id,
            emoji_name="👍",
        )

        await roles_cog.on_raw_reaction_add(payload)

        # Role should be added (with reason parameter)
        mock_member.add_roles.assert_called_once()
        assert mock_member.add_roles.call_args[0][0] == mock_role
        assert "TestPanel" in mock_member.add_roles.call_args[1]["reason"]


class TestOnRawReactionRemove:
    """Tests for on_raw_reaction_remove event handler."""

    def _create_mock_payload(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        user_id: int,
        emoji_name: str = "👍",
        emoji_id: int | None = None,
    ) -> MagicMock:
        """Create a mock RawReactionActionEvent payload."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = guild_id
        payload.channel_id = channel_id
        payload.message_id = message_id
        payload.user_id = user_id

        emoji = MagicMock(spec=discord.PartialEmoji)
        emoji.name = emoji_name
        emoji.id = emoji_id
        emoji.is_custom_emoji.return_value = emoji_id is not None
        payload.emoji = emoji

        return payload

    async def test_ignores_dm_reactions(self, roles_cog: RolesCog) -> None:
        """Test that DM reactions are ignored."""
        payload = self._create_mock_payload(
            guild_id=0,
            channel_id=456,
            message_id=789,
            user_id=123,
        )
        payload.guild_id = None

        await roles_cog.on_raw_reaction_remove(payload)

    async def test_ignores_bot_user_reactions(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that reactions from the bot itself are ignored."""
        roles_cog.bot.user.id = 999888777  # Set bot user ID
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=789,
            user_id=999888777,  # Same as bot user ID
        )

        # Should not raise any errors
        await roles_cog.on_raw_reaction_remove(payload)

    async def test_ignores_bot_reactions(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that bot reactions are ignored."""
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)

        bot_member = MagicMock(spec=discord.Member)
        bot_member.bot = True
        mock_guild.get_member.return_value = bot_member

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=789,
            user_id=123,
        )

        await roles_cog.on_raw_reaction_remove(payload)

    async def test_toggle_panel_removes_role(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that unreacting from toggle panel removes role."""
        # Setup bot
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role

        # Enable cog for this guild
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Create a panel with a mapping
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": mock_role.id}],
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        # Member has the role
        mock_member.roles = [mock_role]

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=mock_member.id,
            emoji_name="👍",
        )

        await roles_cog.on_raw_reaction_remove(payload)

        # Role should be removed (with reason parameter)
        mock_member.remove_roles.assert_called_once()
        assert mock_member.remove_roles.call_args[0][0] == mock_role
        assert "TestPanel" in mock_member.remove_roles.call_args[1]["reason"]


class TestVerifyPanelBehavior:
    """Tests for verify panel specific behavior."""

    def _create_mock_payload(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        user_id: int,
        emoji_name: str = "👍",
    ) -> MagicMock:
        """Create a mock RawReactionActionEvent payload."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = guild_id
        payload.channel_id = channel_id
        payload.message_id = message_id
        payload.user_id = user_id

        emoji = MagicMock(spec=discord.PartialEmoji)
        emoji.name = emoji_name
        emoji.id = None
        emoji.is_custom_emoji.return_value = False
        payload.emoji = emoji

        return payload

    async def test_verify_panel_adds_role_and_removes_reaction(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that verify panel adds role and removes user's reaction."""
        # Setup bot
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role

        # Enable cog for this guild
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Create mock channel and message
        mock_message = MagicMock(spec=discord.Message)
        mock_message.remove_reaction = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.get_partial_message = MagicMock(return_value=mock_message)
        mock_guild.get_channel.return_value = mock_channel

        # Create a verify panel
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="VerifyPanel",
                panel_type=PanelType.VERIFY,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": mock_role.id}],
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        mock_member.roles = []

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=mock_member.id,
            emoji_name="👍",
        )

        await roles_cog.on_raw_reaction_add(payload)

        # Role should be added (with reason parameter mentioning verify)
        mock_member.add_roles.assert_called_once()
        assert mock_member.add_roles.call_args[0][0] == mock_role
        assert "VerifyPanel" in mock_member.add_roles.call_args[1]["reason"]
        assert "verify" in mock_member.add_roles.call_args[1]["reason"]
        # Reaction should be removed
        mock_message.remove_reaction.assert_called_once()


class TestExclusivePanelBehavior:
    """Tests for exclusive panel specific behavior."""

    def _create_mock_payload(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        user_id: int,
        emoji_name: str = "👍",
    ) -> MagicMock:
        """Create a mock RawReactionActionEvent payload."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = guild_id
        payload.channel_id = channel_id
        payload.message_id = message_id
        payload.user_id = user_id

        emoji = MagicMock(spec=discord.PartialEmoji)
        emoji.name = emoji_name
        emoji.id = None
        emoji.is_custom_emoji.return_value = False
        payload.emoji = emoji

        return payload

    async def test_exclusive_panel_removes_other_roles(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        mock_role2: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that exclusive panel removes other panel roles when selecting new one."""
        # Setup bot
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member

        # Enable cog for this guild
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Return the appropriate role based on ID
        def get_role_side_effect(role_id: int) -> MagicMock | None:
            if role_id == 100:
                return mock_role
            if role_id == 200:
                return mock_role2
            return None

        mock_guild.get_role.side_effect = get_role_side_effect

        # Create an exclusive panel with two roles
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="ExclusivePanel",
                panel_type=PanelType.EXCLUSIVE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[
                    {"emoji": "👍", "role_id": 100},
                    {"emoji": "👎", "role_id": 200},
                ],
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        # Member already has role 100
        mock_member.roles = [mock_role]

        # Select role 200 (👎)
        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=mock_member.id,
            emoji_name="👎",
        )

        await roles_cog.on_raw_reaction_add(payload)

        # Previous role should be removed, new role added (with reason parameters)
        mock_member.remove_roles.assert_called_once()
        assert mock_member.remove_roles.call_args[0][0] == mock_role
        assert "ExclusivePanel" in mock_member.remove_roles.call_args[1]["reason"]
        assert "exclusive" in mock_member.remove_roles.call_args[1]["reason"]

        mock_member.add_roles.assert_called_once()
        assert mock_member.add_roles.call_args[0][0] == mock_role2
        assert "ExclusivePanel" in mock_member.add_roles.call_args[1]["reason"]


class TestRequiredRolesCheck:
    """Tests for required roles checking."""

    def _create_mock_payload(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        user_id: int,
        emoji_name: str = "👍",
    ) -> MagicMock:
        """Create a mock RawReactionActionEvent payload."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = guild_id
        payload.channel_id = channel_id
        payload.message_id = message_id
        payload.user_id = user_id

        emoji = MagicMock(spec=discord.PartialEmoji)
        emoji.name = emoji_name
        emoji.id = None
        emoji.is_custom_emoji.return_value = False
        payload.emoji = emoji

        return payload

    async def test_user_without_required_role_is_rejected(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that user without required role cannot use panel."""
        # Setup bot
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role

        # Enable cog for this guild
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Create mock channel and message for reaction removal
        mock_message = MagicMock(spec=discord.Message)
        mock_message.remove_reaction = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.get_partial_message = MagicMock(return_value=mock_message)
        mock_guild.get_channel.return_value = mock_channel

        # Create a panel with required roles
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="RestrictedPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 100}],
                required_roles=[999],  # User doesn't have this role
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        # User has role 100, not 999
        mock_member.roles = [mock_role]

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=mock_member.id,
            emoji_name="👍",
        )

        await roles_cog.on_raw_reaction_add(payload)

        # Role should NOT be added
        mock_member.add_roles.assert_not_called()
        # Reaction should be removed
        mock_message.remove_reaction.assert_called()

    async def test_required_role_missing_sends_dm(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that user without required role gets a DM if configured."""
        # Setup bot
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role

        # Enable cog for this guild
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Create mock channel and message for reaction removal
        mock_message = MagicMock(spec=discord.Message)
        mock_message.remove_reaction = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.get_partial_message = MagicMock(return_value=mock_message)
        mock_guild.get_channel.return_value = mock_channel

        # Setup DM
        mock_member.send = AsyncMock()

        # Create a panel with required roles and dm_on_missing_role enabled
        async with test_database.session() as session:
            # Configure the DM message template
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.DM_MISSING_ROLE_MSG,
                value="You need the required roles to use this panel.",
            )

            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="RestrictedPanelWithDM",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 100}],
                required_roles=[999],  # User doesn't have this role
                dm_on_missing_role=True,  # Enable DM on missing role
            )
            await service.set_message_id(
                panel_id=panel.id, message_id=1000, guild_name="Test Guild"
            )
            await session.commit()

        # User has role 100, not 999
        mock_member.roles = [mock_role]

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=1000,
            user_id=mock_member.id,
            emoji_name="👍",
        )

        await roles_cog.on_raw_reaction_add(payload)

        # Role should NOT be added
        mock_member.add_roles.assert_not_called()
        # DM should be sent
        mock_member.send.assert_called_once()


class TestUserLockManager:
    """Tests for the per-user lock pool."""

    async def test_lock_evicted_after_reaction(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that the per-user lock entry is removed after handling a reaction."""
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member

        await enable_cog_for_guild(test_database, mock_guild.id)

        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = mock_guild.id
        payload.channel_id = 456
        payload.message_id = 99999  # Not a panel
        payload.user_id = mock_member.id
        emoji = MagicMock(spec=discord.PartialEmoji)
        emoji.name = "👍"
        emoji.id = None
        emoji.is_custom_emoji.return_value = False
        payload.emoji = emoji

        await roles_cog.on_raw_reaction_add(payload)

        assert len(roles_cog._user_locks) == 0


class TestReactionCaching:
    """Tests for the per-guild enabled/panel caches used on the reaction hot path."""

    def _payload(self, guild_id: int, message_id: int, user_id: int) -> MagicMock:
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = guild_id
        payload.channel_id = 456
        payload.message_id = message_id
        payload.user_id = user_id
        emoji = MagicMock(spec=discord.PartialEmoji)
        emoji.name = "👍"
        emoji.id = None
        emoji.is_custom_emoji.return_value = False
        payload.emoji = emoji
        return payload

    async def _post_panel(
        self, test_database: DatabaseService, guild_id: int, role_id: int, message_id: int
    ) -> None:
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=guild_id,
                channel_id=456,
                name="CachedPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": role_id}],
            )
            await service.set_message_id(
                panel_id=panel.id, message_id=message_id, guild_name="Test Guild"
            )
            await session.commit()

    async def test_non_panel_reactions_hit_database_once_per_guild(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that repeated reactions on non-panel messages do not open DB sessions."""
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member
        await enable_cog_for_guild(test_database, mock_guild.id)

        with patch.object(test_database, "session", wraps=test_database.session) as session_factory:
            await roles_cog.on_raw_reaction_add(self._payload(mock_guild.id, 1, mock_member.id))
            warm_up_sessions = session_factory.call_count

            await roles_cog.on_raw_reaction_add(self._payload(mock_guild.id, 2, mock_member.id))
            await roles_cog.on_raw_reaction_remove(self._payload(mock_guild.id, 3, mock_member.id))

        assert warm_up_sessions >= 1
        assert session_factory.call_count == warm_up_sessions
        mock_member.add_roles.assert_not_called()

    async def test_disabled_guild_reactions_do_not_query_panels(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that a disabled guild is cached and later reactions skip the DB entirely."""
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777

        with patch.object(test_database, "session", wraps=test_database.session) as session_factory:
            await roles_cog.on_raw_reaction_add(self._payload(mock_guild.id, 1, mock_member.id))
            first = session_factory.call_count
            await roles_cog.on_raw_reaction_add(self._payload(mock_guild.id, 2, mock_member.id))

        assert first == 1
        assert session_factory.call_count == 1

    async def test_invalidate_panel_cache_makes_new_panel_visible(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that a panel posted after the cache warmed up is seen once invalidated."""
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role
        mock_member.roles = []
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Warm the panel cache with a non-panel reaction
        await roles_cog.on_raw_reaction_add(self._payload(mock_guild.id, 1, mock_member.id))

        await self._post_panel(test_database, mock_guild.id, mock_role.id, message_id=999)
        roles_cog.invalidate_panel_cache(mock_guild.id)

        await roles_cog.on_raw_reaction_add(self._payload(mock_guild.id, 999, mock_member.id))

        mock_member.add_roles.assert_called_once()

    async def test_on_cog_toggled_invalidates_enabled_cache(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that enabling the cog after a cached 'disabled' takes effect immediately."""
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role
        mock_member.roles = []
        await self._post_panel(test_database, mock_guild.id, mock_role.id, message_id=999)

        # Cog disabled: reaction ignored and 'disabled' cached
        await roles_cog.on_raw_reaction_add(self._payload(mock_guild.id, 999, mock_member.id))
        mock_member.add_roles.assert_not_called()

        await enable_cog_for_guild(test_database, mock_guild.id)
        with (
            patch.object(roles_cog, "_register_guild_commands", new=AsyncMock()),
            patch.object(roles_cog, "_sync_guild_commands", new=AsyncMock()),
        ):
            await roles_cog.on_cog_toggled(mock_guild, enabled=True)

        await roles_cog.on_raw_reaction_add(self._payload(mock_guild.id, 999, mock_member.id))
        mock_member.add_roles.assert_called_once()

    async def test_on_guild_remove_drops_cached_state(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that leaving a guild drops its cache entries."""
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member
        await enable_cog_for_guild(test_database, mock_guild.id)

        await roles_cog.on_raw_reaction_add(self._payload(mock_guild.id, 1, mock_member.id))
        assert len(roles_cog._enabled_cache) == 1
        assert len(roles_cog._panel_messages_cache) == 1

        with patch.object(roles_cog, "_unregister_guild_commands", new=AsyncMock()):
            await roles_cog.on_guild_remove(mock_guild)

        assert len(roles_cog._enabled_cache) == 0
        assert len(roles_cog._panel_messages_cache) == 0


# ===== COMMAND HANDLER TESTS =====


class TestParseEmoji:
    """Tests for _parse_emoji method."""

    def test_unicode_emoji(self, roles_cog: RolesCog) -> None:
        """Test parsing unicode emoji."""
        name, emoji_id = roles_cog._parse_emoji("👍")
        assert name == "👍"
        assert emoji_id is None

    def test_unicode_emoji_with_spaces(self, roles_cog: RolesCog) -> None:
        """Test parsing unicode emoji with surrounding spaces."""
        name, emoji_id = roles_cog._parse_emoji("  🎉  ")
        assert name == "🎉"
        assert emoji_id is None

    def test_custom_emoji(self, roles_cog: RolesCog) -> None:
        """Test parsing custom emoji."""
        name, emoji_id = roles_cog._parse_emoji("<:test:123456789>")
        assert name == "test"
        assert emoji_id == 123456789

    def test_animated_custom_emoji(self, roles_cog: RolesCog) -> None:
        """Test parsing animated custom emoji."""
        name, emoji_id = roles_cog._parse_emoji("<a:animated:987654321>")
        assert name == "animated"
        assert emoji_id == 987654321


class TestHandleCreate:
    """Tests for _handle_create command handler."""

    async def test_returns_if_no_guild(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test that handler returns early if not in guild."""
        mock_interaction.guild = None
        await roles_cog._handle_create(mock_interaction, "TestPanel", MagicMock(), "toggle")
        mock_interaction.response.send_message.assert_not_called()

    async def test_returns_if_user_not_member(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler returns if user is not a Member."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = MagicMock(spec=discord.User)  # Not Member
        await enable_cog_for_guild(test_database, mock_guild.id)

        await roles_cog._handle_create(mock_interaction, "TestPanel", MagicMock(), "toggle")
        mock_interaction.response.send_message.assert_not_called()

    async def test_rejects_without_permission(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler rejects user without permission."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = []  # No roles
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set manage_roles to require a role the user doesn't have
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[999],  # User doesn't have this role
            )
            await session.commit()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456

        await roles_cog._handle_create(mock_interaction, "TestPanel", mock_channel, "toggle")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True

    async def test_rejects_name_too_long(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler rejects name longer than 100 chars."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            await session.commit()

        mock_channel = MagicMock(spec=discord.TextChannel)
        long_name = "A" * 101

        await roles_cog._handle_create(mock_interaction, long_name, mock_channel, "toggle")

        mock_interaction.response.send_message.assert_called_once()
        assert "100 characters" in mock_interaction.response.send_message.call_args[0][0]

    async def test_rejects_duplicate_name(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler rejects duplicate panel name."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create existing panel with same name
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456

        await roles_cog._handle_create(mock_interaction, "TestPanel", mock_channel, "toggle")

        mock_interaction.response.send_message.assert_called_once()
        assert "already exists" in mock_interaction.response.send_message.call_args[0][0]

    async def test_creates_panel_successfully(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler creates panel successfully."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            await session.commit()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456
        mock_channel.mention = "<#456>"

        await roles_cog._handle_create(mock_interaction, "NewPanel", mock_channel, "toggle")

        mock_interaction.response.send_message.assert_called_once()
        assert "created" in mock_interaction.response.send_message.call_args[0][0]

    async def test_concurrent_creates_leave_a_single_panel(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that two overlapping creates with the same name leave one panel."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            await session.commit()

        second_interaction = MagicMock(spec=discord.Interaction)
        second_interaction.guild = mock_guild
        second_interaction.user = mock_member
        second_interaction.response = MagicMock()
        second_interaction.response.send_message = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456
        mock_channel.mention = "<#456>"

        # Yield on the duplicate check so both commands look before either creates
        original_lookup = ReactionRolesService.get_by_name

        async def slow_lookup(self: ReactionRolesService, guild_id: int, name: str) -> Any:
            await asyncio.sleep(0.01)
            return await original_lookup(self, guild_id=guild_id, name=name)

        with patch.object(ReactionRolesService, "get_by_name", slow_lookup):
            await asyncio.gather(
                roles_cog._handle_create(mock_interaction, "Twice", mock_channel, "toggle"),
                roles_cog._handle_create(second_interaction, "Twice", mock_channel, "toggle"),
            )

        replies = [
            interaction.response.send_message.call_args[0][0]
            for interaction in (mock_interaction, second_interaction)
        ]
        assert sum("already exists" in reply for reply in replies) == 1

        async with test_database.session() as session:
            result = await session.execute(
                select(ReactionPanel).where(
                    ReactionPanel.guild_id == mock_guild.id, ReactionPanel.name == "Twice"
                )
            )
            assert len(result.scalars().all()) == 1


class TestHandleList:
    """Tests for _handle_list command handler."""

    async def test_returns_if_no_guild(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test that handler returns early if not in guild."""
        mock_interaction.guild = None
        await roles_cog._handle_list(mock_interaction)
        mock_interaction.response.send_message.assert_not_called()

    async def test_shows_no_panels_message(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        """Test that handler shows message when no panels exist."""
        mock_interaction.guild = mock_guild

        await roles_cog._handle_list(mock_interaction)

        mock_interaction.response.send_message.assert_called_once()
        assert "No reaction role panels" in mock_interaction.response.send_message.call_args[0][0]

    async def test_shows_panels_list(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler shows list of panels."""
        mock_interaction.guild = mock_guild
        mock_guild.get_channel.return_value = None

        # Create a panel
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

        await roles_cog._handle_list(mock_interaction)

        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        assert "embed" in call_kwargs


class TestHandleInfo:
    """Tests for _handle_info command handler."""

    async def test_returns_if_no_guild(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test that handler returns early if not in guild."""
        mock_interaction.guild = None
        await roles_cog._handle_info(mock_interaction, "TestPanel")
        mock_interaction.response.send_message.assert_not_called()

    async def test_shows_not_found(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler shows not found message."""
        mock_interaction.guild = mock_guild
        await enable_cog_for_guild(test_database, mock_guild.id)

        await roles_cog._handle_info(mock_interaction, "NonExistent")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True

    async def test_shows_panel_info(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler shows panel info."""
        mock_interaction.guild = mock_guild
        mock_guild.get_channel.return_value = None
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = None

        # Create a panel
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=mock_member.id,
                guild_name="Test Guild",
            )
            await session.commit()

        await roles_cog._handle_info(mock_interaction, "TestPanel")

        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        assert "embed" in call_kwargs


class TestHandleAddRole:
    """Tests for _handle_add_role command handler."""

    async def test_returns_if_no_guild(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_role: MagicMock,
    ) -> None:
        """Test that handler returns early if not in guild."""
        mock_interaction.guild = None
        await roles_cog._handle_add_role(mock_interaction, "TestPanel", "👍", mock_role, None)
        mock_interaction.response.send_message.assert_not_called()

    async def test_rejects_without_permission(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler rejects user without permission."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = []  # No roles
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set manage_roles to require a role the user doesn't have
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[999],
            )
            await session.commit()

        await roles_cog._handle_add_role(mock_interaction, "TestPanel", "👍", mock_role, None)

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True

    async def test_shows_not_found_for_missing_panel(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler shows not found for missing panel."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            await session.commit()

        await roles_cog._handle_add_role(mock_interaction, "NonExistent", "👍", mock_role, None)

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True


class TestHandleRemoveRole:
    """Tests for _handle_remove_role command handler."""

    async def test_returns_if_no_guild(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test that handler returns early if not in guild."""
        mock_interaction.guild = None
        await roles_cog._handle_remove_role(mock_interaction, "TestPanel", "👍")
        mock_interaction.response.send_message.assert_not_called()


class TestHandlePost:
    """Tests for _handle_post command handler."""

    async def test_returns_if_no_guild(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test that handler returns early if not in guild."""
        mock_interaction.guild = None
        await roles_cog._handle_post(mock_interaction, "TestPanel")
        mock_interaction.response.send_message.assert_not_called()

    async def test_shows_not_found_for_missing_panel(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler shows not found for missing panel."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            await session.commit()

        await roles_cog._handle_post(mock_interaction, "NonExistent")

        mock_interaction.response.send_message.assert_called_once()


class TestHandleRefresh:
    """Tests for _handle_refresh command handler."""

    async def test_returns_if_no_guild(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test that handler returns early if not in guild."""
        mock_interaction.guild = None
        await roles_cog._handle_refresh(mock_interaction, "TestPanel")
        mock_interaction.response.send_message.assert_not_called()


class TestPanelEditedAudit:
    """Tests for the panel-edited audit notification."""

    AUDIT_CHANNEL_ID = 999

    async def _setup_config(
        self,
        test_database: DatabaseService,
        guild_id: int,
        manage_role_id: int,
        audit_enabled: bool = True,
    ) -> None:
        """Enable the cog and configure permission + audit channel."""
        await enable_cog_for_guild(test_database, guild_id)
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[manage_role_id],
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_CHANNEL,
                value=self.AUDIT_CHANNEL_ID,
            )
            await config_service.set_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_PANEL_EDITED,
                value=audit_enabled,
            )
            await session.commit()

    def _setup_audit_channel(self, mock_guild: MagicMock) -> MagicMock:
        """Make the guild return an audit channel mock for AUDIT_CHANNEL_ID."""
        audit_channel = MagicMock(spec=discord.TextChannel)
        audit_channel.send = AsyncMock()

        def get_channel(channel_id: int) -> MagicMock | None:
            if channel_id == self.AUDIT_CHANNEL_ID:
                return audit_channel
            return None

        mock_guild.get_channel.side_effect = get_channel
        return audit_channel

    async def test_add_role_sends_edited_audit(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that adding a role mapping sends the panel-edited audit message."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await self._setup_config(test_database, mock_guild.id, mock_role.id)
        audit_channel = self._setup_audit_channel(mock_guild)

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

        await roles_cog._handle_add_role(mock_interaction, "TestPanel", "👍", mock_role, None)

        audit_channel.send.assert_called_once()
        sent = audit_channel.send.call_args[0][0]
        assert "TestPanel" in sent
        assert mock_member.mention in sent
        assert "{" not in sent

    async def test_add_role_no_audit_when_disabled(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that no audit message is sent when the toggle is disabled."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await self._setup_config(test_database, mock_guild.id, mock_role.id, audit_enabled=False)
        audit_channel = self._setup_audit_channel(mock_guild)

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

        await roles_cog._handle_add_role(mock_interaction, "TestPanel", "👍", mock_role, None)

        audit_channel.send.assert_not_called()

    async def test_remove_role_sends_edited_audit(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that removing a role mapping sends the panel-edited audit message."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await self._setup_config(test_database, mock_guild.id, mock_role.id)
        audit_channel = self._setup_audit_channel(mock_guild)

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await service.add_mapping(
                panel_id=panel.id,
                emoji="👍",
                emoji_id=None,
                role_id=mock_role.id,
                display_name=None,
                guild_name="Test Guild",
            )
            await session.commit()

        await roles_cog._handle_remove_role(mock_interaction, "TestPanel", "👍")

        audit_channel.send.assert_called_once()
        sent = audit_channel.send.call_args[0][0]
        assert "TestPanel" in sent
        assert mock_member.mention in sent

    async def test_refresh_sends_edited_audit(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that refreshing a posted panel sends the panel-edited audit message."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await self._setup_config(test_database, mock_guild.id, mock_role.id)
        audit_channel = self._setup_audit_channel(mock_guild)

        panel_channel = MagicMock(spec=discord.TextChannel)
        panel_channel.mention = "<#456>"
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        mock_message.clear_reactions = AsyncMock()
        panel_channel.fetch_message = AsyncMock(return_value=mock_message)

        def get_channel(channel_id: int) -> MagicMock | None:
            if channel_id == self.AUDIT_CHANNEL_ID:
                return audit_channel
            if channel_id == 456:
                return panel_channel
            return None

        mock_guild.get_channel.side_effect = get_channel

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await service.set_message_id(
                panel_id=panel.id,
                message_id=555,
                guild_name="Test Guild",
            )
            await session.commit()

        await roles_cog._handle_refresh(mock_interaction, "TestPanel")

        audit_channel.send.assert_called_once()
        sent = audit_channel.send.call_args[0][0]
        assert "TestPanel" in sent
        assert mock_member.mention in sent

    async def test_refresh_no_audit_when_message_missing(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that a failed refresh does not send the audit message."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await self._setup_config(test_database, mock_guild.id, mock_role.id)
        audit_channel = self._setup_audit_channel(mock_guild)

        panel_channel = MagicMock(spec=discord.TextChannel)
        panel_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "not found")
        )

        def get_channel(channel_id: int) -> MagicMock | None:
            if channel_id == self.AUDIT_CHANNEL_ID:
                return audit_channel
            if channel_id == 456:
                return panel_channel
            return None

        mock_guild.get_channel.side_effect = get_channel

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await service.set_message_id(
                panel_id=panel.id,
                message_id=555,
                guild_name="Test Guild",
            )
            await session.commit()

        await roles_cog._handle_refresh(mock_interaction, "TestPanel")

        audit_channel.send.assert_not_called()


class TestHandleDelete:
    """Tests for _handle_delete command handler."""

    async def test_returns_if_no_guild(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test that handler returns early if not in guild."""
        mock_interaction.guild = None
        await roles_cog._handle_delete(mock_interaction, "TestPanel")
        mock_interaction.response.send_message.assert_not_called()

    async def test_shows_not_found_for_missing_panel(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler shows not found for missing panel."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            await session.commit()

        await roles_cog._handle_delete(mock_interaction, "NonExistent")

        mock_interaction.response.send_message.assert_called_once()


class TestSendAuditMessage:
    """Tests for _send_audit_message method."""

    async def test_sends_to_audit_channel(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that audit message is sent to audit channel."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_guild.get_channel.return_value = mock_channel

        await roles_cog._send_audit_message(mock_guild, 456, "Test audit message")

        mock_channel.send.assert_called_once_with("Test audit message")

    async def test_handles_missing_channel(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that missing audit channel is handled gracefully."""
        mock_guild.get_channel.return_value = None

        # Should not raise
        await roles_cog._send_audit_message(mock_guild, 456, "Test audit message")


class TestOnRoleAdded:
    """Tests for _on_role_added method."""

    async def test_sends_dm_when_enabled(
        self,
        roles_cog: RolesCog,
        mock_member: MagicMock,
        mock_role: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that DM is sent when dm_on_role_change is enabled."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set DM message template
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.DM_ROLE_ADDED_MSG,
                value="You got the {role_name} role!",
            )
            await session.commit()

        # Create a panel with DM enabled
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                dm_on_role_change=True,
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            await roles_cog._on_role_added(panel, mock_guild, mock_member, mock_role, config)

        mock_member.send.assert_called_once()

    async def test_does_not_send_dm_when_disabled(
        self,
        roles_cog: RolesCog,
        mock_member: MagicMock,
        mock_role: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that no DM is sent when dm_on_role_change is False."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Create a panel with DM disabled
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                dm_on_role_change=False,
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            await roles_cog._on_role_added(panel, mock_guild, mock_member, mock_role, config)

        mock_member.send.assert_not_called()


class TestOnRoleRemoved:
    """Tests for _on_role_removed method."""

    async def test_sends_dm_when_enabled(
        self,
        roles_cog: RolesCog,
        mock_member: MagicMock,
        mock_role: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that DM is sent when dm_on_role_change is enabled."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set DM message template
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.DM_ROLE_REMOVED_MSG,
                value="You lost the {role_name} role!",
            )
            await session.commit()

        # Create a panel with DM enabled
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                dm_on_role_change=True,
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            await roles_cog._on_role_removed(panel, mock_guild, mock_member, mock_role, config)

        mock_member.send.assert_called_once()


class TestSendMissingRoleDM:
    """Tests for _send_missing_role_dm method."""

    async def test_sends_dm_with_template(
        self,
        roles_cog: RolesCog,
        mock_member: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that DM is sent when template is configured."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set DM message template
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.DM_MISSING_ROLE_MSG,
                value="You need a required role for {panel_name}",
            )
            await session.commit()

        # Create a panel
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                required_roles=[999],
                dm_on_missing_role=True,
            )
            await session.commit()

            await roles_cog._send_missing_role_dm(panel, mock_guild, mock_member)

        mock_member.send.assert_called_once()

    async def test_does_not_send_dm_without_template(
        self,
        roles_cog: RolesCog,
        mock_member: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that no DM is sent when template is not configured."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Create a panel (no DM template configured)
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

            await roles_cog._send_missing_role_dm(panel, mock_guild, mock_member)

        mock_member.send.assert_not_called()


class TestHandleAddRoleSuccess:
    """Additional tests for _handle_add_role command handler."""

    async def test_adds_mapping_successfully(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler adds mapping to existing panel."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel to add mapping to
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

        target_role = MagicMock(spec=discord.Role)
        target_role.id = 555
        target_role.name = "TargetRole"
        target_role.mention = "<@&555>"

        await roles_cog._handle_add_role(mock_interaction, "TestPanel", "👍", target_role, None)

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "added" in call_args[0][0] or "mapping" in call_args[0][0].lower()


class TestHandleRemoveRoleSuccess:
    """Additional tests for _handle_remove_role command handler."""

    async def test_removes_mapping_successfully(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler removes mapping from existing panel."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel with mapping
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 555}],
            )
            await session.commit()

        await roles_cog._handle_remove_role(mock_interaction, "TestPanel", "👍")

        mock_interaction.response.send_message.assert_called_once()

    async def test_rejects_without_permission(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler rejects user without permission."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = []  # No roles
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set manage_roles to require a role the user doesn't have
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[999],
            )
            await session.commit()

        await roles_cog._handle_remove_role(mock_interaction, "TestPanel", "👍")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True


class TestHandleDeleteSuccess:
    """Additional tests for _handle_delete command handler."""

    async def test_deletes_panel_successfully(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler deletes panel successfully."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel to delete
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

        await roles_cog._handle_delete(mock_interaction, "TestPanel")

        mock_interaction.response.send_message.assert_called_once()


class TestHandleRefreshNotFound:
    """Additional tests for _handle_refresh command handler."""

    async def test_shows_not_found_for_missing_panel(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler shows not found for missing panel."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            await session.commit()

        await roles_cog._handle_refresh(mock_interaction, "NonExistent")

        mock_interaction.response.send_message.assert_called_once()


class TestHandlePostNoMappings:
    """Tests for _handle_post when panel has no mappings."""

    async def test_rejects_post_without_mappings(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler rejects posting panel without mappings."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel with no mappings
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[],  # No mappings
            )
            await session.commit()

        await roles_cog._handle_post(mock_interaction, "TestPanel")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        # Should mention that panel has no mappings
        assert call_args[1]["ephemeral"] is True


class TestHandleInfoWithDetails:
    """Additional tests for _handle_info command handler."""

    async def test_shows_panel_with_dm_settings(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler shows panel info with DM settings."""
        mock_interaction.guild = mock_guild
        mock_guild.get_channel.return_value = None
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = None

        # Create a panel with DM settings and required roles
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=mock_member.id,
                guild_name="Test Guild",
                dm_on_role_change=True,
                dm_on_missing_role=True,
                required_roles=[123, 456],
                role_mappings=[{"emoji": "👍", "role_id": 789}],
            )
            await session.commit()

        await roles_cog._handle_info(mock_interaction, "TestPanel")

        mock_interaction.response.send_message.assert_called_once()
        call_kwargs = mock_interaction.response.send_message.call_args[1]
        assert "embed" in call_kwargs


class TestDMForbiddenHandling:
    """Tests for handling discord.Forbidden when sending DMs."""

    async def test_dm_forbidden_does_not_raise(
        self,
        roles_cog: RolesCog,
        mock_member: MagicMock,
        mock_role: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that Forbidden exception when sending DM is handled."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set DM message template
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.DM_ROLE_ADDED_MSG,
                value="You got the {role_name} role!",
            )
            await session.commit()

        # Make send raise Forbidden
        mock_member.send.side_effect = discord.Forbidden(MagicMock(), "Cannot send DM")

        # Create a panel with DM enabled
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                dm_on_role_change=True,
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            # Should not raise
            await roles_cog._on_role_added(panel, mock_guild, mock_member, mock_role, config)


class TestAuditMessageSending:
    """Tests for audit message functionality."""

    async def test_sends_audit_on_role_added(
        self,
        roles_cog: RolesCog,
        mock_member: MagicMock,
        mock_role: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that audit message is sent when role is added."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        mock_audit_channel = MagicMock(spec=discord.TextChannel)
        mock_audit_channel.send = AsyncMock()
        mock_guild.get_channel.return_value = mock_audit_channel

        # Set audit settings
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_CHANNEL,
                value=456,
            )
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_USER_ROLE_ADD,
                value=True,
            )
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_USER_ROLE_ADD_MSG,
                value="{user_mention} got {role_mention}",
            )
            await session.commit()

        # Create a panel
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            await roles_cog._on_role_added(panel, mock_guild, mock_member, mock_role, config)

        mock_audit_channel.send.assert_called_once()

    async def test_sends_audit_on_role_removed(
        self,
        roles_cog: RolesCog,
        mock_member: MagicMock,
        mock_role: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that audit message is sent when role is removed."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        mock_audit_channel = MagicMock(spec=discord.TextChannel)
        mock_audit_channel.send = AsyncMock()
        mock_guild.get_channel.return_value = mock_audit_channel

        # Set audit settings
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_CHANNEL,
                value=456,
            )
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_USER_ROLE_REMOVE,
                value=True,
            )
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_USER_ROLE_REMOVE_MSG,
                value="{user_mention} lost {role_mention}",
            )
            await session.commit()

        # Create a panel
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            await roles_cog._on_role_removed(panel, mock_guild, mock_member, mock_role, config)

        mock_audit_channel.send.assert_called_once()


class TestHandlePostSuccess:
    """Tests for _handle_post success path."""

    async def test_posts_panel_successfully(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler posts panel successfully."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Mock channel and message
        mock_message = MagicMock(spec=discord.Message)
        mock_message.id = 99999
        mock_message.add_reaction = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456
        mock_channel.mention = "<#456>"
        mock_channel.send = AsyncMock(return_value=mock_message)

        mock_guild.get_channel.return_value = mock_channel

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel with mappings
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 100}],
            )
            await session.commit()

        await roles_cog._handle_post(mock_interaction, "TestPanel")

        mock_channel.send.assert_called_once()
        mock_interaction.followup.send.assert_called_once()

    async def test_rejects_already_posted_panel(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler rejects already posted panel."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel with message_id (already posted)
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 100}],
            )
            await service.set_message_id(
                panel_id=panel.id, message_id=99999, guild_name="Test Guild"
            )
            await session.commit()

        await roles_cog._handle_post(mock_interaction, "TestPanel")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "already posted" in call_args[0][0]

    async def test_rejects_when_channel_not_found(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler rejects when channel not found."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        mock_guild.get_channel.return_value = None  # Channel not found
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel with mappings
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 100}],
            )
            await session.commit()

        await roles_cog._handle_post(mock_interaction, "TestPanel")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "not found" in call_args[0][0]


class TestHandleRefreshPaths:
    """Tests for _handle_refresh various paths."""

    async def test_rejects_when_not_posted(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler rejects refresh for non-posted panel."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel without message_id (not posted)
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

        await roles_cog._handle_refresh(mock_interaction, "TestPanel")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "not posted" in call_args[0][0].lower()


class TestHandleToggle:
    """Tests for _handle_toggle method."""

    async def test_does_not_add_role_if_already_has(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that role is not added if member already has it."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Member already has the role
        mock_member.roles = [mock_role]

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            await roles_cog._handle_toggle(panel, mock_guild, mock_member, mock_role, True, config)

        # Role should not be added (already has it)
        mock_member.add_roles.assert_not_called()

    async def test_does_not_remove_role_if_does_not_have(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that role is not removed if member doesn't have it."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Member doesn't have the role
        mock_member.roles = []

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            await roles_cog._handle_toggle(panel, mock_guild, mock_member, mock_role, False, config)

        # Role should not be removed (doesn't have it)
        mock_member.remove_roles.assert_not_called()


class TestMappingToPartialEmoji:
    """Tests for _mapping_to_partial_emoji method."""

    def test_unicode_emoji(self, roles_cog: RolesCog) -> None:
        """Test converting unicode emoji mapping."""
        mapping = {"emoji": "👍", "emoji_id": None, "role_id": 100}
        result = roles_cog._mapping_to_partial_emoji(mapping)
        assert result is not None
        assert result.name == "👍"

    def test_custom_emoji(self, roles_cog: RolesCog) -> None:
        """Test converting custom emoji mapping."""
        mapping = {"emoji": "custom", "emoji_id": 123456789, "role_id": 100}
        result = roles_cog._mapping_to_partial_emoji(mapping)
        assert result is not None
        assert result.name == "custom"
        assert result.id == 123456789

    def test_missing_emoji(self, roles_cog: RolesCog) -> None:
        """Test converting mapping with missing emoji."""
        mapping = {"role_id": 100}
        result = roles_cog._mapping_to_partial_emoji(mapping)
        assert result is None


# ===== COMMAND REGISTRATION TESTS =====


class TestRegisterGuildCommands:
    """Tests for _register_guild_commands method."""

    async def test_skips_when_cog_disabled(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that command registration is skipped when cog is disabled."""
        # Cog is disabled by default
        await roles_cog._register_guild_commands(mock_guild)
        # No commands should be registered
        assert mock_guild.id not in roles_cog._registered_commands

    async def test_registers_commands_when_enabled(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are registered when cog is enabled."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        await roles_cog._register_guild_commands(mock_guild)

        assert mock_guild.id in roles_cog._registered_commands
        assert roles_cog._registered_commands[mock_guild.id]["prefix"] == "roles"
        roles_cog.bot.tree.add_command.assert_called()

    async def test_skips_if_already_registered_same_prefix(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that re-registration is skipped if prefix unchanged."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # First registration
        await roles_cog._register_guild_commands(mock_guild)
        first_call_count = roles_cog.bot.tree.add_command.call_count

        # Second registration (same prefix)
        await roles_cog._register_guild_commands(mock_guild)
        second_call_count = roles_cog.bot.tree.add_command.call_count

        # Should not add again
        assert first_call_count == second_call_count

    async def test_reregisters_on_prefix_change(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are re-registered when prefix changes."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # First registration with default prefix
        await roles_cog._register_guild_commands(mock_guild)
        assert roles_cog._registered_commands[mock_guild.id]["prefix"] == "roles"

        # Change prefix
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_PREFIX,
                value="myroles",
            )
            await session.commit()

        # Second registration with new prefix
        await roles_cog._register_guild_commands(mock_guild)
        assert roles_cog._registered_commands[mock_guild.id]["prefix"] == "myroles"

    async def test_unregisters_when_disabled(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are unregistered when cog is disabled."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # First register
        await roles_cog._register_guild_commands(mock_guild)
        assert mock_guild.id in roles_cog._registered_commands

        # Disable cog
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=False
            )
            await session.commit()

        # Try to register again (should unregister)
        await roles_cog._register_guild_commands(mock_guild)
        assert mock_guild.id not in roles_cog._registered_commands


class TestRegisterGuildCommandsPrefixSafety:
    """Invalid or colliding prefixes fall back to the default group name."""

    async def test_invalid_prefix_registers_default_group(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """An uppercase stored prefix registers '/roles' instead of raising."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        with patch.object(
            roles_cog, "_get_config", AsyncMock(return_value={ConfigKey.COMMAND_PREFIX: "Roles"})
        ):
            await roles_cog._register_guild_commands(mock_guild)

        group = roles_cog.bot.tree.add_command.call_args.args[0]
        assert group.name == "roles"
        assert roles_cog._registered_commands[mock_guild.id]["prefix"] == "roles"

    async def test_colliding_prefix_falls_back_to_default(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """A prefix already used by another command registers '/roles' instead."""
        await enable_cog_for_guild(test_database, mock_guild.id)
        roles_cog.bot.tree.get_command = MagicMock(
            side_effect=lambda name, guild=None: MagicMock() if name == "purge_war" else None
        )

        with patch.object(
            roles_cog,
            "_get_config",
            AsyncMock(return_value={ConfigKey.COMMAND_PREFIX: "purge_war"}),
        ):
            await roles_cog._register_guild_commands(mock_guild)

        group = roles_cog.bot.tree.add_command.call_args.args[0]
        assert group.name == "roles"


class TestOnReadySkipsSyncForFailedGuilds:
    """A guild whose registration raised is not synced (would wipe its commands)."""

    async def test_failed_guild_is_not_synced(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Only guilds that registered successfully are synced."""
        ok_guild = MagicMock(spec=discord.Guild)
        ok_guild.id = 987
        ok_guild.name = "OK"
        roles_cog.bot.guilds = [mock_guild, ok_guild]

        async def register(guild: MagicMock) -> None:
            roles_cog._registered_commands[guild.id] = {"prefix": "roles"}
            if guild is mock_guild:
                raise RuntimeError("db down")

        with patch.object(roles_cog, "_register_guild_commands", side_effect=register):
            await roles_cog.on_ready()

        roles_cog.bot.tree.sync.assert_called_once_with(guild=ok_guild)


class TestOnReadySyncsChangedGuilds:
    """on_ready only syncs guilds whose registered commands actually changed."""

    async def test_reconnect_does_not_resync_unchanged_guilds(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """A READY after a reconnect must not re-sync guilds that were already registered."""
        new_guild = MagicMock(spec=discord.Guild)
        new_guild.id = 987
        new_guild.name = "New"
        roles_cog.bot.guilds = [mock_guild, new_guild]

        # mock_guild was registered before this READY; new_guild is new
        roles_cog._registered_commands[mock_guild.id] = {"prefix": "roles"}

        async def register(guild: MagicMock) -> None:
            if guild is new_guild:
                roles_cog._registered_commands[guild.id] = {"prefix": "roles"}

        with patch.object(roles_cog, "_register_guild_commands", side_effect=register):
            await roles_cog.on_ready()

        roles_cog.bot.tree.sync.assert_called_once_with(guild=new_guild)


class TestUnregisterGuildCommands:
    """Tests for _unregister_guild_commands method."""

    async def test_removes_command_group(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that command group is removed."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Register first
        await roles_cog._register_guild_commands(mock_guild)
        assert mock_guild.id in roles_cog._registered_commands

        # Unregister
        await roles_cog._unregister_guild_commands(mock_guild)

        roles_cog.bot.tree.remove_command.assert_called()
        assert mock_guild.id not in roles_cog._registered_commands

    async def test_handles_guild_not_registered(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that unregistering non-registered guild doesn't error."""
        # Should not raise
        await roles_cog._unregister_guild_commands(mock_guild)


class TestSyncGuildCommands:
    """Tests for _sync_guild_commands method."""

    async def test_syncs_commands(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that commands are synced."""
        await roles_cog._sync_guild_commands(mock_guild)
        roles_cog.bot.tree.sync.assert_called_with(guild=mock_guild)

    async def test_sync_error_is_raised_with_details(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """A failed sync raises CommandSyncError carrying Discord's message."""
        roles_cog.bot.tree.sync.side_effect = Exception("Sync failed")

        with pytest.raises(CommandSyncError, match="Sync failed"):
            await roles_cog._sync_guild_commands(mock_guild)


class TestSyncFailureSurfacesToDashboard:
    """Dashboard callbacks propagate sync failures; startup paths only log them."""

    async def test_on_config_changed_raises_when_sync_fails(
        self, roles_cog: RolesCog, mock_guild: MagicMock
    ) -> None:
        """A prefix change whose sync fails is reported to the caller."""
        roles_cog.bot.tree.sync = AsyncMock(side_effect=Exception("Missing Access"))

        with (
            patch.object(roles_cog, "_register_guild_commands", AsyncMock()),
            pytest.raises(CommandSyncError, match="Missing Access"),
        ):
            await roles_cog.on_config_changed(mock_guild, [ConfigKey.COMMAND_PREFIX])

    async def test_on_cog_toggled_raises_when_sync_fails(
        self, roles_cog: RolesCog, mock_guild: MagicMock
    ) -> None:
        """Enabling the cog with a failing sync is reported to the caller."""
        roles_cog.bot.tree.sync = AsyncMock(side_effect=Exception("Missing Access"))

        async def register(guild: MagicMock) -> None:
            roles_cog._registered_commands[guild.id] = {"prefix": "roles"}

        with (
            patch.object(roles_cog, "_register_guild_commands", side_effect=register),
            pytest.raises(CommandSyncError, match="Missing Access"),
        ):
            await roles_cog.on_cog_toggled(mock_guild, enabled=True)

    async def test_on_ready_continues_after_a_failed_sync(
        self, roles_cog: RolesCog, mock_guild: MagicMock
    ) -> None:
        """A sync failure in one guild does not stop the others from syncing."""
        ok_guild = MagicMock(spec=discord.Guild)
        ok_guild.id = 987
        ok_guild.name = "OK"
        roles_cog.bot.guilds = [mock_guild, ok_guild]
        roles_cog.bot.tree.sync = AsyncMock(
            side_effect=lambda guild: (
                (_ for _ in ()).throw(Exception("boom")) if guild is mock_guild else None
            )
        )

        async def register(guild: MagicMock) -> None:
            roles_cog._registered_commands[guild.id] = {"prefix": "roles"}

        with patch.object(roles_cog, "_register_guild_commands", side_effect=register):
            await roles_cog.on_ready()

        assert roles_cog.bot.tree.sync.await_count == 2

    async def test_on_guild_join_does_not_raise_when_sync_fails(
        self, roles_cog: RolesCog, mock_guild: MagicMock
    ) -> None:
        """Joining a guild whose sync fails is logged, not raised."""
        roles_cog.bot.tree.sync = AsyncMock(side_effect=Exception("boom"))

        async def register(guild: MagicMock) -> None:
            roles_cog._registered_commands[guild.id] = {"prefix": "roles"}

        with patch.object(roles_cog, "_register_guild_commands", side_effect=register):
            await roles_cog.on_guild_join(mock_guild)


class TestOnReady:
    """Tests for on_ready event handler."""

    async def test_registers_commands_for_all_guilds(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that on_ready registers commands for all guilds."""
        await enable_cog_for_guild(test_database, mock_guild.id)
        roles_cog.bot.guilds = [mock_guild]

        await roles_cog.on_ready()

        assert mock_guild.id in roles_cog._registered_commands

    async def test_handles_registration_error(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that on_ready handles registration errors gracefully."""
        roles_cog.bot.guilds = [mock_guild]
        # Make registration fail
        roles_cog.bot.tree.add_command.side_effect = Exception("Failed")

        # Should not raise
        await roles_cog.on_ready()


class TestOnGuildJoin:
    """Tests for on_guild_join event handler."""

    async def test_registers_commands_on_join(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are registered when bot joins guild."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        await roles_cog.on_guild_join(mock_guild)

        assert mock_guild.id in roles_cog._registered_commands


# ===== HANDLER ERROR PATH TESTS =====


class TestHandleToggleErrors:
    """Tests for _handle_toggle error paths."""

    async def test_handles_forbidden_on_add(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that Forbidden is handled when adding role."""
        await enable_cog_for_guild(test_database, mock_guild.id)
        mock_member.roles = []
        mock_member.add_roles.side_effect = discord.Forbidden(MagicMock(), "No perm")

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            # Should not raise
            await roles_cog._handle_toggle(panel, mock_guild, mock_member, mock_role, True, config)

    async def test_handles_general_exception(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that general exceptions are handled."""
        await enable_cog_for_guild(test_database, mock_guild.id)
        mock_member.roles = []
        mock_member.add_roles.side_effect = Exception("Unknown error")

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            # Should not raise
            await roles_cog._handle_toggle(panel, mock_guild, mock_member, mock_role, True, config)


class TestHandleExclusiveUnreact:
    """Tests for _handle_exclusive unreact scenarios."""

    async def test_unreact_removes_role_when_has_other(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        mock_role2: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that unreact removes role when user has another panel role."""
        await enable_cog_for_guild(test_database, mock_guild.id)
        # Member has both roles from the panel
        mock_member.roles = [mock_role, mock_role2]

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="ExclusivePanel",
                panel_type=PanelType.EXCLUSIVE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[
                    {"emoji": "👍", "role_id": mock_role.id},
                    {"emoji": "👎", "role_id": mock_role2.id},
                ],
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            # Unreact - should remove role since user has another
            await roles_cog._handle_exclusive(
                panel, mock_guild, mock_member, mock_role, False, config, 456, 999
            )

        mock_member.remove_roles.assert_called_once()

    async def test_unreact_does_not_remove_last_role(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that unreact doesn't remove last role in exclusive mode."""
        await enable_cog_for_guild(test_database, mock_guild.id)
        # Member only has one role from the panel
        mock_member.roles = [mock_role]

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="ExclusivePanel",
                panel_type=PanelType.EXCLUSIVE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[
                    {"emoji": "👍", "role_id": mock_role.id},
                    {"emoji": "👎", "role_id": 200},
                ],
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            # Unreact - should NOT remove since it's the last role
            await roles_cog._handle_exclusive(
                panel, mock_guild, mock_member, mock_role, False, config, 456, 999
            )

        mock_member.remove_roles.assert_not_called()

    async def test_handles_forbidden_on_unreact(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        mock_role2: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that Forbidden is handled on unreact."""
        await enable_cog_for_guild(test_database, mock_guild.id)
        mock_member.roles = [mock_role, mock_role2]
        mock_member.remove_roles.side_effect = discord.Forbidden(MagicMock(), "No perm")

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="ExclusivePanel",
                panel_type=PanelType.EXCLUSIVE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[
                    {"emoji": "👍", "role_id": mock_role.id},
                    {"emoji": "👎", "role_id": mock_role2.id},
                ],
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            # Should not raise
            await roles_cog._handle_exclusive(
                panel, mock_guild, mock_member, mock_role, False, config, 456, 999
            )


class TestHandleExclusiveReact:
    """Tests for _handle_exclusive react scenarios."""

    async def test_handles_forbidden_on_react(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that Forbidden is handled when adding role."""
        await enable_cog_for_guild(test_database, mock_guild.id)
        mock_member.roles = []
        mock_member.add_roles.side_effect = discord.Forbidden(MagicMock(), "No perm")

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="ExclusivePanel",
                panel_type=PanelType.EXCLUSIVE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": mock_role.id}],
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            # Should not raise
            await roles_cog._handle_exclusive(
                panel, mock_guild, mock_member, mock_role, True, config, 456, 999
            )

    async def test_handles_general_exception(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that general exceptions are handled."""
        await enable_cog_for_guild(test_database, mock_guild.id)
        mock_member.roles = []
        mock_member.add_roles.side_effect = Exception("Error")

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="ExclusivePanel",
                panel_type=PanelType.EXCLUSIVE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": mock_role.id}],
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            # Should not raise
            await roles_cog._handle_exclusive(
                panel, mock_guild, mock_member, mock_role, True, config, 456, 999
            )


class TestHandleVerifyErrors:
    """Tests for _handle_verify error paths."""

    async def test_ignores_unreact(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that unreact is ignored for verify panels."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="VerifyPanel",
                panel_type=PanelType.VERIFY,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": mock_role.id}],
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            emoji = discord.PartialEmoji(name="👍")
            # Unreact - should be ignored
            await roles_cog._handle_verify(
                panel, mock_guild, mock_member, mock_role, False, config, 456, 999, emoji, 123
            )

        mock_member.add_roles.assert_not_called()

    async def test_handles_forbidden(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that Forbidden is handled."""
        await enable_cog_for_guild(test_database, mock_guild.id)
        mock_member.roles = []
        mock_member.add_roles.side_effect = discord.Forbidden(MagicMock(), "No perm")

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="VerifyPanel",
                panel_type=PanelType.VERIFY,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": mock_role.id}],
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            emoji = discord.PartialEmoji(name="👍")
            # Should not raise
            await roles_cog._handle_verify(
                panel, mock_guild, mock_member, mock_role, True, config, 456, 999, emoji, 123
            )

    async def test_handles_general_exception(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that general exceptions are handled."""
        await enable_cog_for_guild(test_database, mock_guild.id)
        mock_member.roles = []
        mock_member.add_roles.side_effect = Exception("Error")

        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="VerifyPanel",
                panel_type=PanelType.VERIFY,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": mock_role.id}],
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            emoji = discord.PartialEmoji(name="👍")
            # Should not raise
            await roles_cog._handle_verify(
                panel, mock_guild, mock_member, mock_role, True, config, 456, 999, emoji, 123
            )


class TestHandleAddRoleValidation:
    """Additional tests for _handle_add_role validation paths."""

    async def test_rejects_emoji_already_mapped(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler rejects emoji that's already mapped."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel with existing mapping
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 555}],
            )
            await session.commit()

        target_role = MagicMock(spec=discord.Role)
        target_role.id = 666
        target_role.name = "NewRole"

        await roles_cog._handle_add_role(mock_interaction, "TestPanel", "👍", target_role, None)

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "already mapped" in call_args[0][0]

    async def test_adds_mapping_successfully(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler successfully adds a new mapping."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel without any mappings
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[],  # Empty mappings
            )
            await session.commit()

        target_role = MagicMock(spec=discord.Role)
        target_role.id = 666
        target_role.name = "NewRole"
        target_role.mention = "<@&666>"

        await roles_cog._handle_add_role(mock_interaction, "TestPanel", "👍", target_role, None)

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "Added mapping" in call_args[0][0]

        # Verify mapping was added
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.get_by_name(guild_id=mock_guild.id, name="TestPanel")
            assert panel is not None
            assert len(panel.role_mappings) == 1
            assert panel.role_mappings[0]["emoji"] == "👍"
            assert panel.role_mappings[0]["role_id"] == 666


class TestHandleRemoveRoleValidation:
    """Additional tests for _handle_remove_role validation paths."""

    async def test_rejects_emoji_not_found(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler rejects emoji not in panel."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel with different emoji
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 555}],
            )
            await session.commit()

        await roles_cog._handle_remove_role(mock_interaction, "TestPanel", "👎")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "not mapped" in call_args[0][0]


class TestHandlePostForbidden:
    """Tests for _handle_post Forbidden error."""

    async def test_handles_forbidden_when_posting(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that Forbidden is handled when posting."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Mock channel that raises Forbidden
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456
        mock_channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No perm"))
        mock_guild.get_channel.return_value = mock_channel

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel with mappings
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 100}],
            )
            await session.commit()

        await roles_cog._handle_post(mock_interaction, "TestPanel")

        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        assert "permissions" in call_args[0][0]

    async def test_handles_general_exception(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that general exceptions are handled when posting."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Mock channel that raises Exception
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456
        mock_channel.send = AsyncMock(side_effect=Exception("Error"))
        mock_guild.get_channel.return_value = mock_channel

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel with mappings
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 100}],
            )
            await session.commit()

        await roles_cog._handle_post(mock_interaction, "TestPanel")

        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        assert "error" in call_args[0][0].lower()


class TestHandleRefreshSuccess:
    """Tests for _handle_refresh success path."""

    async def test_refreshes_posted_panel(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler refreshes posted panel."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Mock channel and message
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        mock_message.clear_reactions = AsyncMock()
        mock_message.add_reaction = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_guild.get_channel.return_value = mock_channel

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create posted panel with mappings
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 100}],
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        await roles_cog._handle_refresh(mock_interaction, "TestPanel")

        mock_message.edit.assert_called_once()
        mock_interaction.followup.send.assert_called_once()


class TestHandleDeletePostedPanel:
    """Tests for _handle_delete with posted panels."""

    async def test_deletes_posted_panel(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that the posted panel message is deleted through a partial message, no fetch."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Mock channel and message
        mock_message = MagicMock(spec=discord.PartialMessage)
        mock_message.delete = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456
        mock_channel.get_partial_message = MagicMock(return_value=mock_message)
        mock_channel.fetch_message = AsyncMock()
        mock_guild.get_channel.return_value = mock_channel

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create posted panel
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        await roles_cog._handle_delete(mock_interaction, "TestPanel")

        mock_channel.get_partial_message.assert_called_once_with(999)
        mock_message.delete.assert_awaited_once()
        mock_channel.fetch_message.assert_not_awaited()
        mock_interaction.response.send_message.assert_called_once()


# ===== SETUP AND TEARDOWN TESTS =====


class TestReloadLifecycle:
    """Reloading the cog from the dashboard must hand the slash commands to the new instance."""

    async def test_cog_unload_removes_registered_commands_from_tree(
        self,
        roles_cog: RolesCog,
        mock_discord_bot: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        """Unloading drops this instance's commands so a reloaded cog can register them again."""
        roles_cog._registered_commands[mock_guild.id] = {"prefix": "roles"}
        mock_discord_bot.get_guild.return_value = mock_guild

        await roles_cog.cog_unload()

        mock_discord_bot.tree.remove_command.assert_any_call("roles", guild=mock_guild)
        assert mock_discord_bot.tree.remove_command.call_count == 1
        assert mock_guild.id not in roles_cog._registered_commands

    async def test_cog_unload_forgets_guilds_the_bot_left(
        self,
        roles_cog: RolesCog,
        mock_discord_bot: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        """A tracked guild the bot is no longer in is dropped without touching the tree."""
        roles_cog._registered_commands[mock_guild.id] = {"prefix": "roles"}
        mock_discord_bot.get_guild.return_value = None

        await roles_cog.cog_unload()

        mock_discord_bot.tree.remove_command.assert_not_called()
        assert roles_cog._registered_commands == {}

    async def test_cog_load_registers_commands_when_bot_is_already_ready(
        self,
        roles_cog: RolesCog,
        mock_discord_bot: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        """A reload on a running bot registers and syncs commands without waiting for on_ready."""
        mock_discord_bot.is_ready.return_value = True
        mock_discord_bot.guilds = [mock_guild]

        async def register(guild: MagicMock) -> None:
            roles_cog._registered_commands[guild.id] = {"prefix": "roles"}

        with (
            patch.object(
                roles_cog, "_register_guild_commands", new_callable=AsyncMock, side_effect=register
            ) as mock_register,
            patch.object(roles_cog, "_sync_guild_commands", new_callable=AsyncMock) as mock_sync,
        ):
            await roles_cog.cog_load()

        mock_register.assert_awaited_once_with(mock_guild)
        mock_sync.assert_awaited_once_with(mock_guild)

    async def test_cog_load_waits_for_on_ready_at_startup(
        self,
        roles_cog: RolesCog,
        mock_discord_bot: MagicMock,
        mock_guild: MagicMock,
    ) -> None:
        """At startup the guilds are not available yet, so cog_load leaves it to on_ready."""
        mock_discord_bot.is_ready.return_value = False
        mock_discord_bot.guilds = [mock_guild]

        with patch.object(
            roles_cog, "_register_guild_commands", new_callable=AsyncMock
        ) as mock_register:
            await roles_cog.cog_load()

        mock_register.assert_not_awaited()


class TestSetupAndTeardown:
    """Tests for setup and teardown functions."""

    async def test_setup_registers_schema_and_adds_cog(
        self,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test that setup registers schema and adds cog."""
        from discord_bot.roles.cog import setup

        mock_discord_bot.add_cog = AsyncMock()

        await setup(mock_discord_bot)

        mock_discord_bot.add_cog.assert_called_once()

    async def test_teardown_unregisters_commands(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that teardown unregisters commands."""
        from discord_bot.roles.cog import teardown

        await enable_cog_for_guild(test_database, mock_guild.id)

        # Register commands
        await roles_cog._register_guild_commands(mock_guild)
        assert mock_guild.id in roles_cog._registered_commands

        # Mock get_cog to return our cog
        roles_cog.bot.get_cog = MagicMock(return_value=roles_cog)
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)

        await teardown(roles_cog.bot)

        assert mock_guild.id not in roles_cog._registered_commands


class TestRemoveUserReaction:
    """Tests for _remove_user_reaction method."""

    @staticmethod
    def _make_channel(mock_guild: MagicMock, message: MagicMock) -> MagicMock:
        """Build a text channel mock whose partial message is the given message.

        Args:
            mock_guild (MagicMock): Guild mock returning the channel.
            message (MagicMock): Message returned by get_partial_message.

        Returns:
            MagicMock: The channel mock.
        """
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.get_partial_message = MagicMock(return_value=message)
        mock_channel.fetch_message = AsyncMock()
        mock_guild.get_channel.return_value = mock_channel
        return mock_channel

    async def test_removes_reaction_with_partial_message(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that the reaction is removed via a partial message without fetching."""
        mock_message = MagicMock(spec=discord.PartialMessage)
        mock_message.remove_reaction = AsyncMock()
        mock_channel = self._make_channel(mock_guild, mock_message)
        mock_guild.get_member.return_value = MagicMock(spec=discord.Member)

        emoji = discord.PartialEmoji(name="👍")
        await roles_cog._remove_user_reaction(mock_guild, 456, 999, emoji, 123)

        mock_channel.get_partial_message.assert_called_once_with(999)
        mock_channel.fetch_message.assert_not_awaited()
        mock_message.remove_reaction.assert_awaited_once()
        called_emoji, called_user = mock_message.remove_reaction.await_args[0]
        assert called_emoji == emoji
        assert called_user.id == 123

    async def test_removes_reaction_when_member_not_cached(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that the reaction is removed even when the member is not cached."""
        mock_message = MagicMock(spec=discord.PartialMessage)
        mock_message.remove_reaction = AsyncMock()
        self._make_channel(mock_guild, mock_message)
        mock_guild.get_member.return_value = None  # Member not in cache

        emoji = discord.PartialEmoji(name="👍")
        await roles_cog._remove_user_reaction(mock_guild, 456, 999, emoji, 123)

        mock_message.remove_reaction.assert_awaited_once()
        assert mock_message.remove_reaction.await_args[0][1].id == 123

    async def test_handles_missing_channel(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that missing channel is handled."""
        mock_guild.get_channel.return_value = None

        emoji = discord.PartialEmoji(name="👍")
        # Should not raise
        await roles_cog._remove_user_reaction(mock_guild, 456, 999, emoji, 123)

    async def test_handles_exception(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that exceptions are handled."""
        mock_message = MagicMock(spec=discord.PartialMessage)
        mock_message.remove_reaction = AsyncMock(side_effect=Exception("Error"))
        self._make_channel(mock_guild, mock_message)

        emoji = discord.PartialEmoji(name="👍")
        # Should not raise
        await roles_cog._remove_user_reaction(mock_guild, 456, 999, emoji, 123)

    async def test_handles_forbidden(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that Forbidden is handled."""
        mock_message = MagicMock(spec=discord.PartialMessage)
        mock_message.remove_reaction = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "No perms")
        )
        self._make_channel(mock_guild, mock_message)

        emoji = discord.PartialEmoji(name="👍")
        # Should not raise
        await roles_cog._remove_user_reaction(mock_guild, 456, 999, emoji, 123)

    async def test_handles_not_found(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that NotFound is handled."""
        mock_message = MagicMock(spec=discord.PartialMessage)
        mock_message.remove_reaction = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )
        self._make_channel(mock_guild, mock_message)

        emoji = discord.PartialEmoji(name="👍")
        # Should not raise
        await roles_cog._remove_user_reaction(mock_guild, 456, 999, emoji, 123)


# ===== CONFIG CHANGE CALLBACK TESTS =====


class TestOnConfigChanged:
    """Tests for on_config_changed callback."""

    async def test_reregisters_on_prefix_change(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are re-registered on prefix change."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # First register
        await roles_cog._register_guild_commands(mock_guild)
        initial_call_count = roles_cog.bot.tree.add_command.call_count

        # Change prefix
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.COMMAND_PREFIX,
                value="newroles",
            )
            await session.commit()

        # Trigger config change
        await roles_cog.on_config_changed(mock_guild, [ConfigKey.COMMAND_PREFIX])

        # Should re-register
        assert roles_cog.bot.tree.add_command.call_count > initial_call_count

    async def test_ignores_non_prefix_changes(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that non-prefix changes don't trigger re-registration."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # First register
        await roles_cog._register_guild_commands(mock_guild)
        initial_call_count = roles_cog.bot.tree.add_command.call_count

        # Trigger config change for different key
        await roles_cog.on_config_changed(mock_guild, [ConfigKey.MANAGE_ROLES])

        # Should not re-register
        assert roles_cog.bot.tree.add_command.call_count == initial_call_count


class TestOnCogToggled:
    """Tests for on_cog_toggled callback."""

    async def test_registers_when_enabled(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are registered when cog is enabled."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        await roles_cog.on_cog_toggled(mock_guild, enabled=True)

        assert mock_guild.id in roles_cog._registered_commands

    async def test_unregisters_when_disabled(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that commands are unregistered when cog is disabled."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # First enable
        await roles_cog._register_guild_commands(mock_guild)
        assert mock_guild.id in roles_cog._registered_commands

        # Then disable
        await roles_cog.on_cog_toggled(mock_guild, enabled=False)

        assert mock_guild.id not in roles_cog._registered_commands


# ===== HANDLE REACTION EDGE CASES =====


class TestHandleReactionEdgeCases:
    """Tests for _handle_reaction edge cases."""

    def _create_mock_payload(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        user_id: int,
        emoji_name: str = "👍",
    ) -> MagicMock:
        """Create a mock payload."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = guild_id
        payload.channel_id = channel_id
        payload.message_id = message_id
        payload.user_id = user_id

        emoji = MagicMock(spec=discord.PartialEmoji)
        emoji.name = emoji_name
        emoji.id = None
        emoji.is_custom_emoji.return_value = False
        payload.emoji = emoji

        return payload

    async def test_ignores_when_guild_not_found(
        self,
        roles_cog: RolesCog,
    ) -> None:
        """Test that reaction is ignored when guild is not found."""
        roles_cog.bot.get_guild.return_value = None

        payload = self._create_mock_payload(
            guild_id=123,
            channel_id=456,
            message_id=789,
            user_id=111,
        )

        # Should not raise
        await roles_cog._handle_reaction(payload, is_add=True)

    async def test_ignores_when_cog_disabled(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that reaction is ignored when cog is disabled."""
        roles_cog.bot.get_guild.return_value = mock_guild

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=789,
            user_id=111,
        )

        # Should not raise (cog is disabled by default)
        await roles_cog._handle_reaction(payload, is_add=True)


class TestProcessReactionEdgeCases:
    """Tests for _process_reaction edge cases."""

    def _create_mock_payload(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        user_id: int,
        emoji_name: str = "👍",
    ) -> MagicMock:
        """Create a mock payload."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = guild_id
        payload.channel_id = channel_id
        payload.message_id = message_id
        payload.user_id = user_id

        emoji = MagicMock(spec=discord.PartialEmoji)
        emoji.name = emoji_name
        emoji.id = None
        emoji.is_custom_emoji.return_value = False
        payload.emoji = emoji

        return payload

    async def test_fetches_member_when_not_in_cache(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that member is fetched when not in cache."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 111
        mock_member.roles = []
        mock_member.add_roles = AsyncMock()
        mock_member.send = AsyncMock()

        # Member not in cache, but fetched
        mock_guild.get_member.return_value = None
        mock_guild.fetch_member = AsyncMock(return_value=mock_member)
        mock_guild.get_role.return_value = mock_role

        # Create panel
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": mock_role.id}],
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=111,
        )

        await roles_cog._process_reaction(payload, mock_guild, is_add=True)

        mock_guild.fetch_member.assert_called_once_with(111)

    async def test_ignores_when_member_not_found(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that reaction is ignored when member not found."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        mock_guild.get_member.return_value = None
        mock_guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        # Create panel
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 100}],
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=111,
        )

        # Should not raise
        await roles_cog._process_reaction(payload, mock_guild, is_add=True)

    async def test_ignores_when_role_not_found(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that reaction is ignored when role not found in guild."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = None  # Role not found

        # Create panel
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 999999}],  # Non-existent role
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=mock_member.id,
        )

        # Should not raise
        await roles_cog._process_reaction(payload, mock_guild, is_add=True)
        # Role should not be added
        mock_member.add_roles.assert_not_called()

    async def test_removes_invalid_reaction(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that invalid reactions are removed."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        mock_guild.get_member.return_value = mock_member
        mock_member.roles = []

        # Create panel with only 👍 mapped
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 100}],
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        # React with 👎 (not mapped)
        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=mock_member.id,
            emoji_name="👎",  # Not in mappings
        )

        # Should not raise or add roles
        await roles_cog._process_reaction(payload, mock_guild, is_add=True)
        mock_member.add_roles.assert_not_called()


# ===== SEND AUDIT MESSAGE ERROR HANDLING =====


class TestSendAuditMessageErrors:
    """Tests for _send_audit_message error handling."""

    async def test_handles_forbidden(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that Forbidden is handled when sending audit message."""
        import builtins

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No perms"))
        mock_guild.get_channel.return_value = mock_channel

        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: object, classinfo: type | tuple) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        with patch.object(builtins, "isinstance", patched_isinstance):
            # Should not raise
            await roles_cog._send_audit_message(mock_guild, 456, "Test")

    async def test_handles_general_exception(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that general exceptions are handled."""
        import builtins

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock(side_effect=Exception("Error"))
        mock_guild.get_channel.return_value = mock_channel

        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: object, classinfo: type | tuple) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        with patch.object(builtins, "isinstance", patched_isinstance):
            # Should not raise
            await roles_cog._send_audit_message(mock_guild, 456, "Test")


# ===== HANDLE REFRESH ERROR PATHS =====


class TestHandleRefreshErrors:
    """Tests for _handle_refresh error paths."""

    async def test_handles_not_found_exception(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that NotFound exception is handled."""
        import builtins

        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        mock_guild.get_channel.return_value = mock_channel

        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: object, classinfo: type | tuple) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        with patch.object(builtins, "isinstance", patched_isinstance):
            await roles_cog._handle_refresh(mock_interaction, "TestPanel")

        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        assert "deleted" in call_args[0][0].lower()

    async def test_handles_forbidden_exception(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that Forbidden exception is handled."""
        import builtins

        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_guild.get_channel.return_value = mock_channel

        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: object, classinfo: type | tuple) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        with patch.object(builtins, "isinstance", patched_isinstance):
            await roles_cog._handle_refresh(mock_interaction, "TestPanel")

        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        assert "permissions" in call_args[0][0].lower()

    async def test_handles_missing_channel(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that missing channel is handled."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        mock_guild.get_channel.return_value = None
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        await roles_cog._handle_refresh(mock_interaction, "TestPanel")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "not found" in call_args[0][0].lower()


# ===== HANDLE CREATE WITH AUDIT =====


class TestHandleCreateWithAudit:
    """Tests for _handle_create audit notification."""

    async def test_sends_audit_notification(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that audit notification is sent on panel creation."""
        import builtins

        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        mock_audit_channel = MagicMock(spec=discord.TextChannel)
        mock_audit_channel.send = AsyncMock()
        mock_guild.get_channel.return_value = mock_audit_channel

        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: object, classinfo: type | tuple) -> bool:
            if classinfo is discord.TextChannel and obj is mock_audit_channel:
                return True
            return original_isinstance(obj, classinfo)

        # Setup audit config
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_CHANNEL,
                value=789,
            )
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_PANEL_CREATED,
                value=True,
            )
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_PANEL_CREATED_MSG,
                value="Panel {panel_name} created by {user_mention}",
            )
            await session.commit()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456
        mock_channel.mention = "<#456>"

        with patch.object(builtins, "isinstance", patched_isinstance):
            await roles_cog._handle_create(mock_interaction, "TestPanel", mock_channel, "toggle")

        mock_audit_channel.send.assert_called()


# ===== HANDLE DELETE WITH AUDIT =====


class TestHandleDeleteWithAudit:
    """Tests for _handle_delete audit notification."""

    async def test_sends_audit_notification(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that audit notification is sent on panel deletion."""
        import builtins

        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        mock_audit_channel = MagicMock(spec=discord.TextChannel)
        mock_audit_channel.send = AsyncMock()
        mock_guild.get_channel.return_value = mock_audit_channel

        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: object, classinfo: type | tuple) -> bool:
            if classinfo is discord.TextChannel and obj is mock_audit_channel:
                return True
            return original_isinstance(obj, classinfo)

        # Setup audit config
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_CHANNEL,
                value=789,
            )
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_PANEL_DELETED,
                value=True,
            )
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.AUDIT_PANEL_DELETED_MSG,
                value="Panel {panel_name} deleted by {user_mention}",
            )
            # Create panel
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

        with patch.object(builtins, "isinstance", patched_isinstance):
            await roles_cog._handle_delete(mock_interaction, "TestPanel")

        mock_audit_channel.send.assert_called()


# ===== CUSTOM EMOJI HANDLING =====


class TestCustomEmojiHandling:
    """Tests for custom emoji handling in reactions."""

    def _create_mock_payload_custom(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        user_id: int,
        emoji_name: str,
        emoji_id: int,
    ) -> MagicMock:
        """Create a mock payload with custom emoji."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = guild_id
        payload.channel_id = channel_id
        payload.message_id = message_id
        payload.user_id = user_id

        emoji = MagicMock(spec=discord.PartialEmoji)
        emoji.name = emoji_name
        emoji.id = emoji_id
        emoji.is_custom_emoji.return_value = True
        payload.emoji = emoji

        return payload

    async def test_handles_custom_emoji_reaction(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that custom emoji reactions are handled."""
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role

        await enable_cog_for_guild(test_database, mock_guild.id)

        mock_member.roles = []

        # Create panel with custom emoji
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "custom", "emoji_id": 123456789, "role_id": mock_role.id}],
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        payload = self._create_mock_payload_custom(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=mock_member.id,
            emoji_name="custom",
            emoji_id=123456789,
        )

        await roles_cog.on_raw_reaction_add(payload)

        mock_member.add_roles.assert_called_once()


# ===== HANDLE POST REACTION ADD ERRORS =====


class TestHandlePostReactionAddErrors:
    """Tests for _handle_post HTTPException during reaction add."""

    async def test_handles_http_exception_on_reaction_add(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that HTTPException is handled when adding reactions."""
        import builtins

        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Mock message that fails on add_reaction
        mock_message = MagicMock(spec=discord.Message)
        mock_message.id = 99999
        mock_message.add_reaction = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "Failed")
        )

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456
        mock_channel.mention = "<#456>"
        mock_channel.send = AsyncMock(return_value=mock_message)
        mock_guild.get_channel.return_value = mock_channel

        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: object, classinfo: type | tuple) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 100}],
            )
            await session.commit()

        with patch.object(builtins, "isinstance", patched_isinstance):
            await roles_cog._handle_post(mock_interaction, "TestPanel")

        # Should still post successfully even if reaction add fails
        mock_interaction.followup.send.assert_called_once()


# ===== HANDLE REFRESH REACTION ADD ERRORS =====


class TestHandleRefreshReactionAddErrors:
    """Tests for _handle_refresh HTTPException during reaction add."""

    async def test_handles_http_exception_on_reaction_add(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that HTTPException is handled when adding reactions."""
        import builtins

        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Mock message that fails on add_reaction
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        mock_message.clear_reactions = AsyncMock()
        mock_message.add_reaction = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "Failed")
        )

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_guild.get_channel.return_value = mock_channel

        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: object, classinfo: type | tuple) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 100}],
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        with patch.object(builtins, "isinstance", patched_isinstance):
            await roles_cog._handle_refresh(mock_interaction, "TestPanel")

        # Should still refresh successfully even if reaction add fails
        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        assert "refreshed" in call_args[0][0].lower()


# ===== HANDLE DELETE MESSAGE DELETION ERRORS =====


class TestHandleDeleteMessageErrors:
    """Tests for _handle_delete message deletion errors."""

    async def test_handles_message_delete_forbidden(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that Forbidden is handled when deleting message."""
        import builtins

        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Mock message that fails on delete
        mock_message = MagicMock(spec=discord.PartialMessage)
        mock_message.delete = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No perms"))

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456
        mock_channel.get_partial_message = MagicMock(return_value=mock_message)
        mock_guild.get_channel.return_value = mock_channel

        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: object, classinfo: type | tuple) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        with patch.object(builtins, "isinstance", patched_isinstance):
            await roles_cog._handle_delete(mock_interaction, "TestPanel")

        # Should still delete panel even if message deletion fails
        mock_interaction.response.send_message.assert_called_once()

    async def test_handles_message_not_found_during_delete(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that NotFound is handled when deleting message."""
        import builtins

        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        mock_message = MagicMock(spec=discord.PartialMessage)
        mock_message.delete = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Not found"))
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 456
        mock_channel.get_partial_message = MagicMock(return_value=mock_message)
        mock_guild.get_channel.return_value = mock_channel

        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: object, classinfo: type | tuple) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        with patch.object(builtins, "isinstance", patched_isinstance):
            await roles_cog._handle_delete(mock_interaction, "TestPanel")

        # Should still delete panel even if message already deleted
        mock_interaction.response.send_message.assert_called_once()


# ===== EXCLUSIVE PANEL REACTION REMOVAL =====


class TestExclusivePanelReactionRemoval:
    """Tests for exclusive panel reaction removal."""

    def _create_mock_payload(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        user_id: int,
        emoji_name: str = "👍",
    ) -> MagicMock:
        """Create a mock payload."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = guild_id
        payload.channel_id = channel_id
        payload.message_id = message_id
        payload.user_id = user_id

        emoji = MagicMock(spec=discord.PartialEmoji)
        emoji.name = emoji_name
        emoji.id = None
        emoji.is_custom_emoji.return_value = False
        payload.emoji = emoji

        return payload

    async def test_removes_other_reactions_when_switching(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        mock_role2: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that other reactions are removed when switching roles."""
        import builtins

        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member

        def get_role_side_effect(role_id: int) -> MagicMock | None:
            if role_id == 100:
                return mock_role
            if role_id == 200:
                return mock_role2
            return None

        mock_guild.get_role.side_effect = get_role_side_effect

        await enable_cog_for_guild(test_database, mock_guild.id)

        # Create mock message for reaction removal
        mock_message = MagicMock(spec=discord.Message)
        mock_message.remove_reaction = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.get_partial_message = MagicMock(return_value=mock_message)
        mock_guild.get_channel.return_value = mock_channel

        original_isinstance = builtins.isinstance

        def patched_isinstance(obj: object, classinfo: type | tuple) -> bool:
            if classinfo is discord.TextChannel and obj is mock_channel:
                return True
            return original_isinstance(obj, classinfo)

        # Member has role 100 initially
        mock_member.roles = [mock_role]

        # Create exclusive panel with two roles
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="ExclusivePanel",
                panel_type=PanelType.EXCLUSIVE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[
                    {"emoji": "👍", "role_id": 100},
                    {"emoji": "👎", "role_id": 200},
                ],
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        # React with 👎 to switch to role 200
        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=mock_member.id,
            emoji_name="👎",
        )

        with patch.object(builtins, "isinstance", patched_isinstance):
            await roles_cog.on_raw_reaction_add(payload)

        # Old role should be removed, new role added
        mock_member.remove_roles.assert_called()
        mock_member.add_roles.assert_called()


# ===== COMMAND GROUP METHODS =====


class TestCommandGroupMethods:
    """Tests for command group adding methods."""

    def test_add_create_command(self, roles_cog: RolesCog) -> None:
        """Test that create command is added."""
        from discord import app_commands

        group = app_commands.Group(name="test", description="Test")
        roles_cog._add_create_command(group)

    def test_add_add_role_command(self, roles_cog: RolesCog) -> None:
        """Test that add_role command is added."""
        from discord import app_commands

        group = app_commands.Group(name="test", description="Test")
        roles_cog._add_add_role_command(group)

    def test_add_remove_role_command(self, roles_cog: RolesCog) -> None:
        """Test that remove_role command is added."""
        from discord import app_commands

        group = app_commands.Group(name="test", description="Test")
        roles_cog._add_remove_role_command(group)

    def test_add_post_command(self, roles_cog: RolesCog) -> None:
        """Test that post command is added."""
        from discord import app_commands

        group = app_commands.Group(name="test", description="Test")
        roles_cog._add_post_command(group)

    def test_add_refresh_command(self, roles_cog: RolesCog) -> None:
        """Test that refresh command is added."""
        from discord import app_commands

        group = app_commands.Group(name="test", description="Test")
        roles_cog._add_refresh_command(group)

    def test_add_delete_command(self, roles_cog: RolesCog) -> None:
        """Test that delete command is added."""
        from discord import app_commands

        group = app_commands.Group(name="test", description="Test")
        roles_cog._add_delete_command(group)

    def test_add_list_command(self, roles_cog: RolesCog) -> None:
        """Test that list command is added."""
        from discord import app_commands

        group = app_commands.Group(name="test", description="Test")
        roles_cog._add_list_command(group)

    def test_add_info_command(self, roles_cog: RolesCog) -> None:
        """Test that info command is added."""
        from discord import app_commands

        group = app_commands.Group(name="test", description="Test")
        roles_cog._add_info_command(group)


# ===== COMMAND HANDLERS USER NOT MEMBER =====


class TestCommandHandlersUserNotMember:
    """Tests for command handlers when user is not a Member."""

    async def test_handle_add_role_returns_if_user_not_member(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler returns if user is not a Member."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = MagicMock(spec=discord.User)  # Not Member
        await enable_cog_for_guild(test_database, mock_guild.id)

        await roles_cog._handle_add_role(mock_interaction, "TestPanel", "👍", mock_role, None)
        mock_interaction.response.send_message.assert_not_called()

    async def test_handle_remove_role_returns_if_user_not_member(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler returns if user is not a Member."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = MagicMock(spec=discord.User)
        await enable_cog_for_guild(test_database, mock_guild.id)

        await roles_cog._handle_remove_role(mock_interaction, "TestPanel", "👍")
        mock_interaction.response.send_message.assert_not_called()

    async def test_handle_post_returns_if_user_not_member(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler returns if user is not a Member."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = MagicMock(spec=discord.User)
        await enable_cog_for_guild(test_database, mock_guild.id)

        await roles_cog._handle_post(mock_interaction, "TestPanel")
        mock_interaction.response.send_message.assert_not_called()

    async def test_handle_refresh_returns_if_user_not_member(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler returns if user is not a Member."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = MagicMock(spec=discord.User)
        await enable_cog_for_guild(test_database, mock_guild.id)

        await roles_cog._handle_refresh(mock_interaction, "TestPanel")
        mock_interaction.response.send_message.assert_not_called()

    async def test_handle_delete_returns_if_user_not_member(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handler returns if user is not a Member."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = MagicMock(spec=discord.User)
        await enable_cog_for_guild(test_database, mock_guild.id)

        await roles_cog._handle_delete(mock_interaction, "TestPanel")
        mock_interaction.response.send_message.assert_not_called()


# ===== PANEL AUTOCOMPLETE =====


class TestPanelAutocompleteMethod:
    """Tests for panel_autocomplete method."""

    async def test_returns_empty_when_no_guild(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test that autocomplete returns empty when no guild."""
        mock_interaction.guild = None

        result = await roles_cog.panel_autocomplete(mock_interaction, "test")

        assert result == []

    async def test_returns_matching_panels(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that autocomplete returns matching panels."""
        mock_interaction.guild = mock_guild

        # Create panels
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="OtherPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
            )
            await session.commit()

        result = await roles_cog.panel_autocomplete(mock_interaction, "Test")

        assert len(result) >= 1
        names = [choice.name for choice in result]
        assert "TestPanel" in names

    async def test_limits_results_to_25(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that autocomplete limits results to 25."""
        mock_interaction.guild = mock_guild

        # Create 30 panels
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            for i in range(30):
                await service.create_panel(
                    guild_id=mock_guild.id,
                    channel_id=456,
                    name=f"Panel{i}",
                    panel_type=PanelType.TOGGLE,
                    created_by=789,
                    guild_name="Test Guild",
                )
            await session.commit()

        result = await roles_cog.panel_autocomplete(mock_interaction, "Panel")

        assert len(result) <= 25


# ===== GET CONFIG =====


class TestGetConfigMethod:
    """Tests for _get_config method."""

    async def test_returns_config_dict(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that config dict is returned."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        config = await roles_cog._get_config(mock_guild.id)

        assert isinstance(config, dict)
        assert ConfigKey.COMMAND_PREFIX in config


# ===== ON RAW REACTION REMOVE =====


class TestOnRawReactionRemoveHandler:
    """Tests for on_raw_reaction_remove event handler."""

    def _create_mock_payload(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        user_id: int,
        emoji_name: str = "👍",
    ) -> MagicMock:
        """Create a mock payload."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.guild_id = guild_id
        payload.channel_id = channel_id
        payload.message_id = message_id
        payload.user_id = user_id

        emoji = MagicMock(spec=discord.PartialEmoji)
        emoji.name = emoji_name
        emoji.id = None
        emoji.is_custom_emoji.return_value = False
        payload.emoji = emoji

        return payload

    async def test_toggle_panel_removes_role(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that toggle panel removes role on unreact."""
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777
        mock_guild.get_member.return_value = mock_member
        mock_guild.get_role.return_value = mock_role

        await enable_cog_for_guild(test_database, mock_guild.id)

        # Member has the role
        mock_member.roles = [mock_role]

        # Create toggle panel
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": mock_role.id}],
            )
            await service.set_message_id(panel_id=panel.id, message_id=999, guild_name="Test Guild")
            await session.commit()

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=mock_member.id,
        )

        await roles_cog.on_raw_reaction_remove(payload)

        mock_member.remove_roles.assert_called_once()

    async def test_ignores_bot_reactions(
        self,
        roles_cog: RolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that bot's own reactions are ignored."""
        roles_cog.bot.get_guild = MagicMock(return_value=mock_guild)
        roles_cog.bot.user.id = 999888777

        payload = self._create_mock_payload(
            guild_id=mock_guild.id,
            channel_id=456,
            message_id=999,
            user_id=999888777,  # Bot's own user ID
        )

        await roles_cog.on_raw_reaction_remove(payload)

        # Should not process
        mock_guild.get_member.assert_not_called()


# ===== DM FORBIDDEN HANDLING =====


class TestDMForbiddenInOnRoleRemoved:
    """Tests for Forbidden exception handling in _on_role_removed."""

    async def test_handles_dm_forbidden(
        self,
        roles_cog: RolesCog,
        mock_member: MagicMock,
        mock_role: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that Forbidden is handled when sending DM in _on_role_removed."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set DM message template
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.DM_ROLE_REMOVED_MSG,
                value="You lost {role_name}",
            )
            await session.commit()

        # Make DM raise Forbidden
        mock_member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Cannot send DM"))

        # Create panel with DM enabled
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                dm_on_role_change=True,
            )
            await session.commit()

            config = await roles_cog._get_config(mock_guild.id)
            # Should not raise
            await roles_cog._on_role_removed(panel, mock_guild, mock_member, mock_role, config)


class TestSendMissingRoleDMForbidden:
    """Tests for Forbidden exception handling in _send_missing_role_dm."""

    async def test_handles_dm_forbidden(
        self,
        roles_cog: RolesCog,
        mock_member: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that Forbidden is handled when sending missing role DM."""
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set DM message template
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.DM_MISSING_ROLE_MSG,
                value="You need {required_roles}",
            )
            await session.commit()

        # Make DM raise Forbidden
        mock_member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Cannot send DM"))

        # Create panel
        async with test_database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                required_roles=[999],
                dm_on_missing_role=True,
            )
            await session.commit()

            # Should not raise
            await roles_cog._send_missing_role_dm(panel, mock_guild, mock_member)


# ===== HANDLE REMOVE ROLE FULL PATHS =====


class TestHandleRemoveRoleFullPaths:
    """Tests for _handle_remove_role full code paths."""

    async def test_removes_mapping_successfully(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that mapping is removed successfully."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission via MANAGE_ROLES
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            # Create panel with mapping
            service = ReactionRolesService(session)
            await service.create_panel(
                guild_id=mock_guild.id,
                channel_id=456,
                name="TestPanel",
                panel_type=PanelType.TOGGLE,
                created_by=789,
                guild_name="Test Guild",
                role_mappings=[{"emoji": "👍", "role_id": 555}],
            )
            await session.commit()

        await roles_cog._handle_remove_role(mock_interaction, "TestPanel", "👍")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert "Removed" in call_args[0][0]

    async def test_rejects_when_no_permission(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test rejection when user lacks permission."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = []
        mock_member.guild_permissions.administrator = False
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set required role
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[999],  # User doesn't have
            )
            await session.commit()

        await roles_cog._handle_remove_role(mock_interaction, "TestPanel", "👍")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True

    async def test_shows_not_found(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        mock_role: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test panel not found message."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = [mock_role]
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Give user permission
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[mock_role.id],
            )
            await session.commit()

        await roles_cog._handle_remove_role(mock_interaction, "NonExistent", "👍")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True


# ===== HANDLE POST NO PERMISSION =====


class TestHandlePostNoPermission:
    """Tests for _handle_post permission check."""

    async def test_rejects_when_no_permission(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test rejection when user lacks permission."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = []
        mock_member.guild_permissions.administrator = False
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set required role
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[999],
            )
            await session.commit()

        await roles_cog._handle_post(mock_interaction, "TestPanel")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True


# ===== HANDLE REFRESH NO PERMISSION =====


class TestHandleRefreshNoPermission:
    """Tests for _handle_refresh permission check."""

    async def test_rejects_when_no_permission(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test rejection when user lacks permission."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = []
        mock_member.guild_permissions.administrator = False
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set required role
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[999],
            )
            await session.commit()

        await roles_cog._handle_refresh(mock_interaction, "TestPanel")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True


# ===== HANDLE DELETE NO PERMISSION =====


class TestHandleDeleteNoPermission:
    """Tests for _handle_delete permission check."""

    async def test_rejects_when_no_permission(
        self,
        roles_cog: RolesCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test rejection when user lacks permission."""
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_member.roles = []
        mock_member.guild_permissions.administrator = False
        await enable_cog_for_guild(test_database, mock_guild.id)

        # Set required role
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=mock_guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.MANAGE_ROLES,
                value=[999],
            )
            await session.commit()

        await roles_cog._handle_delete(mock_interaction, "TestPanel")

        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        assert call_args[1]["ephemeral"] is True


class TestOnGuildRemove:
    """Tests for on_guild_remove cleanup."""

    async def test_clears_guild_state(self, roles_cog: RolesCog, mock_guild: MagicMock) -> None:
        """Test that guild commands and cached state are dropped on removal."""
        roles_cog._registered_commands[mock_guild.id] = {"prefix": "roles"}

        await roles_cog.on_guild_remove(mock_guild)

        assert mock_guild.id not in roles_cog._registered_commands
        roles_cog.bot.tree.remove_command.assert_called_once_with("roles", guild=mock_guild)
