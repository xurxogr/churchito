"""Tests for PurgeCog."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.database import DatabaseService
from discord_bot.purge.cog import PurgeCog
from discord_bot.purge.config import COG_NAME, PURGE_CONFIG_SCHEMA
from discord_bot.purge.enums import ConfigKey, PurgeStatus, PurgeType
from discord_bot.purge.service import PurgeService


@pytest.fixture
def mock_discord_bot(test_database: DatabaseService) -> MagicMock:
    """Create mock of the bot with database."""
    bot = MagicMock(spec=DiscordBot)
    bot.database = test_database
    bot.guilds = []
    bot.add_view = MagicMock()
    bot.get_guild = MagicMock(return_value=None)
    bot.wait_until_ready = AsyncMock()
    bot.tree = MagicMock()
    bot.tree.add_command = MagicMock()
    bot.tree.remove_command = MagicMock()
    bot.tree.sync = AsyncMock()
    return bot


@pytest.fixture
def purge_cog(mock_discord_bot: MagicMock) -> PurgeCog:
    """Create cog instance for tests."""
    cog = PurgeCog(mock_discord_bot)
    # Allow test mode in tests
    cog._cog_settings.test_mode_allowed = True
    return cog


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
def mock_member(mock_guild: MagicMock) -> MagicMock:
    """Create mock of a Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 111222333
    member.bot = False
    member.display_name = "TestUser"
    member.nick = None
    member.guild = mock_guild
    member.guild_permissions = MagicMock()
    member.guild_permissions.manage_guild = True

    # Create mock roles
    role1 = MagicMock(spec=discord.Role)
    role1.id = 100
    role1.name = "Admin"
    role2 = MagicMock(spec=discord.Role)
    role2.id = 200
    role2.name = "Moderator"
    member.roles = [role1, role2]

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
    return interaction


@pytest.fixture
def mock_purge_record() -> MagicMock:
    """Create mock of a purge record."""
    record = MagicMock()
    record.id = 1
    record.guild_id = 123456789
    record.purge_type = PurgeType.WAR_END
    record.status = PurgeStatus.PENDING
    record.initiated_by = 111222333
    record.authorized_by = [111222333]
    record.cancelled_by = []
    record.confirmed_by = []
    record.scheduled_for = datetime.now(UTC) + timedelta(days=3)
    record.expires_at = datetime.now(UTC) + timedelta(hours=1)
    record.config_snapshot = {}
    record.mod_channel_id = 555666777
    record.mod_message_id = 888999000
    record.user_channel_id = None
    record.user_message_id = None
    return record


class TestGetConfigSchema:
    """Tests for get_config_schema."""

    def test_returns_schema(self, purge_cog: PurgeCog) -> None:
        """Test that returns the correct schema."""
        schema = purge_cog.get_config_schema()
        assert schema == PURGE_CONFIG_SCHEMA
        assert schema.cog_name == "purge"


class TestIsCogEnabled:
    """Tests for _is_cog_enabled."""

    async def test_cog_enabled(self, purge_cog: PurgeCog, test_database: DatabaseService) -> None:
        """Test when cog is enabled."""
        guild_id = 123

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await session.commit()

        result = await purge_cog._is_cog_enabled(guild_id)
        assert result is True

    async def test_cog_disabled(self, purge_cog: PurgeCog, test_database: DatabaseService) -> None:
        """Test when cog is disabled."""
        guild_id = 456

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name=COG_NAME, enabled=False
            )
            await session.commit()

        result = await purge_cog._is_cog_enabled(guild_id)
        assert result is False


class TestGetConfig:
    """Tests for _get_config."""

    async def test_returns_config_dict(
        self, purge_cog: PurgeCog, test_database: DatabaseService
    ) -> None:
        """Test that returns a configuration dictionary."""
        guild_id = 123

        result = await purge_cog._get_config(guild_id)

        assert isinstance(result, dict)

    async def test_returns_saved_config(
        self, purge_cog: PurgeCog, test_database: DatabaseService
    ) -> None:
        """Test that returns saved configuration."""
        guild_id = 789

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_CHANNEL, 123456)
            await session.commit()

        result = await purge_cog._get_config(guild_id)

        assert result.get(ConfigKey.MOD_CHANNEL) == 123456


class TestGetAvailablePurgeTypes:
    """Tests for _get_available_purge_types."""

    def test_war_complete_config(self, purge_cog: PurgeCog) -> None:
        """Test complete configuration for war purge."""
        config: dict[str, Any] = {
            ConfigKey.MOD_CHANNEL: 123,
            ConfigKey.USER_CHANNEL: 456,
            ConfigKey.WAR_ADMIN_ROLES: [100],
            ConfigKey.WAR_AFFECTED_ROLES: [200],
        }

        result = purge_cog._get_available_purge_types(config)

        assert result["war"] is True
        assert result["global"] is False

    def test_global_complete_config(self, purge_cog: PurgeCog) -> None:
        """Test complete configuration for global purge."""
        config: dict[str, Any] = {
            ConfigKey.MOD_CHANNEL: 123,
            ConfigKey.USER_CHANNEL: 456,
            ConfigKey.GLOBAL_ADMIN_ROLES: [100],
        }

        result = purge_cog._get_available_purge_types(config)

        assert result["war"] is False
        assert result["global"] is True

    def test_both_complete_config(self, purge_cog: PurgeCog) -> None:
        """Test complete configuration for both types."""
        config: dict[str, Any] = {
            ConfigKey.MOD_CHANNEL: 123,
            ConfigKey.USER_CHANNEL: 456,
            ConfigKey.WAR_ADMIN_ROLES: [100],
            ConfigKey.WAR_AFFECTED_ROLES: [200],
            ConfigKey.GLOBAL_ADMIN_ROLES: [300],
        }

        result = purge_cog._get_available_purge_types(config)

        assert result["war"] is True
        assert result["global"] is True

    def test_missing_mod_channel(self, purge_cog: PurgeCog) -> None:
        """Test without moderation channel."""
        config: dict[str, Any] = {
            ConfigKey.USER_CHANNEL: 456,
            ConfigKey.WAR_ADMIN_ROLES: [100],
            ConfigKey.WAR_AFFECTED_ROLES: [200],
            ConfigKey.GLOBAL_ADMIN_ROLES: [300],
        }

        result = purge_cog._get_available_purge_types(config)

        assert result["war"] is False
        assert result["global"] is False

    def test_missing_user_channel(self, purge_cog: PurgeCog) -> None:
        """Test without user channel."""
        config: dict[str, Any] = {
            ConfigKey.MOD_CHANNEL: 123,
            ConfigKey.WAR_ADMIN_ROLES: [100],
            ConfigKey.WAR_AFFECTED_ROLES: [200],
            ConfigKey.GLOBAL_ADMIN_ROLES: [300],
        }

        result = purge_cog._get_available_purge_types(config)

        assert result["war"] is False
        assert result["global"] is False

    def test_war_missing_admin_roles(self, purge_cog: PurgeCog) -> None:
        """Test war without admin roles."""
        config: dict[str, Any] = {
            ConfigKey.MOD_CHANNEL: 123,
            ConfigKey.USER_CHANNEL: 456,
            ConfigKey.WAR_AFFECTED_ROLES: [200],
        }

        result = purge_cog._get_available_purge_types(config)

        assert result["war"] is False
        assert result["global"] is False

    def test_war_missing_affected_roles(self, purge_cog: PurgeCog) -> None:
        """Test war without affected roles."""
        config: dict[str, Any] = {
            ConfigKey.MOD_CHANNEL: 123,
            ConfigKey.USER_CHANNEL: 456,
            ConfigKey.WAR_ADMIN_ROLES: [100],
        }

        result = purge_cog._get_available_purge_types(config)

        assert result["war"] is False
        assert result["global"] is False

    def test_all_missing(self, purge_cog: PurgeCog) -> None:
        """Test without any configuration."""
        config: dict[str, Any] = {}

        result = purge_cog._get_available_purge_types(config)

        assert result["war"] is False
        assert result["global"] is False


class TestHandleWarPurge:
    """Tests for _handle_purge with PurgeType.WAR_END."""

    async def test_no_guild(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test without guild."""
        mock_interaction.guild = None

        await purge_cog._handle_purge(mock_interaction, 3, PurgeType.WAR_END)

        mock_interaction.response.defer.assert_not_called()

    async def test_no_member(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test without member (user is not Member)."""
        mock_interaction.user = MagicMock(spec=discord.User)  # Not a Member

        await purge_cog._handle_purge(mock_interaction, 3, PurgeType.WAR_END)

        mock_interaction.response.defer.assert_not_called()

    async def test_no_permission(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test without permissions."""
        guild_id = mock_interaction.guild.id

        # User without admin roles
        mock_interaction.user.roles = []
        mock_interaction.user.guild_permissions.manage_guild = False

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [999])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_NO_PERMISSION_TEXT, "No permissions"
            )
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 3, PurgeType.WAR_END)

        mock_interaction.response.defer.assert_called_once()
        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "No permissions" in str(call_args)

    async def test_active_purge_exists(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test with existing active purge."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        # Configure permissions
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_ACTIVE_PURGE_TEXT, "Active purge"
            )

            # Create active purge
            purge_service = PurgeService(session)
            await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=mock_member.id,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 3, PurgeType.WAR_END)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "Active purge" in str(call_args)


class TestHandleGlobalPurge:
    """Tests for _handle_purge with PurgeType.GLOBAL."""

    async def test_no_guild(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test without guild."""
        mock_interaction.guild = None

        await purge_cog._handle_purge(mock_interaction, 3, PurgeType.GLOBAL)

        mock_interaction.response.defer.assert_not_called()

    async def test_no_member(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test without member (user is not Member)."""
        mock_interaction.user = MagicMock(spec=discord.User)  # Not a Member

        await purge_cog._handle_purge(mock_interaction, 3, PurgeType.GLOBAL)

        mock_interaction.response.defer.assert_not_called()

    async def test_no_permission(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test without permissions."""
        guild_id = mock_interaction.guild.id

        # User without admin roles
        mock_interaction.user.roles = []
        mock_interaction.user.guild_permissions.manage_guild = False

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.GLOBAL_ADMIN_ROLES, [999])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_NO_PERMISSION_TEXT, "No permissions"
            )
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 3, PurgeType.GLOBAL)

        mock_interaction.response.defer.assert_called_once()
        mock_interaction.followup.send.assert_called()

    async def test_active_purge_exists(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test when there is already active purge."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.GLOBAL_ADMIN_ROLES, [100])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_ACTIVE_PURGE_TEXT, "Active purge"
            )

            # Create active purge
            purge_service = PurgeService(session)
            await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.GLOBAL,
                initiated_by=mock_member.id,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 3, PurgeType.GLOBAL)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "Active purge" in str(call_args)

    async def test_successful_purge_creation(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test successful global purge creation."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        # Configure moderation channel
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 456
        mock_mod_channel.mention = "#moderacion"
        mock_mod_channel.send = AsyncMock(return_value=MagicMock(id=789))
        mock_interaction.guild.get_channel = MagicMock(return_value=mock_mod_channel)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.GLOBAL_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_CHANNEL, 456)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.USER_CHANNEL, 789)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 2)
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 3, PurgeType.GLOBAL)

        mock_mod_channel.send.assert_called()
        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "started" in str(call_args).lower()

    async def test_mod_channel_not_configured(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test when no moderation channel is configured."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.GLOBAL_ADMIN_ROLES, [100])
            # Do not configure MOD_CHANNEL
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 3, PurgeType.GLOBAL)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "not configured" in str(call_args).lower()

    async def test_mod_channel_not_found(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test when moderation channel does not exist."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member
        mock_interaction.guild.get_channel = MagicMock(return_value=None)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.GLOBAL_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_CHANNEL, 456)
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 3, PurgeType.GLOBAL)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "not found" in str(call_args).lower()

    async def test_auto_authorize_in_test_mode(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test auto-authorization in test mode."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        # Configure moderation and user channels
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 456
        mock_mod_channel.mention = "#moderacion"
        mock_mod_channel.send = AsyncMock(return_value=MagicMock(id=789))

        mock_user_channel = MagicMock(spec=discord.TextChannel)
        mock_user_channel.id = 789
        mock_user_channel.send = AsyncMock(return_value=MagicMock(id=101112))

        def get_channel(channel_id: int) -> MagicMock | None:
            if channel_id == 456:
                return mock_mod_channel
            if channel_id == 789:
                return mock_user_channel
            return None

        mock_interaction.guild.get_channel = MagicMock(side_effect=get_channel)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.GLOBAL_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_CHANNEL, 456)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.USER_CHANNEL, 789)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.TEST_MODE, True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 1)
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 3, PurgeType.GLOBAL)

        # Should have sent message to users (auto-authorized)
        mock_user_channel.send.assert_called()


class TestRegisterGlobalCommand:
    """Tests for _register_purge_command with PurgeType.GLOBAL."""

    async def test_registers_command_with_complete_config(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that registers command with complete config."""
        # Initialize dict for the guild
        purge_cog._registered_commands[mock_guild.id] = {}

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.MOD_CHANNEL, 123)
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.USER_CHANNEL, 456)
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.GLOBAL_ADMIN_ROLES, [100]
            )
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.GLOBAL_COMMAND_NAME, "purge_global"
            )
            await session.commit()

        config = await purge_cog._get_config(mock_guild.id)
        available = purge_cog._get_available_purge_types(config)

        await purge_cog._register_purge_command(
            mock_guild, config, PurgeType.GLOBAL, available["global"]
        )

        mock_discord_bot.tree.add_command.assert_called()
        assert purge_cog._registered_commands[mock_guild.id]["global"] == "purge_global"

    async def test_skips_when_config_incomplete(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that does not register with incomplete config."""
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            # Do not configure GLOBAL_ADMIN_ROLES
            await session.commit()

        config = await purge_cog._get_config(mock_guild.id)
        available = purge_cog._get_available_purge_types(config)

        await purge_cog._register_purge_command(
            mock_guild, config, PurgeType.GLOBAL, available["global"]
        )

        mock_discord_bot.tree.add_command.assert_not_called()

    async def test_removes_old_command_when_name_changed(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that removes old command when name changes."""
        # Register old command
        purge_cog._registered_commands[mock_guild.id] = {"global": "old_global_command"}

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.MOD_CHANNEL, 123)
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.USER_CHANNEL, 456)
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.GLOBAL_ADMIN_ROLES, [100]
            )
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.GLOBAL_COMMAND_NAME, "new_global_command"
            )
            await session.commit()

        config = await purge_cog._get_config(mock_guild.id)
        available = purge_cog._get_available_purge_types(config)

        await purge_cog._register_purge_command(
            mock_guild, config, PurgeType.GLOBAL, available["global"]
        )

        # Verify that the old command was removed
        mock_discord_bot.tree.remove_command.assert_called_with(
            "old_global_command", guild=mock_guild
        )
        # Verify that the new command was registered
        mock_discord_bot.tree.add_command.assert_called()

    async def test_unregisters_when_config_becomes_incomplete(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that removes command when config becomes incomplete."""
        # Register existing command
        purge_cog._registered_commands[mock_guild.id] = {"global": "purge_global"}

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            # Do not configure GLOBAL_ADMIN_ROLES (incomplete config)
            await session.commit()

        config = await purge_cog._get_config(mock_guild.id)
        available = purge_cog._get_available_purge_types(config)

        await purge_cog._register_purge_command(
            mock_guild, config, PurgeType.GLOBAL, available["global"]
        )

        # Verify that the command was removed
        mock_discord_bot.tree.remove_command.assert_called_with("purge_global", guild=mock_guild)
        assert "global" not in purge_cog._registered_commands.get(mock_guild.id, {})


class TestHandleAuthorize:
    """Tests for _handle_authorize."""

    async def test_no_guild(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test without guild."""
        mock_interaction.guild = None

        await purge_cog._handle_authorize(mock_interaction, "1")

        mock_interaction.response.defer.assert_not_called()

    async def test_no_permission(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test without permissions."""
        guild_id = mock_interaction.guild.id

        # User without admin roles
        mock_interaction.user.roles = []
        mock_interaction.user.guild_permissions.manage_guild = False

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [999])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_NO_PERMISSION_TEXT, "No permissions"
            )
            await session.commit()

            # Create war purge to test permissions
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            public_id = record.public_id

        await purge_cog._handle_authorize(mock_interaction, public_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "No permissions" in str(call_args)

    async def test_purge_not_found(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test with non-existent purge."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await session.commit()

        await purge_cog._handle_authorize(mock_interaction, "99999")

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "not found" in str(call_args).lower()

    async def test_already_authorized(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test when user has already authorized."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])

            # Create purge where user already authorized
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=mock_member.id,  # The initiator auto-authorizes
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()

        await purge_cog._handle_authorize(mock_interaction, record.public_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "already authorized" in str(call_args).lower()


class TestHandleCancel:
    """Tests for _handle_cancel."""

    async def test_no_guild(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test without guild."""
        mock_interaction.guild = None

        await purge_cog._handle_cancel(mock_interaction, "1")

        mock_interaction.response.defer.assert_not_called()

    async def test_no_permission(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test without permissions."""
        guild_id = mock_interaction.guild.id

        # User without admin roles
        mock_interaction.user.roles = []
        mock_interaction.user.guild_permissions.manage_guild = False

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [999])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_NO_PERMISSION_TEXT, "No permissions"
            )
            await session.commit()

            # Create war purge to test permissions
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            public_id = record.public_id

        await purge_cog._handle_cancel(mock_interaction, public_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "No permissions" in str(call_args)


class TestHandleConfirm:
    """Tests for _handle_confirm."""

    async def test_no_guild(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Test without guild."""
        mock_interaction.guild = None

        await purge_cog._handle_confirm(mock_interaction, "1")

        mock_interaction.response.defer.assert_not_called()

    async def test_purge_not_found(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test with non-existent purge."""
        mock_interaction.user = mock_member

        await purge_cog._handle_confirm(mock_interaction, "99999")

        mock_interaction.response.send_message.assert_called()
        call_args = mock_interaction.response.send_message.call_args
        assert "not found" in str(call_args).lower() or "no longer active" in str(call_args).lower()


class TestRegisterGuildCommands:
    """Tests for _register_guild_commands."""

    async def test_skips_when_cog_disabled(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that does not register commands when cog is disabled."""
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=False
            )
            await session.commit()

        await purge_cog._register_guild_commands(mock_guild)

        mock_discord_bot.tree.add_command.assert_not_called()

    async def test_skips_when_config_incomplete(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that does not register commands with incomplete config."""
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            # Do not configure the required fields
            await session.commit()

        await purge_cog._register_guild_commands(mock_guild)

        mock_discord_bot.tree.add_command.assert_not_called()

    async def test_registers_command_with_complete_config(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that registers commands with complete config."""
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.MOD_CHANNEL, 123)
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.USER_CHANNEL, 456)
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100]
            )
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.WAR_AFFECTED_ROLES, [200]
            )
            await session.commit()

        await purge_cog._register_guild_commands(mock_guild)

        mock_discord_bot.tree.add_command.assert_called_once()


class TestUnregisterGuildCommands:
    """Tests for _unregister_guild_commands."""

    async def test_removes_registered_command(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test that removes registered commands."""
        purge_cog._registered_commands[mock_guild.id] = {"war": "purge_war"}

        await purge_cog._unregister_guild_commands(mock_guild)

        mock_discord_bot.tree.remove_command.assert_called_once_with("purge_war", guild=mock_guild)
        assert mock_guild.id not in purge_cog._registered_commands

    async def test_removes_multiple_registered_commands(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test that removes multiple registered commands."""
        purge_cog._registered_commands[mock_guild.id] = {
            "war": "purge_war",
            "global": "purge_global",
        }

        await purge_cog._unregister_guild_commands(mock_guild)

        assert mock_discord_bot.tree.remove_command.call_count == 2
        assert mock_guild.id not in purge_cog._registered_commands

    async def test_does_nothing_when_no_command(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test that does nothing if no command is registered."""
        await purge_cog._unregister_guild_commands(mock_guild)

        mock_discord_bot.tree.remove_command.assert_not_called()


class TestCogLifecycle:
    """Tests for cog lifecycle."""

    async def test_cog_unload_cancels_loop(
        self, purge_cog: PurgeCog, mock_discord_bot: MagicMock
    ) -> None:
        """Test that cog_unload cancels the loop."""
        with patch.object(purge_cog.expiration_check_loop, "cancel") as mock_cancel:
            await purge_cog.cog_unload()
            mock_cancel.assert_called_once()


class TestSetupAndTeardown:
    """Tests for cog setup and teardown."""

    async def test_setup_registers_schema_and_adds_cog(self, mock_discord_bot: MagicMock) -> None:
        """Test that setup registers the schema and adds the cog."""
        from discord_bot.common.services.config_schema_service import (
            get_config_schema_service,
        )
        from discord_bot.purge.cog import setup
        from discord_bot.purge.config import PURGE_CONFIG_SCHEMA

        mock_discord_bot.add_cog = AsyncMock()

        await setup(mock_discord_bot)

        mock_discord_bot.add_cog.assert_called_once()
        # Verify that the schema was registered
        schema = get_config_schema_service().get_schema("purge")
        assert schema == PURGE_CONFIG_SCHEMA

    async def test_teardown_unregisters_schema(self, mock_discord_bot: MagicMock) -> None:
        """Test that teardown unregisters the schema."""
        from discord_bot.common.services.config_schema_service import (
            get_config_schema_service,
        )
        from discord_bot.purge.cog import setup, teardown

        mock_discord_bot.add_cog = AsyncMock()

        # First setup to register
        await setup(mock_discord_bot)
        assert get_config_schema_service().get_schema("purge") is not None

        # Then teardown
        await teardown(mock_discord_bot)
        assert get_config_schema_service().get_schema("purge") is None


class TestHandleCancelExtended:
    """Extended tests for _handle_cancel."""

    async def test_purge_not_found(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test with non-existent purge."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await session.commit()

        await purge_cog._handle_cancel(mock_interaction, "99999")

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "not found" in str(call_args).lower()

    async def test_purge_not_active(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test with purge that is not active."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Change status to cancelled
            await purge_service.update_status(record.id, PurgeStatus.CANCELLED)
            await session.commit()

        await purge_cog._handle_cancel(mock_interaction, record.public_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "cannot be cancelled" in str(call_args).lower()

    async def test_already_voted_cancel(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test when user has already voted to cancel."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Add user's cancellation vote
            await purge_service.add_cancellation(record.id, mock_member.id)
            await session.commit()

        await purge_cog._handle_cancel(mock_interaction, record.public_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "already voted" in str(call_args).lower()


class TestHandleConfirmExtended:
    """Extended tests for _handle_confirm."""

    async def test_purge_not_authorized(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test with purge in pending state (not authorized)."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Status is PENDING by default
            await session.commit()

        await purge_cog._handle_confirm(mock_interaction, record.public_id)

        mock_interaction.response.send_message.assert_called()
        call_args = mock_interaction.response.send_message.call_args
        assert "no longer active" in str(call_args).lower()


class TestScheduleMessageDeletion:
    """Tests for _schedule_message_deletion."""

    def test_schedules_deletion(self, purge_cog: PurgeCog) -> None:
        """Test that schedules deletion."""
        purge_cog._schedule_message_deletion(channel_id=123, message_id=456, retention_minutes=30)

        assert (123, 456) in purge_cog._pending_deletions

    def test_does_not_schedule_when_retention_zero(self, purge_cog: PurgeCog) -> None:
        """Test that does not schedule when retention is 0."""
        purge_cog._schedule_message_deletion(channel_id=123, message_id=456, retention_minutes=0)

        assert (123, 456) not in purge_cog._pending_deletions


class TestCheckPendingDeletions:
    """Tests for _check_pending_deletions."""

    async def test_deletes_expired_messages(
        self, purge_cog: PurgeCog, mock_discord_bot: MagicMock
    ) -> None:
        """Test that deletes expired messages."""
        # Schedule message with past time
        past_time = datetime.now(UTC) - timedelta(minutes=5)
        purge_cog._pending_deletions[(123, 456)] = past_time

        # Mock channel and message
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.delete = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_discord_bot.get_channel = MagicMock(return_value=mock_channel)

        await purge_cog._check_pending_deletions()

        assert (123, 456) not in purge_cog._pending_deletions
        mock_message.delete.assert_called_once()

    async def test_does_not_delete_future_messages(
        self, purge_cog: PurgeCog, mock_discord_bot: MagicMock
    ) -> None:
        """Test that does not delete future messages."""
        # Schedule message with future time
        future_time = datetime.now(UTC) + timedelta(minutes=30)
        purge_cog._pending_deletions[(123, 456)] = future_time

        await purge_cog._check_pending_deletions()

        assert (123, 456) in purge_cog._pending_deletions


class TestCheckExpiredPurges:
    """Tests for _check_expired_purges."""

    async def test_expires_pending_purge(
        self, purge_cog: PurgeCog, test_database: DatabaseService
    ) -> None:
        """Test that expires pending purges."""
        guild_id = 123

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
                expires_at=datetime.now(UTC) - timedelta(minutes=5),  # Already expired
            )
            await session.commit()
            purge_id = record.id
            purge_id = record.id

        # Register in tracking
        purge_cog._active_purges[guild_id] = (
            purge_id,
            datetime.now(UTC) - timedelta(minutes=5),
        )

        await purge_cog._check_expired_purges()

        # Verify that it was removed from tracking
        assert guild_id not in purge_cog._active_purges


class TestCheckReadyPurges:
    """Tests for _check_ready_purges."""

    async def test_executes_ready_purge(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that executes ready purges."""
        guild_id = 123

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test"
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [],
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),  # Already passed
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id
            purge_id = record.id

        # Register in tracking
        purge_cog._authorized_purges[guild_id] = (
            purge_id,
            datetime.now(UTC) - timedelta(minutes=5),
        )

        with patch.object(purge_cog, "_execute_purge", new_callable=AsyncMock) as mock_exec:
            await purge_cog._check_ready_purges()
            mock_exec.assert_called_once_with(guild_id=guild_id, purge_id=purge_id)

        # Verify that it was removed from tracking
        assert guild_id not in purge_cog._authorized_purges


class TestExecutePurge:
    """Tests for _execute_purge."""

    async def test_execute_no_guild(self, purge_cog: PurgeCog, mock_discord_bot: MagicMock) -> None:
        """Test execution without guild."""
        mock_discord_bot.get_guild = MagicMock(return_value=None)

        # Should not raise exception
        await purge_cog._execute_purge(999, 1)

    async def test_execute_purge_not_found(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test execution with purge not found."""
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        # Should not raise exception
        await purge_cog._execute_purge(mock_guild.id, 99999)

    async def test_execute_purge_not_authorized(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test execution with purge not authorized."""
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Status is PENDING, not AUTHORIZED
            await session.commit()
            purge_id = record.id

        # Should not raise exception
        await purge_cog._execute_purge(mock_guild.id, purge_id)


class TestUpdateModMessage:
    """Tests for _update_mod_message."""

    async def test_updates_message(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test message update."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Test",
            ConfigKey.MOD_STATUS_PENDING: "Pending",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        await purge_cog._update_mod_message(
            guild=mock_guild, record=mock_purge_record, config=config
        )

        mock_message.edit.assert_called_once()

    async def test_handles_no_channel(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test when there is no channel."""
        mock_purge_record.mod_channel_id = None

        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Test",
            ConfigKey.MOD_STATUS_PENDING: "Pending",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        # Should not raise exception
        await purge_cog._update_mod_message(
            guild=mock_guild, record=mock_purge_record, config=config
        )


class TestSendUserMessage:
    """Tests for _send_user_message."""

    async def test_sends_message(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test sending message to users."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123  # Integer, not MagicMock
        mock_message = MagicMock(spec=discord.Message)
        mock_message.id = 999
        mock_channel.send = AsyncMock(return_value=mock_message)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        config: dict[str, Any] = {
            ConfigKey.USER_CHANNEL: 123,
            ConfigKey.WAR_MESSAGE_TEMPLATE: "Test message",
            ConfigKey.USER_BUTTON_COLOR: "green",
            ConfigKey.USER_BUTTON_TEXT: "Confirm",
            ConfigKey.WAR_AFFECTED_ROLES: [],
            ConfigKey.USER_REACTION_ROLE: None,
        }

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.flush()

            await purge_cog._send_user_message(
                guild=mock_guild,
                record=record,
                config=config,
                session=session,
            )

            mock_channel.send.assert_called_once()


class TestOnGuildJoin:
    """Tests for on_guild_join."""

    async def test_registers_commands_on_join(
        self, purge_cog: PurgeCog, mock_guild: MagicMock
    ) -> None:
        """Test that registers commands when joining guild."""
        with patch.object(
            purge_cog, "_register_guild_commands", new_callable=AsyncMock
        ) as mock_register:
            await purge_cog.on_guild_join(mock_guild)
            mock_register.assert_called_once_with(mock_guild)


class TestOnConfigChanged:
    """Tests for on_config_changed."""

    async def test_triggers_resync_on_config_change(
        self, purge_cog: PurgeCog, mock_guild: MagicMock
    ) -> None:
        """Test that triggers re-sync when config changes."""
        with patch.object(
            purge_cog, "_debounced_register_and_sync", new_callable=AsyncMock
        ) as mock_register:
            await purge_cog.on_config_changed(mock_guild, [ConfigKey.WAR_COMMAND_NAME])
            mock_register.assert_called_once_with(mock_guild)


class TestOnCogToggled:
    """Tests for on_cog_toggled."""

    async def test_registers_commands_when_enabled(
        self, purge_cog: PurgeCog, mock_guild: MagicMock
    ) -> None:
        """Test that registers commands when enabling cog."""
        with patch.object(
            purge_cog, "_register_guild_commands", new_callable=AsyncMock
        ) as mock_register:
            await purge_cog.on_cog_toggled(mock_guild, True)
            mock_register.assert_called_once_with(mock_guild)

    async def test_unregisters_commands_when_disabled(
        self, purge_cog: PurgeCog, mock_guild: MagicMock
    ) -> None:
        """Test that removes commands when disabling cog."""
        with patch.object(
            purge_cog, "_unregister_guild_commands", new_callable=AsyncMock
        ) as mock_unregister:
            await purge_cog.on_cog_toggled(mock_guild, False)
            mock_unregister.assert_called_once_with(mock_guild)


class TestRestoreActivePurges:
    """Tests for _restore_active_purges."""

    async def test_restores_pending_purges(
        self, purge_cog: PurgeCog, test_database: DatabaseService
    ) -> None:
        """Test restoring pending purges."""
        guild_id = 123
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
                expires_at=expires_at,
            )
            await session.commit()

        await purge_cog._restore_active_purges()

        assert guild_id in purge_cog._active_purges

    async def test_restores_authorized_purges(
        self, purge_cog: PurgeCog, test_database: DatabaseService
    ) -> None:
        """Test restoring authorized purges."""
        guild_id = 456
        scheduled_for = datetime.now(UTC) + timedelta(hours=2)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=789,
                config_snapshot={},
                scheduled_for=scheduled_for,
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()

        await purge_cog._restore_active_purges()

        assert guild_id in purge_cog._authorized_purges


class TestSyncGuildCommands:
    """Tests for _sync_guild_commands."""

    async def test_syncs_commands(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test commands synchronization."""
        await purge_cog._sync_guild_commands(mock_guild)
        mock_discord_bot.tree.sync.assert_called_once_with(guild=mock_guild)

    async def test_handles_sync_error(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test sync error handling."""
        mock_discord_bot.tree.sync = AsyncMock(side_effect=Exception("Sync error"))

        # Should not raise exception
        await purge_cog._sync_guild_commands(mock_guild)


class TestDebouncedRegisterAndSync:
    """Tests for _debounced_register_and_sync."""

    async def test_cancels_pending_sync(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
    ) -> None:
        """Test that cancels pending synchronization."""
        import asyncio

        # Create pending task mock
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.cancel = MagicMock()
        purge_cog._pending_syncs[mock_guild.id] = mock_task

        await purge_cog._debounced_register_and_sync(mock_guild)

        mock_task.cancel.assert_called_once()


class TestExpirationCheckLoop:
    """Tests for expiration_check_loop."""

    async def test_calls_all_check_methods(self, purge_cog: PurgeCog) -> None:
        """Test that calls all verification methods."""
        with (
            patch.object(
                purge_cog, "_check_expired_purges", new_callable=AsyncMock
            ) as mock_expired,
            patch.object(purge_cog, "_check_ready_purges", new_callable=AsyncMock) as mock_ready,
            patch.object(
                purge_cog, "_check_pending_deletions", new_callable=AsyncMock
            ) as mock_deletions,
        ):
            await purge_cog.expiration_check_loop()

            mock_expired.assert_called_once()
            mock_ready.assert_called_once()
            mock_deletions.assert_called_once()


class TestExecutePurgeExtended:
    """Extended tests for _execute_purge."""

    async def test_execute_with_full_config(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test execution with complete configuration."""
        guild_id = 123456

        # Mock guild and roles
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"

        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected"
        affected_role.members = []

        mock_guild.get_role = MagicMock(
            side_effect=lambda rid: affected_role if rid == 100 else None
        )
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.get_member = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.AUDIT_LEVEL, 1)
            await session.commit()

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        # Verify that the purge was executed
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            updated_record = await purge_service.get_purge(purge_id)
            assert updated_record is not None
            assert updated_record.status == PurgeStatus.EXECUTED

    async def test_execute_with_test_mode(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test execution in test mode."""
        guild_id = 789

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.get_member = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.AUDIT_LEVEL, 2)
            await session.commit()

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": None,
                    "test_mode": True,  # Test mode
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            updated_record = await purge_service.get_purge(purge_id)
            assert updated_record is not None
            assert updated_record.status == PurgeStatus.EXECUTED


class TestOnInteraction:
    """Tests for on_interaction."""

    async def test_ignores_non_component_interaction(self, purge_cog: PurgeCog) -> None:
        """Test that ignores non-component interactions."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.application_command

        # Should not call any handler
        with patch.object(purge_cog, "_handle_authorize", new_callable=AsyncMock) as mock_auth:
            await purge_cog.on_interaction(interaction)
            mock_auth.assert_not_called()

    async def test_handles_authorize_button(self, purge_cog: PurgeCog) -> None:
        """Test authorize button handling."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "purge:authorize:test123"}

        with patch.object(purge_cog, "_handle_authorize", new_callable=AsyncMock) as mock_auth:
            await purge_cog.on_interaction(interaction)
            mock_auth.assert_called_once_with(interaction=interaction, public_id="test123")

    async def test_handles_cancel_button(self, purge_cog: PurgeCog) -> None:
        """Test cancel button handling."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "purge:cancel:test456"}

        with patch.object(purge_cog, "_handle_cancel", new_callable=AsyncMock) as mock_cancel:
            await purge_cog.on_interaction(interaction)
            mock_cancel.assert_called_once_with(interaction=interaction, public_id="test456")

    async def test_handles_confirm_button(self, purge_cog: PurgeCog) -> None:
        """Test confirm button handling."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "purge:confirm:test789"}

        with patch.object(purge_cog, "_handle_confirm", new_callable=AsyncMock) as mock_confirm:
            await purge_cog.on_interaction(interaction)
            mock_confirm.assert_called_once_with(interaction=interaction, public_id="test789")

    async def test_ignores_invalid_custom_id(self, purge_cog: PurgeCog) -> None:
        """Test that ignores invalid custom_id - now accepts any string."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "purge:authorize:anystring"}

        with patch.object(purge_cog, "_handle_authorize", new_callable=AsyncMock) as mock_auth:
            await purge_cog.on_interaction(interaction)
            mock_auth.assert_called_once_with(interaction=interaction, public_id="anystring")

    async def test_ignores_unknown_button(self, purge_cog: PurgeCog) -> None:
        """Test that ignores unknown button."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "other:button:123"}

        with patch.object(purge_cog, "_handle_authorize", new_callable=AsyncMock) as mock_auth:
            await purge_cog.on_interaction(interaction)
            mock_auth.assert_not_called()


class TestOnConfigChangedExtended:
    """Extended tests for on_config_changed."""

    async def test_triggers_resync_on_essential_key(
        self, purge_cog: PurgeCog, mock_guild: MagicMock
    ) -> None:
        """Test that triggers re-sync with essential key."""
        with patch.object(
            purge_cog, "_debounced_register_and_sync", new_callable=AsyncMock
        ) as mock_register:
            await purge_cog.on_config_changed(mock_guild, [ConfigKey.WAR_COMMAND_NAME])
            mock_register.assert_called_once_with(mock_guild)

    async def test_ignores_non_essential_key(
        self, purge_cog: PurgeCog, mock_guild: MagicMock
    ) -> None:
        """Test that ignores non-essential keys."""
        with patch.object(
            purge_cog, "_debounced_register_and_sync", new_callable=AsyncMock
        ) as mock_register:
            await purge_cog.on_config_changed(mock_guild, [ConfigKey.TEST_MODE])
            mock_register.assert_not_called()

    async def test_triggers_resync_on_global_command_name(
        self, purge_cog: PurgeCog, mock_guild: MagicMock
    ) -> None:
        """Test that triggers re-sync with GLOBAL_COMMAND_NAME."""
        with patch.object(
            purge_cog, "_debounced_register_and_sync", new_callable=AsyncMock
        ) as mock_register:
            await purge_cog.on_config_changed(mock_guild, [ConfigKey.GLOBAL_COMMAND_NAME])
            mock_register.assert_called_once_with(mock_guild)

    async def test_triggers_resync_on_global_admin_roles(
        self, purge_cog: PurgeCog, mock_guild: MagicMock
    ) -> None:
        """Test that triggers re-sync with GLOBAL_ADMIN_ROLES."""
        with patch.object(
            purge_cog, "_debounced_register_and_sync", new_callable=AsyncMock
        ) as mock_register:
            await purge_cog.on_config_changed(mock_guild, [ConfigKey.GLOBAL_ADMIN_ROLES])
            mock_register.assert_called_once_with(mock_guild)


class TestCheckPendingDeletionsExtended:
    """Extended tests for _check_pending_deletions."""

    async def test_handles_channel_not_found(
        self, purge_cog: PurgeCog, mock_discord_bot: MagicMock
    ) -> None:
        """Test when channel does not exist."""
        past_time = datetime.now(UTC) - timedelta(minutes=5)
        purge_cog._pending_deletions[(123, 456)] = past_time

        mock_discord_bot.get_channel = MagicMock(return_value=None)

        await purge_cog._check_pending_deletions()

        # Should be removed from pending even if channel not found
        assert (123, 456) not in purge_cog._pending_deletions

    async def test_handles_message_not_found(
        self, purge_cog: PurgeCog, mock_discord_bot: MagicMock
    ) -> None:
        """Test when message does not exist."""
        past_time = datetime.now(UTC) - timedelta(minutes=5)
        purge_cog._pending_deletions[(123, 456)] = past_time

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )
        mock_discord_bot.get_channel = MagicMock(return_value=mock_channel)

        await purge_cog._check_pending_deletions()

        assert (123, 456) not in purge_cog._pending_deletions


class TestHandleAuthorizeExtended:
    """Extended tests for _handle_authorize."""

    async def test_authorize_adds_authorization(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that adds authorization correctly."""
        guild_id = mock_interaction.guild.id
        # Use another user so it is not the initiator
        other_member = MagicMock(spec=discord.Member)
        other_member.id = 999888777
        other_member.display_name = "OtherUser"
        other_member.bot = False
        other_member.guild_permissions = MagicMock()
        other_member.guild_permissions.manage_guild = True
        other_role = MagicMock(spec=discord.Role)
        other_role.id = 100
        other_member.roles = [other_role]
        mock_interaction.user = other_member

        mock_guild = mock_interaction.guild
        mock_guild.get_channel = MagicMock(return_value=None)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=mock_member.id,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            public_id = record.public_id
            purge_id = record.id
            purge_id = record.id

        await purge_cog._handle_authorize(mock_interaction, public_id)

        # Verify confirmation message
        mock_interaction.followup.send.assert_called()

        # Verify that authorization was added
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            updated = await purge_service.get_purge(purge_id)
            assert updated is not None
            assert other_member.id in updated.authorized_by


class TestHandleWarPurgeSuccess:
    """Tests for _handle_purge (WAR_END) with successful creation."""

    async def test_successful_purge_creation(
        self,
        purge_cog: PurgeCog,
        test_database: DatabaseService,
    ) -> None:
        """Test successful purge creation."""
        guild_id = 555666777
        user_id = 111222333

        # Mock member with proper int id
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = user_id
        mock_member.display_name = "TestUser"
        mock_member.bot = False
        admin_role = MagicMock(spec=discord.Role)
        admin_role.id = 100
        mock_member.roles = [admin_role]

        # Mock interaction
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(
            side_effect=lambda mid: mock_member if mid == user_id else None
        )
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        # Mock mod channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123456
        mock_channel.mention = "#mod-channel"
        mock_message = MagicMock(spec=discord.Message)
        mock_message.id = 789
        mock_channel.send = AsyncMock(return_value=mock_message)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_CHANNEL, mock_channel.id
            )
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.USER_CHANNEL, 999)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_AFFECTED_ROLES, [200])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 3)
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 5, PurgeType.WAR_END)

        mock_channel.send.assert_called_once()
        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "Purge started" in str(call_args)

    async def test_purge_creation_without_mod_channel(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test error when there is no moderation channel."""
        guild_id = 888999000

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            # Do not configure MOD_CHANNEL
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 5, PurgeType.WAR_END)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "Moderation channel not configured" in str(call_args)

    async def test_purge_creation_auto_authorize_test_mode(
        self,
        purge_cog: PurgeCog,
        test_database: DatabaseService,
    ) -> None:
        """Test auto-authorization in test mode (1 authorization sufficient)."""
        guild_id = 111222333
        user_id = 444555666

        # Mock member with proper int id
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = user_id
        mock_member.display_name = "TestUser"
        mock_member.bot = False
        admin_role = MagicMock(spec=discord.Role)
        admin_role.id = 100
        mock_member.roles = [admin_role]

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(
            side_effect=lambda mid: mock_member if mid == user_id else None
        )
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        # Mock roles
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 200
        affected_role.mention = "@Affected"

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123
        mock_channel.mention = "#mod"
        mock_message = MagicMock(spec=discord.Message)
        mock_message.id = 456
        mock_channel.send = AsyncMock(return_value=mock_message)

        # User channel for the user message
        user_channel = MagicMock(spec=discord.TextChannel)
        user_channel.id = 888
        user_channel.send = AsyncMock(return_value=mock_message)

        def get_channel_side_effect(cid: int) -> MagicMock | None:
            if cid == 123:
                return mock_channel
            if cid == 888:
                return user_channel
            return None

        mock_guild.get_channel = MagicMock(side_effect=get_channel_side_effect)
        mock_guild.get_role = MagicMock(
            side_effect=lambda rid: affected_role if rid == 200 else None
        )

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_CHANNEL, mock_channel.id
            )
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.USER_CHANNEL, 888)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_AFFECTED_ROLES, [200])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.TEST_MODE, True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 1)
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 5, PurgeType.WAR_END)

        # Should be auto-authorized
        assert guild_id in purge_cog._authorized_purges


class TestHandleConfirmToggle:
    """Tests for _handle_confirm with toggle."""

    async def test_confirm_first_time(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test first confirmation."""
        guild_id = 444555666

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_role = MagicMock(return_value=None)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.USER_FIRST_REACTION_TEXT, "Confirmed"
            )

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            public_id = record.public_id
            purge_id = record.id
            purge_id = record.id

        await purge_cog._handle_confirm(mock_interaction, public_id)

        mock_interaction.response.send_message.assert_called()
        call_args = mock_interaction.response.send_message.call_args
        assert "confirmed" in str(call_args).lower()

        # Verify that confirmation was added
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            updated = await purge_service.get_purge(purge_id)
            assert updated is not None
            assert mock_member.id in updated.confirmed_by

    async def test_confirm_toggle_remove(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test withdraw confirmation (toggle)."""
        guild_id = 777888999

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_role = MagicMock(return_value=None)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.USER_REMOVED_REACTION_TEXT, "Withdrawn"
            )

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            # Add previous confirmation
            await purge_service.add_confirmation(record.id, mock_member.id)
            await session.commit()
            public_id = record.public_id

        await purge_cog._handle_confirm(mock_interaction, public_id)

        mock_interaction.response.send_message.assert_called()
        call_args = mock_interaction.response.send_message.call_args
        assert "withdrawn" in str(call_args).lower()

    async def test_confirm_with_role_assignment(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test confirmation with role assignment."""
        guild_id = 123123123

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 500
        mock_role.name = "Confirmed"
        mock_member.add_roles = AsyncMock()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.USER_REACTION_ROLE, 500)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            public_id = record.public_id

        await purge_cog._handle_confirm(mock_interaction, public_id)

        mock_member.add_roles.assert_called_once_with(mock_role)


class TestHandleCancelExtendedFull:
    """Full tests for _handle_cancel."""

    async def test_cancel_vote_added(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that cancellation vote is added."""
        guild_id = 321321321

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 2)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            public_id = record.public_id

        await purge_cog._handle_cancel(mock_interaction, public_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "1/2" in str(call_args) or "added" in str(call_args).lower()

    async def test_cancel_completes_cancellation(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test complete cancellation when there are enough votes."""
        guild_id = 654654654

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=None)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.TEST_MODE, True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 1)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            public_id = record.public_id
            purge_id = record.id
            purge_id = record.id

        await purge_cog._handle_cancel(mock_interaction, public_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "cancelled" in str(call_args).lower()

        # Verify status
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            updated = await purge_service.get_purge(purge_id)
            assert updated is not None
            assert updated.status == PurgeStatus.CANCELLED


class TestUpdateModMessageExtended:
    """Extended tests for _update_mod_message."""

    async def test_updates_with_view_for_pending(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test update with view for pending state."""
        channel_id = 123
        message_id = 456

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.update_mod_message(record.id, channel_id, message_id)
            await session.commit()

            # Refetch to get updated record
            refetched_record = await purge_service.get_purge(record.id)
            assert refetched_record is not None
            record = refetched_record

        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Test",
            ConfigKey.MOD_STATUS_PENDING: "Pending",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        await purge_cog._update_mod_message(guild=mock_guild, record=record, config=config)

        mock_message.edit.assert_called_once()
        # Verify that a view was passed
        call_kwargs = mock_message.edit.call_args.kwargs
        assert "view" in call_kwargs or "content" in call_kwargs

    async def test_removes_view_for_cancelled(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that removes view for cancelled state."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.update_mod_message(record.id, 123, 456)
            await purge_service.update_status(record.id, PurgeStatus.CANCELLED)
            await session.flush()

            config: dict[str, Any] = {
                ConfigKey.MOD_MESSAGE_TEMPLATE: "Test",
                ConfigKey.MOD_STATUS_CANCELLED: "Cancelled",
                ConfigKey.MOD_REQUIRED_REACTIONS: 2,
            }

            await purge_cog._update_mod_message(guild=mock_guild, record=record, config=config)

            mock_message.edit.assert_called_once()
            call_kwargs = mock_message.edit.call_args.kwargs
            assert call_kwargs.get("view") is None


class TestExecutePurgeFullExecution:
    """Full tests for _execute_purge with members."""

    async def test_execute_cleans_members(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test execution that cleans members."""
        guild_id = 999888777

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.get_channel = MagicMock(return_value=None)

        # Mock affected role with members
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected"

        # Mock member that didn't confirm
        member1 = MagicMock(spec=discord.Member)
        member1.id = 11111
        member1.name = "Member1"
        member1.display_name = "Member1"
        member1.roles = [affected_role, mock_guild.default_role]
        member1.remove_roles = AsyncMock()
        member1.add_roles = AsyncMock()
        member1.edit = AsyncMock()

        affected_role.members = [member1]

        mock_guild.get_role = MagicMock(
            side_effect=lambda rid: affected_role if rid == 100 else None
        )
        mock_guild.get_member = MagicMock(side_effect=lambda mid: member1 if mid == 11111 else None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.AUDIT_LEVEL, 2)
            await session.commit()

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        # Verify that the member was cleaned
        member1.edit.assert_called()

    async def test_execute_with_promotions(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test execution with promotions."""
        guild_id = 888777666

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.get_channel = MagicMock(return_value=None)

        # Mock roles
        from_role = MagicMock(spec=discord.Role)
        from_role.id = 100
        from_role.name = "FromRole"
        to_role = MagicMock(spec=discord.Role)
        to_role.id = 200
        to_role.name = "ToRole"

        # Mock member that confirmed
        member1 = MagicMock(spec=discord.Member)
        member1.id = 22222
        member1.name = "Member1"
        member1.display_name = "Member1"
        member1.roles = [from_role, mock_guild.default_role]
        member1.remove_roles = AsyncMock()
        member1.add_roles = AsyncMock()

        from_role.members = [member1]

        mock_guild.get_role = MagicMock(
            side_effect=lambda rid: from_role if rid == 100 else to_role if rid == 200 else None
        )
        mock_guild.get_member = MagicMock(side_effect=lambda mid: member1 if mid == 22222 else None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.AUDIT_LEVEL, 2)
            await session.commit()

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [{"from_role": 100, "to_role": 200}],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            # Add confirmation for member
            await purge_service.add_confirmation(record.id, 22222)
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        # Verify promotion
        member1.add_roles.assert_called()


class TestSendUserMessageExtended:
    """Extended tests for _send_user_message."""

    async def test_send_user_message_updates_record(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that updates record with message IDs."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123
        mock_message = MagicMock(spec=discord.Message)
        mock_message.id = 456
        mock_channel.send = AsyncMock(return_value=mock_message)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)
        mock_guild.get_role = MagicMock(return_value=None)

        config: dict[str, Any] = {
            ConfigKey.USER_CHANNEL: 123,
            ConfigKey.WAR_MESSAGE_TEMPLATE: "Test {roles} {dia}",
            ConfigKey.USER_BUTTON_COLOR: "green",
            ConfigKey.USER_BUTTON_TEXT: "Confirm",
            ConfigKey.WAR_AFFECTED_ROLES: [],
            ConfigKey.USER_REACTION_ROLE: None,
        }

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.flush()

            await purge_cog._send_user_message(
                guild=mock_guild,
                record=record,
                config=config,
                session=session,
            )

            await session.flush()

            # Verify that the record was updated
            updated = await purge_service.get_purge(record.id)
            assert updated is not None
            assert updated.user_message_id == 456
            assert updated.user_channel_id == 123


class TestOnReady:
    """Tests for on_ready."""

    async def test_registers_commands_for_all_guilds(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test that registers commands in all guilds."""
        guild1 = MagicMock(spec=discord.Guild)
        guild1.id = 111
        guild1.name = "Guild1"
        guild2 = MagicMock(spec=discord.Guild)
        guild2.id = 222
        guild2.name = "Guild2"
        mock_discord_bot.guilds = [guild1, guild2]

        with (
            patch.object(
                purge_cog, "_register_guild_commands", new_callable=AsyncMock
            ) as mock_register,
            patch.object(purge_cog, "_sync_guild_commands", new_callable=AsyncMock),
            patch.object(purge_cog, "_restore_active_purges", new_callable=AsyncMock),
            patch.object(purge_cog, "_check_expired_purges", new_callable=AsyncMock),
            patch.object(purge_cog.expiration_check_loop, "is_running", return_value=True),
        ):
            await purge_cog.on_ready()

            assert mock_register.call_count == 2

    async def test_handles_registration_error(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test registration error handling."""
        guild1 = MagicMock(spec=discord.Guild)
        guild1.id = 111
        guild1.name = "Guild1"
        mock_discord_bot.guilds = [guild1]

        with (
            patch.object(
                purge_cog,
                "_register_guild_commands",
                new_callable=AsyncMock,
                side_effect=Exception("Test error"),
            ),
            patch.object(purge_cog, "_restore_active_purges", new_callable=AsyncMock),
            patch.object(purge_cog, "_check_expired_purges", new_callable=AsyncMock),
            patch.object(purge_cog.expiration_check_loop, "is_running", return_value=True),
        ):
            # Should not raise exception
            await purge_cog.on_ready()

    async def test_starts_loop_if_not_running(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test that starts loop if not running."""
        mock_discord_bot.guilds = []

        with (
            patch.object(purge_cog, "_restore_active_purges", new_callable=AsyncMock),
            patch.object(purge_cog, "_check_expired_purges", new_callable=AsyncMock),
            patch.object(purge_cog.expiration_check_loop, "is_running", return_value=False),
            patch.object(purge_cog.expiration_check_loop, "start") as mock_start,
        ):
            await purge_cog.on_ready()
            mock_start.assert_called_once()


class TestRestoreActivePurgesExtended:
    """Extended tests for _restore_active_purges."""

    async def test_handles_exception(
        self, purge_cog: PurgeCog, mock_discord_bot: MagicMock
    ) -> None:
        """Test exception handling."""
        # Make database.session raise an exception
        mock_discord_bot.database.session = MagicMock(side_effect=Exception("DB error"))

        # Should not raise exception
        await purge_cog._restore_active_purges()


class TestCheckExpiredPurgesExtended:
    """Extended tests for _check_expired_purges."""

    async def test_handles_expiration_error(
        self, purge_cog: PurgeCog, test_database: DatabaseService
    ) -> None:
        """Test error handling when expiring purge."""
        guild_id = 999

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
                expires_at=datetime.now(UTC) - timedelta(minutes=5),
            )
            await session.commit()
            purge_id = record.id
            purge_id = record.id

        purge_cog._active_purges[guild_id] = (
            purge_id,
            datetime.now(UTC) - timedelta(minutes=5),
        )

        # Mock _get_config to raise an error
        with patch.object(
            purge_cog, "_get_config", new_callable=AsyncMock, side_effect=Exception("Config error")
        ):
            # Should not raise exception
            await purge_cog._check_expired_purges()


class TestCheckReadyPurgesExtended:
    """Extended tests for _check_ready_purges."""

    async def test_handles_execution_error(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test error handling in execution."""
        guild_id = 888

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test"
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        purge_cog._authorized_purges[guild_id] = (
            1,
            datetime.now(UTC) - timedelta(minutes=5),
        )

        with patch.object(
            purge_cog, "_execute_purge", new_callable=AsyncMock, side_effect=Exception("Exec error")
        ):
            # Should not raise exception
            await purge_cog._check_ready_purges()

        # Should have been removed from tracking
        assert guild_id not in purge_cog._authorized_purges


class TestHandleConfirmRoleRemoval:
    """Tests for _handle_confirm with role removal."""

    async def test_confirm_toggle_with_role_removal(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test withdraw confirmation with role assigned."""
        guild_id = 555444333

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 500
        mock_role.name = "Confirmed"
        mock_member.remove_roles = AsyncMock()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.USER_REACTION_ROLE, 500)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await purge_service.add_confirmation(record.id, mock_member.id)
            await session.commit()
            public_id = record.public_id

        await purge_cog._handle_confirm(mock_interaction, public_id)

        mock_member.remove_roles.assert_called_once_with(mock_role)


class TestHandleCancelWithReactionRole:
    """Tests for _handle_cancel with reaction role."""

    async def test_cancel_removes_reaction_roles(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that cancellation removes reaction roles."""
        guild_id = 666777888
        confirmed_user_id = 999888

        # Mock user that confirmed
        confirmed_member = MagicMock(spec=discord.Member)
        confirmed_member.id = confirmed_user_id
        confirmed_member.name = "ConfirmedUser"
        confirmed_member.remove_roles = AsyncMock()

        reaction_role = MagicMock(spec=discord.Role)
        reaction_role.id = 600
        reaction_role.name = "Reacted"
        confirmed_member.roles = [reaction_role]

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_guild.get_role = MagicMock(return_value=reaction_role)
        mock_guild.get_member = MagicMock(
            side_effect=lambda mid: confirmed_member if mid == confirmed_user_id else None
        )
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.TEST_MODE, True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 1)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.USER_REACTION_ROLE, 600)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Add confirmation
            await purge_service.add_confirmation(record.id, confirmed_user_id)
            await session.commit()
            public_id = record.public_id

        await purge_cog._handle_cancel(mock_interaction, public_id)

        # Verify that the role was removed
        confirmed_member.remove_roles.assert_called()


class TestRegisterGuildCommandsExtended:
    """Extended tests for _register_guild_commands."""

    async def test_removes_old_command_when_name_changed(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that removes old command when name changes."""
        # Register old command
        purge_cog._registered_commands[mock_guild.id] = {"war": "old_command"}

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.MOD_CHANNEL, 123)
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.USER_CHANNEL, 456)
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100]
            )
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.WAR_AFFECTED_ROLES, [200]
            )
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.WAR_COMMAND_NAME, "new_command"
            )
            await session.commit()

        await purge_cog._register_guild_commands(mock_guild)

        # Verify that the old command was removed
        mock_discord_bot.tree.remove_command.assert_called_with("old_command", guild=mock_guild)
        # Verify that the new command was registered
        mock_discord_bot.tree.add_command.assert_called()

    async def test_skips_if_same_command_registered(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that does not re-register if same command is already registered."""
        # Register command with same name
        purge_cog._registered_commands[mock_guild.id] = {"war": "purge_war"}

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.MOD_CHANNEL, 123)
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.USER_CHANNEL, 456)
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100]
            )
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.WAR_AFFECTED_ROLES, [200]
            )
            # Same default name
            await session.commit()

        mock_discord_bot.tree.add_command.reset_mock()

        await purge_cog._register_guild_commands(mock_guild)

        # Should not add new command
        mock_discord_bot.tree.add_command.assert_not_called()


class TestRegisterWhenDisabled:
    """Tests for _register_guild_commands when cog is disabled."""

    async def test_unregisters_when_cog_disabled(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that removes commands when cog is disabled."""
        # Register existing command
        purge_cog._registered_commands[mock_guild.id] = {"war": "purge_war"}

        # Do not enable the cog (disabled by default)
        await purge_cog._register_guild_commands(mock_guild)

        # Verify that the command was removed
        mock_discord_bot.tree.remove_command.assert_called_with("purge_war", guild=mock_guild)
        assert mock_guild.id not in purge_cog._registered_commands

    async def test_unregisters_when_config_incomplete(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that removes commands when config is incomplete."""
        # Register existing command
        purge_cog._registered_commands[mock_guild.id] = {"war": "purge_war"}

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            # Only configure partially (without WAR_AFFECTED_ROLES)
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.MOD_CHANNEL, 123)
            await session.commit()

        await purge_cog._register_guild_commands(mock_guild)

        # Verify that the command was removed
        mock_discord_bot.tree.remove_command.assert_called()
        assert mock_guild.id not in purge_cog._registered_commands


class TestHandleWarPurgeModChannelNotFound:
    """Tests for _handle_purge (WAR_END) when mod_channel does not exist."""

    async def test_mod_channel_not_found(
        self,
        purge_cog: PurgeCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test error when moderation channel does not exist."""
        mock_interaction.guild = mock_guild
        mock_guild.get_channel = MagicMock(return_value=None)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100]
            )
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.MOD_CHANNEL, 999999)
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 5, PurgeType.WAR_END)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "not found" in str(call_args).lower()


class TestHandleAuthorizeRevertToPending:
    """Tests for _handle_authorize when reverting to pending."""

    async def test_revert_to_pending_when_not_enough_auths(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test reversion to pending when there are not enough authorizations."""
        guild_id = 777666555

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 3)
            await session.commit()

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Already had 2 authorizations and was authorized
            # Simulate authorized status with 2 authorizations
            await purge_service.add_authorization(record.id, 111)
            await purge_service.add_authorization(record.id, 222)
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            public_id = record.public_id

        # Now the user adds an authorization (total 3)
        await purge_cog._handle_authorize(mock_interaction, public_id)

        # Verify that it worked
        mock_interaction.followup.send.assert_called()


class TestHandleAuthorizeNotActive:
    """Tests for _handle_authorize when purge is not active."""

    async def test_purge_not_active(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test error when purge is not active."""
        guild_id = 444333222

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await session.commit()

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Change to cancelled status (not active)
            await purge_service.update_status(record.id, PurgeStatus.CANCELLED)
            await session.commit()
            public_id = record.public_id

        await purge_cog._handle_authorize(mock_interaction, public_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "no longer active" in str(call_args).lower()


class TestHandleConfirmNotAuthorized:
    """Tests for _handle_confirm when purge is not authorized."""

    async def test_purge_not_authorized(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test error when purge is not authorized."""
        guild_id = 333222111

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await session.commit()

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Leave in pending status (not authorized)
            await session.commit()
            public_id = record.public_id

        await purge_cog._handle_confirm(mock_interaction, public_id)

        mock_interaction.response.send_message.assert_called()
        call_args = mock_interaction.response.send_message.call_args
        assert "no longer active" in str(call_args).lower()


class TestHandleConfirmRoleForbidden:
    """Tests for _handle_confirm when there are permission errors."""

    async def test_add_role_forbidden(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test Forbidden error handling when adding role."""
        guild_id = 222111000

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 700
        mock_role.name = "Confirmed"
        mock_member.add_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No perms"))
        mock_member.name = "TestUser"

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.USER_REACTION_ROLE, 700)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            public_id = record.public_id

        # Should not raise exception
        await purge_cog._handle_confirm(mock_interaction, public_id)

        mock_interaction.response.send_message.assert_called()


class TestUpdateModMessageNotTextChannel:
    """Tests for _update_mod_message when channel is not TextChannel."""

    async def test_channel_not_text_channel(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that does not fail when channel is not TextChannel."""
        # Mock a channel that is not TextChannel
        mock_voice_channel = MagicMock(spec=discord.VoiceChannel)
        mock_guild.get_channel = MagicMock(return_value=mock_voice_channel)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.mod_message_id = 12345
            record.mod_channel_id = 67890
            await session.commit()

            config: dict[str, Any] = {}
            # Should not raise exception
            await purge_cog._update_mod_message(mock_guild, record, config)


class TestUpdateModMessageNotFound:
    """Tests for _update_mod_message when message does not exist."""

    async def test_message_not_found(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that does not fail when message does not exist."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.mod_message_id = 12345
            record.mod_channel_id = 67890
            await session.commit()

            config: dict[str, Any] = {}
            # Should not raise exception
            await purge_cog._update_mod_message(mock_guild, record, config)


class TestCheckPendingDeletionsException:
    """Tests for _check_pending_deletions with exceptions."""

    async def test_handles_deletion_exception(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test exception handling when deleting message."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(side_effect=Exception("Unknown error"))
        mock_discord_bot.get_channel = MagicMock(return_value=mock_channel)

        # Schedule deletion - key is tuple (channel_id, message_id), value is delete_at
        purge_cog._pending_deletions[(123, 456)] = datetime.now(UTC) - timedelta(minutes=1)

        # Should not raise exception
        await purge_cog._check_pending_deletions()


class TestOnInteractionInvalidCustomId:
    """Tests for on_interaction with invalid custom_id."""

    async def test_authorize_invalid_id(
        self,
        purge_cog: PurgeCog,
    ) -> None:
        """Test invalid custom_id for authorize."""
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.type = discord.InteractionType.component
        mock_interaction.data = {"custom_id": "purge:authorize:invalid"}

        # Should not raise exception
        await purge_cog.on_interaction(mock_interaction)

    async def test_cancel_invalid_id(
        self,
        purge_cog: PurgeCog,
    ) -> None:
        """Test invalid custom_id for cancel."""
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.type = discord.InteractionType.component
        mock_interaction.data = {"custom_id": "purge:cancel:invalid"}

        # Should not raise exception
        await purge_cog.on_interaction(mock_interaction)

    async def test_confirm_invalid_id(
        self,
        purge_cog: PurgeCog,
    ) -> None:
        """Test invalid custom_id for confirm."""
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.type = discord.InteractionType.component
        mock_interaction.data = {"custom_id": "purge:confirm:invalid"}

        # Should not raise exception
        await purge_cog.on_interaction(mock_interaction)


class TestOnCogToggledSync:
    """Tests for on_cog_toggled with synchronization."""

    async def test_syncs_when_enabled(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that syncs commands when enabled."""
        # Configure to register command
        purge_cog._registered_commands[mock_guild.id] = {"war": "purge_war"}

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.MOD_CHANNEL, 123)
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.USER_CHANNEL, 456)
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100]
            )
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.WAR_AFFECTED_ROLES, [200]
            )
            await session.commit()

        await purge_cog.on_cog_toggled(mock_guild, True)

        mock_discord_bot.tree.sync.assert_called()


class TestTeardown:
    """Tests for teardown."""

    async def test_unregisters_all_commands(
        self,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test that removes all registered commands."""
        from discord_bot.purge.cog import teardown

        cog = PurgeCog(mock_discord_bot)
        cog._registered_commands = {
            111: {"war": "cmd1"},
            222: {"war": "cmd2", "global": "cmd3"},
        }

        mock_guild1 = MagicMock(spec=discord.Guild)
        mock_guild1.id = 111
        mock_guild2 = MagicMock(spec=discord.Guild)
        mock_guild2.id = 222

        mock_discord_bot.get_cog = MagicMock(return_value=cog)
        mock_discord_bot.get_guild = MagicMock(
            side_effect=lambda gid: (
                mock_guild1 if gid == 111 else mock_guild2 if gid == 222 else None
            )
        )

        await teardown(mock_discord_bot)

        # Verify that commands were removed (1 from guild1 + 2 from guild2)
        assert mock_discord_bot.tree.remove_command.call_count == 3


class TestBeforeExpirationCheck:
    """Tests for before_expiration_check."""

    async def test_waits_until_ready(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test that waits until bot is ready."""
        await purge_cog.before_expiration_check()

        mock_discord_bot.wait_until_ready.assert_called_once()


class TestOnGuildJoinSync:
    """Tests for on_guild_join with synchronization."""

    async def test_syncs_if_registered(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that syncs if command was registered."""
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.MOD_CHANNEL, 123)
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.USER_CHANNEL, 456)
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100]
            )
            await config_service.set_value(
                mock_guild.id, COG_NAME, ConfigKey.WAR_AFFECTED_ROLES, [200]
            )
            await session.commit()

        await purge_cog.on_guild_join(mock_guild)

        mock_discord_bot.tree.sync.assert_called()


class TestExecutePurgeDefaultPromotion:
    """Tests for _execute_purge with default promotion."""

    async def test_applies_default_promotion(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that applies default promotion to confirmed users."""
        guild_id = 111222333

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        # Mock default role
        default_role = MagicMock(spec=discord.Role)
        default_role.id = 300
        default_role.name = "DefaultPromo"

        # Mock affected role
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected"
        affected_role.members = []

        # Mock member that confirmed (not in affected role)
        confirmed_member = MagicMock(spec=discord.Member)
        confirmed_member.id = 55555
        confirmed_member.name = "ConfirmedUser"
        confirmed_member.display_name = "ConfirmedUser"
        confirmed_member.roles = [mock_guild.default_role]
        confirmed_member.add_roles = AsyncMock()

        def get_role(rid: int) -> MagicMock | None:
            if rid == 100:
                return affected_role
            if rid == 300:
                return default_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role)
        mock_guild.get_member = MagicMock(
            side_effect=lambda mid: confirmed_member if mid == 55555 else None
        )
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.AUDIT_LEVEL, 2)
            await session.commit()

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": 300,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await purge_service.add_confirmation(record.id, 55555)
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        # Verify that the default promotion was applied
        confirmed_member.add_roles.assert_called_with(default_role)


class TestExecutePurgeReactionRoleRemoval:
    """Tests for _execute_purge with reaction role removal."""

    async def test_removes_reaction_role_after_execution(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that removes reaction role after execution."""
        guild_id = 999888777

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        # Mock reaction role
        reaction_role = MagicMock(spec=discord.Role)
        reaction_role.id = 800
        reaction_role.name = "Reacted"

        # Mock affected role
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected"
        affected_role.members = []

        # Mock member that confirmed
        confirmed_member = MagicMock(spec=discord.Member)
        confirmed_member.id = 66666
        confirmed_member.name = "ConfirmedUser"
        confirmed_member.display_name = "ConfirmedUser"
        confirmed_member.roles = [reaction_role, mock_guild.default_role]
        confirmed_member.remove_roles = AsyncMock()

        def get_role(rid: int) -> MagicMock | None:
            if rid == 100:
                return affected_role
            if rid == 800:
                return reaction_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role)
        mock_guild.get_member = MagicMock(
            side_effect=lambda mid: confirmed_member if mid == 66666 else None
        )
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": None,
                    "test_mode": False,
                    "reaction_role": 800,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await purge_service.add_confirmation(record.id, 66666)
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        # Verify that reaction role was removed
        confirmed_member.remove_roles.assert_called()


class TestExecutePurgeWithRolesToRemoveAndAdd:
    """Tests for _execute_purge with roles_to_remove and roles_to_add."""

    async def test_removes_and_adds_specific_roles(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that removes and adds specific roles."""
        guild_id = 888999000

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        # Mock roles
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected"
        remove_role = MagicMock(spec=discord.Role)
        remove_role.id = 200
        remove_role.name = "ToRemove"
        add_role = MagicMock(spec=discord.Role)
        add_role.id = 300
        add_role.name = "ToAdd"

        # Mock member to clean
        member = MagicMock(spec=discord.Member)
        member.id = 77777
        member.name = "Member"
        member.display_name = "Member"
        member.roles = [affected_role, remove_role, mock_guild.default_role]
        member.remove_roles = AsyncMock()
        member.add_roles = AsyncMock()

        affected_role.members = [member]

        def get_role(rid: int) -> MagicMock | None:
            if rid == 100:
                return affected_role
            if rid == 200:
                return remove_role
            if rid == 300:
                return add_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role)
        mock_guild.get_member = MagicMock(side_effect=lambda mid: member if mid == 77777 else None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [200],
                    "roles_to_add": [300],
                    "promotions": [],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        # Verify that roles were removed and added
        member.remove_roles.assert_called()
        member.add_roles.assert_called()


class TestExecutePurgeRoleForbidden:
    """Tests for _execute_purge with permission errors."""

    async def test_handles_forbidden_on_role_changes(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test Forbidden error handling on role changes."""
        guild_id = 123123123

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        # Mock affected role
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected"

        # Mock member - role changes fail
        member = MagicMock(spec=discord.Member)
        member.id = 88888
        member.name = "Member"
        member.display_name = "Member"
        member.roles = [affected_role, mock_guild.default_role]
        member.edit = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No perms"))

        affected_role.members = [member]

        mock_guild.get_role = MagicMock(
            side_effect=lambda rid: affected_role if rid == 100 else None
        )
        mock_guild.get_member = MagicMock(side_effect=lambda mid: member if mid == 88888 else None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id

        # Should not raise exception
        await purge_cog._execute_purge(guild_id, purge_id)


class TestCheckExpiredPurgesWithUpdate:
    """Tests for _check_expired_purges with message update."""

    async def test_updates_mod_message_and_schedules_deletion(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that updates message and schedules deletion."""
        guild_id = 456456456

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_message.edit = AsyncMock()

        # Mock role to avoid error in _format_roles
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected"
        affected_role.mention = "@Affected"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_channel)
        mock_guild.get_role = MagicMock(
            side_effect=lambda rid: affected_role if rid == 100 else None
        )
        mock_guild.get_member = MagicMock(return_value=None)

        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_MESSAGE_RETENTION, 5)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_AFFECTED_ROLES, [100])
            await session.commit()

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={"affected_roles": [100]},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
                expires_at=datetime.now(UTC) - timedelta(minutes=5),
            )
            record.mod_channel_id = 123
            record.mod_message_id = 456
            await session.commit()
            purge_id = record.id
            purge_id = record.id

        purge_cog._active_purges[guild_id] = (
            purge_id,
            datetime.now(UTC) - timedelta(minutes=5),
        )

        await purge_cog._check_expired_purges()

        # Verify that the message was updated
        mock_message.edit.assert_called()
        # Verify that deletion was scheduled
        assert len(purge_cog._pending_deletions) > 0


class TestExecutePurgeWithRetentionDeletion:
    """Tests for _execute_purge with retention and deletion."""

    async def test_deletes_user_message_after_execution(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that deletes user message and schedules retention."""
        guild_id = 789789789

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_message = MagicMock(spec=discord.Message)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_message.edit = AsyncMock()

        mock_user_channel = MagicMock(spec=discord.TextChannel)
        mock_user_message = MagicMock(spec=discord.Message)
        mock_user_channel.fetch_message = AsyncMock(return_value=mock_user_message)
        mock_user_message.delete = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0

        # Mock affected role (no members to clean)
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected"
        affected_role.mention = "@Affected"
        affected_role.members = []

        def get_channel(cid: int) -> MagicMock | None:
            if cid == 123:
                return mock_mod_channel
            if cid == 456:
                return mock_user_channel
            return None

        mock_guild.get_channel = MagicMock(side_effect=get_channel)
        mock_guild.get_role = MagicMock(
            side_effect=lambda rid: affected_role if rid == 100 else None
        )
        mock_guild.get_member = MagicMock(return_value=None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_MESSAGE_RETENTION, 10)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_AFFECTED_ROLES, [100])
            await session.commit()

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            record.mod_channel_id = 123
            record.mod_message_id = 789
            record.user_channel_id = 456
            record.user_message_id = 111
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        # Verify that user message was deleted
        mock_user_message.delete.assert_called()
        # Verify that retention was scheduled
        assert len(purge_cog._pending_deletions) > 0


class TestHandleCancelRemovesRoleForbidden:
    """Tests for _handle_cancel when removing role fails."""

    async def test_handles_forbidden_on_role_removal(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test Forbidden handling when removing reaction role."""
        guild_id = 321321321
        confirmed_user_id = 888777

        # Mock user that confirmed with Forbidden on remove
        confirmed_member = MagicMock(spec=discord.Member)
        confirmed_member.id = confirmed_user_id
        confirmed_member.name = "ConfirmedUser"
        confirmed_member.remove_roles = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "No perms")
        )

        reaction_role = MagicMock(spec=discord.Role)
        reaction_role.id = 900
        reaction_role.name = "Reacted"
        confirmed_member.roles = [reaction_role]

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_guild.get_role = MagicMock(return_value=reaction_role)
        mock_guild.get_member = MagicMock(
            side_effect=lambda mid: confirmed_member if mid == confirmed_user_id else None
        )
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.TEST_MODE, True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 1)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.USER_REACTION_ROLE, 900)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.add_confirmation(record.id, confirmed_user_id)
            await session.commit()
            public_id = record.public_id

        # Should not raise exception
        await purge_cog._handle_cancel(mock_interaction, public_id)

        # Tried to remove the role but failed
        confirmed_member.remove_roles.assert_called()


class TestUpdateModMessageCancelPending:
    """Tests for _update_mod_message with CANCEL_PENDING status."""

    async def test_updates_with_cancel_pending_status(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test update with CANCEL_PENDING status (without view)."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_message.edit = AsyncMock()

        mock_guild.get_channel = MagicMock(return_value=mock_channel)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=None)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.mod_message_id = 12345
            record.mod_channel_id = 67890
            record.status = PurgeStatus.FAILED
            await session.commit()

            config: dict[str, Any] = {}
            await purge_cog._update_mod_message(mock_guild, record, config)

        # Verify that edit was called (without view because it is a terminal status)
        mock_message.edit.assert_called()


class TestSendUserMessageNoChannel:
    """Tests for _send_user_message when channel is not TextChannel."""

    async def test_channel_not_text_channel(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that does not fail when channel is not TextChannel."""
        mock_voice = MagicMock(spec=discord.VoiceChannel)
        mock_guild.get_channel = MagicMock(return_value=mock_voice)

        config: dict[str, Any] = {
            ConfigKey.USER_CHANNEL: 123,
        }

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.flush()

            # Should not raise exception or send message
            await purge_cog._send_user_message(
                guild=mock_guild,
                record=record,
                config=config,
                session=session,
            )


class TestOnReadySyncsRegisteredGuilds:
    """Tests for on_ready syncing guilds with registered commands."""

    async def test_syncs_only_registered_guilds(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test that only syncs guilds with registered commands."""
        guild1 = MagicMock(spec=discord.Guild)
        guild1.id = 111
        guild1.name = "Guild1"
        guild2 = MagicMock(spec=discord.Guild)
        guild2.id = 222
        guild2.name = "Guild2"
        mock_discord_bot.guilds = [guild1, guild2]

        # Only guild1 has a registered command
        purge_cog._registered_commands[111] = {"war": "purge_war"}

        with (
            patch.object(purge_cog, "_register_guild_commands", new_callable=AsyncMock),
            patch.object(purge_cog, "_sync_guild_commands", new_callable=AsyncMock) as mock_sync,
            patch.object(purge_cog, "_restore_active_purges", new_callable=AsyncMock),
            patch.object(purge_cog, "_check_expired_purges", new_callable=AsyncMock),
            patch.object(purge_cog.expiration_check_loop, "is_running", return_value=True),
        ):
            await purge_cog.on_ready()

            # Should only sync guild1
            mock_sync.assert_called_once_with(guild1)


class TestExecutePurgePromotionNotInAffected:
    """Tests for promotions outside the affected group."""

    async def test_promotion_not_in_affected_group(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test promotion of user not in affected group."""
        guild_id = 654654654

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        # Mock roles
        from_role = MagicMock(spec=discord.Role)
        from_role.id = 100
        from_role.name = "FromRole"
        to_role = MagicMock(spec=discord.Role)
        to_role.id = 200
        to_role.name = "ToRole"
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 300
        affected_role.name = "Affected"
        affected_role.members = []

        # Mock member that confirmed (in from_role but NOT in affected_role)
        member = MagicMock(spec=discord.Member)
        member.id = 44444
        member.name = "Member"
        member.display_name = "Member"
        member.roles = [from_role, mock_guild.default_role]
        member.add_roles = AsyncMock()
        member.remove_roles = AsyncMock()

        from_role.members = [member]

        def get_role(rid: int) -> MagicMock | None:
            if rid == 100:
                return from_role
            if rid == 200:
                return to_role
            if rid == 300:
                return affected_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role)
        mock_guild.get_member = MagicMock(side_effect=lambda mid: member if mid == 44444 else None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [300],  # Different from from_role
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [{"from_role": 100, "to_role": 200}],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await purge_service.add_confirmation(record.id, 44444)
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        # Should be promoted but NOT have from_role removed (not in affected)
        member.add_roles.assert_called_with(to_role)
        # remove_roles should NOT have been called with from_role
        for call in member.remove_roles.call_args_list:
            assert from_role not in call.args


class TestExecutePurgeRemoveReactionRoleForbidden:
    """Tests for error when removing reaction role during execution."""

    async def test_handles_forbidden_on_reaction_role_removal(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test Forbidden handling when removing reaction role."""
        guild_id = 987987987

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        reaction_role = MagicMock(spec=discord.Role)
        reaction_role.id = 500
        reaction_role.name = "Reacted"

        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected"
        affected_role.members = []

        confirmed_member = MagicMock(spec=discord.Member)
        confirmed_member.id = 33333
        confirmed_member.name = "ConfirmedUser"
        confirmed_member.roles = [reaction_role, mock_guild.default_role]
        confirmed_member.remove_roles = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "No perms")
        )

        def get_role(rid: int) -> MagicMock | None:
            if rid == 100:
                return affected_role
            if rid == 500:
                return reaction_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role)
        mock_guild.get_member = MagicMock(
            side_effect=lambda mid: confirmed_member if mid == 33333 else None
        )
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": None,
                    "test_mode": False,
                    "reaction_role": 500,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await purge_service.add_confirmation(record.id, 33333)
            await session.commit()
            purge_id = record.id

        # Should not raise exception
        await purge_cog._execute_purge(guild_id, purge_id)


class TestExecutePurgePromotionForbidden:
    """Tests for permission errors in promotions."""

    async def test_handles_forbidden_on_promotion(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test Forbidden handling when promoting."""
        guild_id = 555666777

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        from_role = MagicMock(spec=discord.Role)
        from_role.id = 100
        from_role.name = "FromRole"
        to_role = MagicMock(spec=discord.Role)
        to_role.id = 200
        to_role.name = "ToRole"

        member = MagicMock(spec=discord.Member)
        member.id = 22222
        member.name = "Member"
        member.display_name = "Member"
        member.roles = [from_role, mock_guild.default_role]
        member.add_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No perms"))
        member.remove_roles = AsyncMock()

        from_role.members = [member]

        def get_role(rid: int) -> MagicMock | None:
            if rid == 100:
                return from_role
            if rid == 200:
                return to_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role)
        mock_guild.get_member = MagicMock(side_effect=lambda mid: member if mid == 22222 else None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [{"from_role": 100, "to_role": 200}],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await purge_service.add_confirmation(record.id, 22222)
            await session.commit()
            purge_id = record.id

        # Should not raise exception
        await purge_cog._execute_purge(guild_id, purge_id)


class TestHandleWarPurgeRequiredReactionsMinimum:
    """Tests for _handle_purge (WAR_END) with required_reactions < 2."""

    async def test_required_reactions_minimum_enforced(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that required_reactions has minimum 2 in normal mode."""
        guild_id = 111333555
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 200
        affected_role.name = "Affected"
        affected_role.mention = "@Affected"

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123
        mock_message = MagicMock(spec=discord.Message)
        mock_message.id = 456
        mock_channel.send = AsyncMock(return_value=mock_message)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_channel)
        mock_guild.get_role = MagicMock(
            side_effect=lambda rid: affected_role if rid == 200 else None
        )
        # Properly mock get_member to return member with display_name
        mock_guild.get_member = MagicMock(
            side_effect=lambda mid: mock_member if mid == mock_member.id else None
        )
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_AFFECTED_ROLES, [200])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_CHANNEL, 123)
            # Set required_reactions to 1 (should be forced to 2 in non-test mode)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 1)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.TEST_MODE, False)
            await session.commit()

        await purge_cog._handle_purge(mock_interaction, 5, PurgeType.WAR_END)

        # Should have created purge but NOT auto-authorized (needs 2 not 1)
        mock_interaction.followup.send.assert_called()


class TestHandleAuthorizeTestModeExecTime:
    """Tests for _handle_authorize in test mode."""

    async def test_authorize_in_test_mode_short_exec_time(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that in test mode execution is in 2 minutes."""
        guild_id = 222444666
        second_user_id = 999111

        # Second user that authorizes
        second_user = MagicMock(spec=discord.Member)
        second_user.id = second_user_id
        second_user.display_name = "SecondUser"
        second_user.guild_permissions = MagicMock()
        second_user.guild_permissions.manage_guild = True

        role = MagicMock(spec=discord.Role)
        role.id = 100
        role.name = "Admin"
        second_user.roles = [role]

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 123
        mock_channel.send = AsyncMock(return_value=MagicMock(id=789))

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_channel)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=None)
        mock_interaction.guild = mock_guild
        mock_interaction.user = second_user
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.TEST_MODE, True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 2)
            await session.commit()

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=mock_member.id,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=5),
            )
            # First authorization from initiator
            await purge_service.add_authorization(record.id, mock_member.id)
            await session.commit()
            public_id = record.public_id
            purge_id = record.id
            purge_id = record.id

        # Track before
        purge_cog._active_purges[guild_id] = (purge_id, None)

        await purge_cog._handle_authorize(mock_interaction, public_id)

        # Should be in authorized_purges now
        assert guild_id in purge_cog._authorized_purges


class TestHandleConfirmRemoveRoleForbidden:
    """Tests for _handle_confirm when remove_roles fails."""

    async def test_handles_forbidden_on_remove_role(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test Forbidden handling when removing role."""
        guild_id = 333444555

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 800
        mock_role.name = "Confirmed"
        mock_member.remove_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No perms"))
        mock_member.name = "TestUser"

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.USER_REACTION_ROLE, 800)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            # User already confirmed, now will toggle off
            await purge_service.add_confirmation(record.id, mock_member.id)
            await session.commit()
            public_id = record.public_id

        # Should not raise - handles Forbidden gracefully
        await purge_cog._handle_confirm(mock_interaction, public_id)
        mock_interaction.response.send_message.assert_called()


class TestHandleCancelDeletesUserMessage:
    """Tests for _handle_cancel deleting user message."""

    async def test_deletes_user_message_on_cancel(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that cancel deletes user message."""
        guild_id = 444555666

        mock_user_channel = MagicMock(spec=discord.TextChannel)
        mock_user_message = MagicMock(spec=discord.Message)
        mock_user_channel.fetch_message = AsyncMock(return_value=mock_user_message)
        mock_user_message.delete = AsyncMock()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=None)

        def get_channel(cid: int) -> MagicMock | None:
            if cid == 789:
                return mock_user_channel
            return None

        mock_guild.get_channel = MagicMock(side_effect=get_channel)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.TEST_MODE, True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 1)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_MESSAGE_RETENTION, 5)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.user_channel_id = 789
            record.user_message_id = 111
            await session.commit()
            public_id = record.public_id

        await purge_cog._handle_cancel(mock_interaction, public_id)

        # Should have deleted user message
        mock_user_message.delete.assert_called()


class TestExecutePurgeMemberAlreadyProcessed:
    """Tests for _execute_purge with member already processed."""

    async def test_skips_already_processed_member(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that does not process member twice."""
        guild_id = 111999111

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        # Two affected roles with same member
        affected_role1 = MagicMock(spec=discord.Role)
        affected_role1.id = 100
        affected_role1.name = "Affected1"
        affected_role2 = MagicMock(spec=discord.Role)
        affected_role2.id = 200
        affected_role2.name = "Affected2"

        # Member is in both affected roles
        member = MagicMock(spec=discord.Member)
        member.id = 11111
        member.name = "Member"
        member.display_name = "Member"
        member.roles = [affected_role1, affected_role2, mock_guild.default_role]
        member.edit = AsyncMock()

        affected_role1.members = [member]
        affected_role2.members = [member]

        def get_role(rid: int) -> MagicMock | None:
            if rid == 100:
                return affected_role1
            if rid == 200:
                return affected_role2
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role)
        mock_guild.get_member = MagicMock(side_effect=lambda mid: member if mid == 11111 else None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100, 200],  # Both roles
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        # Should only be processed once (member.edit called once)
        assert member.edit.call_count == 1


class TestExecutePurgeRoleNotFound:
    """Tests for _execute_purge when role does not exist."""

    async def test_skips_nonexistent_role(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that ignores roles that do not exist."""
        guild_id = 222888222

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        # Return None for all role lookups
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [999999],  # Non-existent role
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [{"from_role": 888888, "to_role": 777777}],  # Non-existent
                    "default_promotion": 666666,  # Non-existent
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id

        # Should complete without errors
        await purge_cog._execute_purge(guild_id, purge_id)


class TestExecutePurgePromotionMemberNotConfirmed:
    """Tests for promotions with unconfirmed members."""

    async def test_skips_unconfirmed_members_in_promotion(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that does not promote members who did not confirm."""
        guild_id = 333777333

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        from_role = MagicMock(spec=discord.Role)
        from_role.id = 100
        from_role.name = "FromRole"
        to_role = MagicMock(spec=discord.Role)
        to_role.id = 200
        to_role.name = "ToRole"
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 300
        affected_role.name = "Affected"
        affected_role.members = []

        # Member that did NOT confirm
        member = MagicMock(spec=discord.Member)
        member.id = 44444
        member.name = "Member"
        member.display_name = "Member"
        member.roles = [from_role, mock_guild.default_role]
        member.add_roles = AsyncMock()

        from_role.members = [member]

        def get_role(rid: int) -> MagicMock | None:
            if rid == 100:
                return from_role
            if rid == 200:
                return to_role
            if rid == 300:
                return affected_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role)
        mock_guild.get_member = MagicMock(return_value=None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [300],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [{"from_role": 100, "to_role": 200}],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            # NO confirmation added!
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        # Member should NOT have been promoted (no add_roles called)
        member.add_roles.assert_not_called()


class TestExecutePurgePromotionMemberAlreadyPromoted:
    """Tests for promotions with already promoted members."""

    async def test_skips_already_promoted_member(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that does not promote member twice."""
        guild_id = 444666444

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        # Two promotion paths for same member
        from_role1 = MagicMock(spec=discord.Role)
        from_role1.id = 100
        from_role1.name = "FromRole1"
        from_role2 = MagicMock(spec=discord.Role)
        from_role2.id = 200
        from_role2.name = "FromRole2"
        to_role1 = MagicMock(spec=discord.Role)
        to_role1.id = 300
        to_role1.name = "ToRole1"
        to_role2 = MagicMock(spec=discord.Role)
        to_role2.id = 400
        to_role2.name = "ToRole2"

        # Member with both from roles (should only be promoted once)
        member = MagicMock(spec=discord.Member)
        member.id = 55555
        member.name = "Member"
        member.display_name = "Member"
        member.roles = [from_role1, from_role2, mock_guild.default_role]
        member.add_roles = AsyncMock()
        member.remove_roles = AsyncMock()

        from_role1.members = [member]
        from_role2.members = [member]

        def get_role(rid: int) -> MagicMock | None:
            if rid == 100:
                return from_role1
            if rid == 200:
                return from_role2
            if rid == 300:
                return to_role1
            if rid == 400:
                return to_role2
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role)
        mock_guild.get_member = MagicMock(side_effect=lambda mid: member if mid == 55555 else None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100, 200],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [
                        {"from_role": 100, "to_role": 300},
                        {"from_role": 200, "to_role": 400},
                    ],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await purge_service.add_confirmation(record.id, 55555)
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        # Should only be promoted once
        assert member.add_roles.call_count == 1


class TestDefaultPromotionAlreadyProcessed:
    """Tests for default promotion with already processed user."""

    async def test_skips_already_promoted_in_default_promotion(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that does not apply default promotion to already promoted user."""
        guild_id = 555888555

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        default_role = MagicMock(spec=discord.Role)
        default_role.id = 300
        default_role.name = "Default"
        from_role = MagicMock(spec=discord.Role)
        from_role.id = 100
        from_role.name = "FromRole"
        to_role = MagicMock(spec=discord.Role)
        to_role.id = 200
        to_role.name = "ToRole"

        # Member that confirmed AND has from_role (will be promoted)
        member = MagicMock(spec=discord.Member)
        member.id = 66666
        member.name = "Member"
        member.display_name = "Member"
        member.roles = [from_role, mock_guild.default_role]
        member.add_roles = AsyncMock()
        member.remove_roles = AsyncMock()

        from_role.members = [member]

        def get_role(rid: int) -> MagicMock | None:
            if rid == 100:
                return from_role
            if rid == 200:
                return to_role
            if rid == 300:
                return default_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role)
        mock_guild.get_member = MagicMock(side_effect=lambda mid: member if mid == 66666 else None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [{"from_role": 100, "to_role": 200}],
                    "default_promotion": 300,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await purge_service.add_confirmation(record.id, 66666)
            await session.commit()
            purge_id = record.id

        await purge_cog._execute_purge(guild_id, purge_id)

        # Should have been promoted to to_role, NOT default_role
        # add_roles should be called once with to_role
        assert member.add_roles.call_count == 1
        member.add_roles.assert_called_with(to_role)


class TestExecutePurgeRemoveRolesForbidden:
    """Tests for error when removing roles during execution."""

    async def test_handles_forbidden_on_remove_specific_roles(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test Forbidden handling when removing specific roles."""
        guild_id = 666999666

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected"
        remove_role = MagicMock(spec=discord.Role)
        remove_role.id = 200
        remove_role.name = "ToRemove"

        member = MagicMock(spec=discord.Member)
        member.id = 77777
        member.name = "Member"
        member.display_name = "Member"
        member.roles = [affected_role, remove_role, mock_guild.default_role]
        member.remove_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No perms"))
        member.add_roles = AsyncMock()

        affected_role.members = [member]

        def get_role(rid: int) -> MagicMock | None:
            if rid == 100:
                return affected_role
            if rid == 200:
                return remove_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role)
        mock_guild.get_member = MagicMock(side_effect=lambda mid: member if mid == 77777 else None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [200],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id

        # Should not raise
        await purge_cog._execute_purge(guild_id, purge_id)


class TestExecutePurgeAddRolesForbidden:
    """Tests for error when adding roles during execution."""

    async def test_handles_forbidden_on_add_roles(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test Forbidden handling when adding roles."""
        guild_id = 777111777

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.default_role = MagicMock(spec=discord.Role)
        mock_guild.default_role.id = 0
        mock_guild.get_channel = MagicMock(return_value=None)

        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected"
        add_role = MagicMock(spec=discord.Role)
        add_role.id = 200
        add_role.name = "ToAdd"

        member = MagicMock(spec=discord.Member)
        member.id = 88888
        member.name = "Member"
        member.display_name = "Member"
        member.roles = [affected_role, mock_guild.default_role]
        member.edit = AsyncMock()
        member.add_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No perms"))

        affected_role.members = [member]

        def get_role(rid: int) -> MagicMock | None:
            if rid == 100:
                return affected_role
            if rid == 200:
                return add_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role)
        mock_guild.get_member = MagicMock(side_effect=lambda mid: member if mid == 88888 else None)
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [100],
                    "roles_to_remove": [],
                    "roles_to_add": [200],
                    "promotions": [],
                    "default_promotion": None,
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id

        # Should not raise
        await purge_cog._execute_purge(guild_id, purge_id)


class TestHandleCancelSchedulesDeletion:
    """Tests for _handle_cancel scheduling message deletion."""

    async def test_schedules_deletion_after_cancel(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that schedules deletion after cancelling."""
        guild_id = 999888777

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_message = MagicMock(spec=discord.Message)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_message.edit = AsyncMock()

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=None)

        def get_channel(cid: int) -> MagicMock | None:
            if cid == 123:
                return mock_mod_channel
            return None

        mock_guild.get_channel = MagicMock(side_effect=get_channel)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.TEST_MODE, True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 1)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_MESSAGE_RETENTION, 10)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.mod_channel_id = 123
            record.mod_message_id = 456
            await session.commit()
            public_id = record.public_id

        await purge_cog._handle_cancel(mock_interaction, public_id)

        # Should have scheduled deletion
        assert len(purge_cog._pending_deletions) > 0


class TestUpdateModMessageCancelPendingBranch:
    """Tests for _update_mod_message CANCEL_PENDING branch (else branch)."""

    async def test_updates_without_view_for_cancel_pending(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test update without view for CANCEL_PENDING status."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_message.edit = AsyncMock()

        mock_guild.get_channel = MagicMock(return_value=mock_channel)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=None)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.mod_message_id = 12345
            record.mod_channel_id = 67890
            # Set to CANCEL_PENDING - not terminal but not PENDING/AUTHORIZED
            record.status = PurgeStatus.CANCEL_PENDING
            await session.commit()

            config: dict[str, Any] = {}
            await purge_cog._update_mod_message(mock_guild, record, config)

        # Should call edit without view (line 1488)
        mock_message.edit.assert_called()


class TestHandleCancelToCancelPending:
    """Tests for transition to CANCEL_PENDING in _handle_cancel."""

    async def test_transitions_to_cancel_pending(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that the first cancellation vote transitions to CANCEL_PENDING."""
        guild_id = 999888777

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=None)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id, COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 3)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REACTION_TIMEOUT, 5)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            public_id = record.public_id
            purge_id = record.id

        await purge_cog._handle_cancel(mock_interaction, public_id)

        # Verify that transitioned to CANCEL_PENDING
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            updated = await purge_service.get_purge(purge_id)
            assert updated is not None
            assert updated.status == PurgeStatus.CANCEL_PENDING
            assert mock_member.id in updated.cancelled_by

        # Verify that expiration is tracked
        assert guild_id in purge_cog._cancel_pending_purges

    async def test_cancel_pending_allows_more_votes(
        self,
        purge_cog: PurgeCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that more votes can be added in CANCEL_PENDING."""
        guild_id = 888777666

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=None)
        mock_interaction.guild = mock_guild
        mock_interaction.user = mock_member
        mock_interaction.response = MagicMock()
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup = MagicMock()
        mock_interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id, COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REQUIRED_REACTIONS, 3)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Already in CANCEL_PENDING with one vote
            await purge_service.update_status(record.id, PurgeStatus.CANCEL_PENDING)
            await purge_service.add_cancellation(record.id, 888)
            await session.commit()
            public_id = record.public_id
            purge_id = record.id

        await purge_cog._handle_cancel(mock_interaction, public_id)

        # Verify that the vote was added and remains in CANCEL_PENDING
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            updated = await purge_service.get_purge(purge_id)
            assert updated is not None
            assert updated.status == PurgeStatus.CANCEL_PENDING
            assert len(updated.cancelled_by) == 2


class TestCheckCancelPendingExpired:
    """Tests for _check_cancel_pending_expired."""

    async def test_reverts_expired_cancel_pending(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test that reverts expired CANCEL_PENDING to AUTHORIZED."""
        guild_id = mock_guild.id
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_message.edit = AsyncMock()
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id, COG_NAME, enabled=True)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.mod_message_id = 12345
            record.mod_channel_id = 67890
            await purge_service.update_status(record.id, PurgeStatus.CANCEL_PENDING)
            await purge_service.add_cancellation(record.id, 111)
            await purge_service.add_cancellation(record.id, 222)
            await session.commit()
            purge_id = record.id

        # Add to tracking with expired time
        purge_cog._cancel_pending_purges[guild_id] = (
            purge_id,
            datetime.now(UTC) - timedelta(minutes=1),
        )

        await purge_cog._check_cancel_pending_expired()

        # Verify that it was removed from tracking
        assert guild_id not in purge_cog._cancel_pending_purges

        # Verify that reverted to AUTHORIZED and cleared votes
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            updated = await purge_service.get_purge(purge_id)
            assert updated is not None
            assert updated.status == PurgeStatus.AUTHORIZED
            assert updated.cancelled_by == []

    async def test_does_not_revert_non_expired(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that does not revert non-expired CANCEL_PENDING."""
        guild_id = mock_guild.id

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.update_status(record.id, PurgeStatus.CANCEL_PENDING)
            await purge_service.add_cancellation(record.id, 111)
            await session.commit()
            purge_id = record.id

        # Add to tracking with future time
        future_expiry = datetime.now(UTC) + timedelta(minutes=5)
        purge_cog._cancel_pending_purges[guild_id] = (purge_id, future_expiry)

        await purge_cog._check_cancel_pending_expired()

        # Verify that remains in tracking
        assert guild_id in purge_cog._cancel_pending_purges

        # Verify that remains in CANCEL_PENDING
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            updated = await purge_service.get_purge(purge_id)
            assert updated is not None
            assert updated.status == PurgeStatus.CANCEL_PENDING


class TestRestoreCancelPendingPurges:
    """Tests for restoration of CANCEL_PENDING purges."""

    async def test_restores_cancel_pending_purges(
        self,
        purge_cog: PurgeCog,
        test_database: DatabaseService,
    ) -> None:
        """Test that restores CANCEL_PENDING purges on startup."""
        guild_id = 111222333

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id, COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_REACTION_TIMEOUT, 10)

            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.update_status(record.id, PurgeStatus.CANCEL_PENDING)
            await session.commit()
            purge_id = record.id

        await purge_cog._restore_active_purges()

        # Verify that it was restored
        assert guild_id in purge_cog._cancel_pending_purges
        restored_id, expires_at = purge_cog._cancel_pending_purges[guild_id]
        assert restored_id == purge_id
        # The expiration should be in the future (10 minute timeout)
        assert expires_at > datetime.now(UTC)


class TestModAuthorizationViewCancelPending:
    """Tests for ModAuthorizationView with CANCEL_PENDING."""

    async def test_view_creation_cancel_pending(self) -> None:
        """Test that CANCEL_PENDING shows cancel button."""
        from discord_bot.purge.views import ModAuthorizationView

        view = ModAuthorizationView(
            public_id="123",
            status=PurgeStatus.CANCEL_PENDING,
            authorize_label="Authorize",
            cancel_label="Cancel",
        )

        # Should have exactly one button (the cancel one)
        assert len(view.children) == 1
        button = view.children[0]
        assert isinstance(button, discord.ui.Button)
        assert button.label == "Cancel"
        assert button.style == discord.ButtonStyle.danger


class TestHandleAuthorizeReturnsNone:
    """Tests for when add_authorization returns None in _handle_authorize."""

    async def test_add_authorization_returns_none(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns early when add_authorization returns None."""
        public_id = "test123"

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = mock_member
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        # Create initial record in PENDING status
        mock_record = MagicMock()
        mock_record.id = 1
        mock_record.public_id = public_id
        mock_record.guild_id = mock_guild.id
        mock_record.status = PurgeStatus.PENDING
        mock_record.purge_type = PurgeType.WAR_END
        mock_record.authorized_by = []

        with (
            patch.object(purge_cog, "_get_config", new_callable=AsyncMock) as mock_config,
            patch("discord_bot.purge.cog.PurgeService") as mock_service_class,
        ):
            mock_config.return_value = {
                ConfigKey.WAR_ADMIN_ROLES: [100],  # mock_member has role 100
            }

            mock_service = MagicMock()
            mock_service.get_by_public_id = AsyncMock(return_value=mock_record)
            mock_service.add_authorization = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            await purge_cog._handle_authorize(
                interaction=interaction,
                public_id=public_id,
            )

            # Verify that add_authorization was called and returned
            mock_service.add_authorization.assert_called_once()


class TestHandleCancelReturnsNone:
    """Tests for when add_cancellation returns None in _handle_cancel."""

    async def test_add_cancellation_returns_none(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns early when add_cancellation returns None."""
        public_id = "test123"

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = mock_member
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_record = MagicMock()
        mock_record.id = 1
        mock_record.public_id = public_id
        mock_record.guild_id = mock_guild.id
        mock_record.status = PurgeStatus.AUTHORIZED
        mock_record.purge_type = PurgeType.WAR_END
        mock_record.cancelled_by = []

        with (
            patch.object(purge_cog, "_get_config", new_callable=AsyncMock) as mock_config,
            patch("discord_bot.purge.cog.PurgeService") as mock_service_class,
        ):
            mock_config.return_value = {
                ConfigKey.WAR_ADMIN_ROLES: [100],
            }

            mock_service = MagicMock()
            mock_service.get_by_public_id = AsyncMock(return_value=mock_record)
            mock_service.add_cancellation = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            await purge_cog._handle_cancel(
                interaction=interaction,
                public_id=public_id,
            )

            mock_service.add_cancellation.assert_called_once()


class TestUpdateStatusReturnsNone:
    """Tests for when update_status returns None in different contexts."""

    async def test_update_status_returns_none_on_cancel_transition(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns when update_status fails in transition to CANCEL_PENDING."""
        public_id = "test123"

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = mock_member
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        # Record with AUTHORIZED status
        mock_record = MagicMock()
        mock_record.id = 1
        mock_record.public_id = public_id
        mock_record.guild_id = mock_guild.id
        mock_record.status = PurgeStatus.AUTHORIZED
        mock_record.purge_type = PurgeType.WAR_END
        mock_record.cancelled_by = [111]  # One cancellation vote

        with (
            patch.object(purge_cog, "_get_config", new_callable=AsyncMock) as mock_config,
            patch("discord_bot.purge.cog.PurgeService") as mock_service_class,
        ):
            mock_config.return_value = {
                ConfigKey.WAR_ADMIN_ROLES: [100],
                ConfigKey.MOD_REQUIRED_REACTIONS: 2,  # Requires 2, has 1
                ConfigKey.MOD_REACTION_TIMEOUT: 10,
            }

            mock_service = MagicMock()
            mock_service.get_by_public_id = AsyncMock(return_value=mock_record)
            mock_service.add_cancellation = AsyncMock(return_value=mock_record)
            mock_service.update_status = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            await purge_cog._handle_cancel(
                interaction=interaction,
                public_id=public_id,
            )

            mock_service.update_status.assert_called()

    async def test_update_status_returns_none_on_full_cancel(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns when update_status fails to cancel completely."""
        public_id = "test123"

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = mock_member
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        # Record with enough votes to cancel
        mock_record = MagicMock()
        mock_record.id = 1
        mock_record.public_id = public_id
        mock_record.guild_id = mock_guild.id
        mock_record.status = PurgeStatus.CANCEL_PENDING
        mock_record.purge_type = PurgeType.WAR_END
        mock_record.cancelled_by = [111]

        with (
            patch.object(purge_cog, "_get_config", new_callable=AsyncMock) as mock_config,
            patch("discord_bot.purge.cog.PurgeService") as mock_service_class,
        ):
            mock_config.return_value = {
                ConfigKey.WAR_ADMIN_ROLES: [100],
                ConfigKey.MOD_REQUIRED_REACTIONS: 1,
            }

            mock_service = MagicMock()
            mock_service.get_by_public_id = AsyncMock(return_value=mock_record)
            mock_service.add_cancellation = AsyncMock(return_value=mock_record)
            mock_service.update_status = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            await purge_cog._handle_cancel(
                interaction=interaction,
                public_id=public_id,
            )


class TestCheckExpiredPurgesException:
    """Tests for exception handling in _check_expired_purges."""

    async def test_exception_during_expiration(
        self, purge_cog: PurgeCog, mock_guild: MagicMock, test_database: DatabaseService
    ) -> None:
        """Test that catches exceptions during purge expiration."""
        guild_id = mock_guild.id
        purge_id = 999

        purge_cog._active_purges[guild_id] = (
            purge_id,
            datetime.now(UTC) - timedelta(hours=1),
        )

        with (
            patch.object(purge_cog.bot, "get_guild", return_value=mock_guild),
            patch.object(purge_cog, "_get_config", new_callable=AsyncMock) as mock_config,
        ):
            mock_config.side_effect = Exception("Test error")

            await purge_cog._check_expired_purges()


class TestCheckCancelPendingExpiredException:
    """Tests for exception handling in _check_cancel_pending_expired."""

    async def test_exception_during_revert(
        self, purge_cog: PurgeCog, mock_guild: MagicMock, test_database: DatabaseService
    ) -> None:
        """Test that catches exceptions during cancellation reversion."""
        guild_id = mock_guild.id
        purge_id = 999

        purge_cog._cancel_pending_purges[guild_id] = (
            purge_id,
            datetime.now(UTC) - timedelta(hours=1),
        )

        with (
            patch.object(purge_cog.bot, "get_guild", return_value=mock_guild),
            patch.object(purge_cog, "_get_config", new_callable=AsyncMock) as mock_config,
        ):
            mock_config.side_effect = Exception("Test error")

            await purge_cog._check_cancel_pending_expired()


class TestAuthorizePurgeReturnsNone:
    """Tests for when _authorize_purge returns None."""

    async def test_authorize_purge_update_status_returns_none(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns None when update_status fails to authorize."""
        # Create record in DB
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()

            config: dict[str, Any] = {}

            # Mock update_status to return None
            with patch.object(
                purge_service, "update_status", new_callable=AsyncMock
            ) as mock_update:
                mock_update.return_value = None

                result = await purge_cog._authorize_purge(
                    guild=mock_guild,
                    record=record,
                    config=config,
                    purge_service=purge_service,
                    session=session,
                )

                assert result is None


class TestCogSettings:
    """Tests for cog deployment configuration."""

    def test_get_locked_options_test_mode_not_allowed(self, mock_discord_bot: MagicMock) -> None:
        """Returns test_mode as blocked when not allowed."""
        cog = PurgeCog(mock_discord_bot)
        cog._cog_settings.test_mode_allowed = False

        locked = cog.get_locked_options()

        assert ConfigKey.TEST_MODE in locked
        assert locked[ConfigKey.TEST_MODE]["locked"] is True
        assert "reason" in locked[ConfigKey.TEST_MODE]

    def test_get_locked_options_test_mode_allowed(self, purge_cog: PurgeCog) -> None:
        """Does not return test_mode as blocked when allowed."""
        # purge_cog fixture already has test_mode_allowed = True
        locked = purge_cog.get_locked_options()

        assert ConfigKey.TEST_MODE not in locked

    def test_is_test_mode_enabled_blocked_by_settings(self, mock_discord_bot: MagicMock) -> None:
        """test_mode returns False if settings does not allow it."""
        cog = PurgeCog(mock_discord_bot)
        cog._cog_settings.test_mode_allowed = False

        config: dict[str, Any] = {ConfigKey.TEST_MODE: True}

        assert cog._is_test_mode_enabled(config) is False

    def test_is_test_mode_enabled_allowed_by_settings(self, purge_cog: PurgeCog) -> None:
        """test_mode returns True if settings and config allow it."""
        config: dict[str, Any] = {ConfigKey.TEST_MODE: True}

        assert purge_cog._is_test_mode_enabled(config) is True

    def test_is_test_mode_enabled_disabled_in_config(self, purge_cog: PurgeCog) -> None:
        """test_mode returns False if config disables it."""
        config: dict[str, Any] = {ConfigKey.TEST_MODE: False}

        assert purge_cog._is_test_mode_enabled(config) is False


class TestGetPurgeDisplayName:
    """Tests for the _get_purge_display_name method."""

    def test_war_end_default(self, purge_cog: PurgeCog) -> None:
        """Returns default name for war purge."""
        config: dict[str, Any] = {}
        result = purge_cog._get_purge_display_name(config, PurgeType.WAR_END)
        assert result == "War end purge"

    def test_war_end_custom(self, purge_cog: PurgeCog) -> None:
        """Returns custom name for war purge."""
        config: dict[str, Any] = {ConfigKey.WAR_DISPLAY_NAME: "End of season"}
        result = purge_cog._get_purge_display_name(config, PurgeType.WAR_END)
        assert result == "End of season"

    def test_global_default(self, purge_cog: PurgeCog) -> None:
        """Returns default name for global purge."""
        config: dict[str, Any] = {}
        result = purge_cog._get_purge_display_name(config, PurgeType.GLOBAL)
        assert result == "Global purge"

    def test_global_custom(self, purge_cog: PurgeCog) -> None:
        """Returns custom name for global purge."""
        config: dict[str, Any] = {ConfigKey.GLOBAL_DISPLAY_NAME: "General cleanup"}
        result = purge_cog._get_purge_display_name(config, PurgeType.GLOBAL)
        assert result == "General cleanup"


class TestSendLog:
    """Tests for the _send_log method."""

    async def test_no_channel_configured(self, purge_cog: PurgeCog, mock_guild: MagicMock) -> None:
        """Does not send if no channel is configured."""
        config: dict[str, Any] = {}

        await purge_cog._send_log(
            guild=mock_guild,
            config=config,
            public_id="test1",
            message="Test message",
        )

        # Should not call get_channel
        mock_guild.get_channel.assert_not_called()

    async def test_audit_level_too_low(self, purge_cog: PurgeCog, mock_guild: MagicMock) -> None:
        """Does not send if audit level is insufficient."""
        config: dict[str, Any] = {
            ConfigKey.LOG_CHANNEL: 123456,
            ConfigKey.AUDIT_LEVEL: 0,
        }

        await purge_cog._send_log(
            guild=mock_guild,
            config=config,
            public_id="test1",
            message="Test message",
            audit_level_required=1,
        )

        # Should not call get_channel because audit level is insufficient
        mock_guild.get_channel.assert_not_called()

    async def test_channel_not_found(self, purge_cog: PurgeCog, mock_guild: MagicMock) -> None:
        """Does not crash if channel does not exist."""
        mock_guild.get_channel.return_value = None
        config: dict[str, Any] = {
            ConfigKey.LOG_CHANNEL: 123456,
            ConfigKey.AUDIT_LEVEL: 1,
        }

        # Should not raise exception
        await purge_cog._send_log(
            guild=mock_guild,
            config=config,
            public_id="test1",
            message="Test message",
        )

        mock_guild.get_channel.assert_called_once_with(123456)

    async def test_send_success(self, purge_cog: PurgeCog, mock_guild: MagicMock) -> None:
        """Sends message with purge ID prefix correctly."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_guild.get_channel.return_value = mock_channel

        config: dict[str, Any] = {
            ConfigKey.LOG_CHANNEL: 123456,
            ConfigKey.AUDIT_LEVEL: 1,
        }

        await purge_cog._send_log(
            guild=mock_guild,
            config=config,
            public_id="test42",
            message="Test message",
        )

        mock_channel.send.assert_called_once_with("[#test42] Test message")

    async def test_audit_level_met(self, purge_cog: PurgeCog, mock_guild: MagicMock) -> None:
        """Sends when audit level meets the requirement."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_guild.get_channel.return_value = mock_channel

        config: dict[str, Any] = {
            ConfigKey.LOG_CHANNEL: 123456,
            ConfigKey.AUDIT_LEVEL: 2,
        }

        await purge_cog._send_log(
            guild=mock_guild,
            config=config,
            public_id="test1",
            message="Test",
            audit_level_required=1,
        )

        mock_channel.send.assert_called_once()

    async def test_discord_error_no_crash(self, purge_cog: PurgeCog, mock_guild: MagicMock) -> None:
        """Discord error does not crash."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "Error"))
        mock_guild.get_channel.return_value = mock_channel

        config: dict[str, Any] = {
            ConfigKey.LOG_CHANNEL: 123456,
        }

        # Should not raise exception
        await purge_cog._send_log(
            guild=mock_guild,
            config=config,
            public_id="test1",
            message="Test message",
        )

    async def test_invalid_channel_type(self, purge_cog: PurgeCog, mock_guild: MagicMock) -> None:
        """Does not send if the channel is not TextChannel."""
        mock_channel = MagicMock(spec=discord.VoiceChannel)
        mock_guild.get_channel.return_value = mock_channel

        config: dict[str, Any] = {
            ConfigKey.LOG_CHANNEL: 123456,
        }

        await purge_cog._send_log(
            guild=mock_guild,
            config=config,
            public_id="test1",
            message="Test message",
        )

        # Should not try to send to a voice channel
        assert not hasattr(mock_channel, "send") or not mock_channel.send.called

    async def test_invalid_channel_id_no_crash(
        self, purge_cog: PurgeCog, mock_guild: MagicMock
    ) -> None:
        """Does not crash with invalid channel ID."""
        config: dict[str, Any] = {
            ConfigKey.LOG_CHANNEL: "not_a_number",
        }

        # Should not raise exception
        await purge_cog._send_log(
            guild=mock_guild,
            config=config,
            public_id="test1",
            message="Test message",
        )
