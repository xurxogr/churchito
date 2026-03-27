"""Tests for AutonameCog."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_bot.autoname.cog import AutonameCog
from discord_bot.autoname.config import AUTONAME_CONFIG_SCHEMA, ConfigKey
from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.database import DatabaseService


@pytest.fixture
def mock_discord_bot(test_database: DatabaseService) -> MagicMock:
    """Create mock of bot with database."""
    bot = MagicMock(spec=DiscordBot)
    bot.database = test_database
    bot.guilds = []
    bot.wait_until_ready = AsyncMock()
    return bot


@pytest.fixture
def autoname_cog(mock_discord_bot: MagicMock) -> AutonameCog:
    """Create cog instance for tests."""
    return AutonameCog(mock_discord_bot)


@pytest.fixture
def mock_member() -> MagicMock:
    """Create mock of a Discord member."""
    member = MagicMock(spec=discord.Member)
    member.id = 123456789
    member.bot = False
    member.display_name = "Xurxo"
    member.nick = None
    member.guild = MagicMock(spec=discord.Guild)
    member.guild.id = 987654321
    member.guild.name = "Test Guild"
    member.edit = AsyncMock()

    # Create mock roles
    role1 = MagicMock(spec=discord.Role)
    role1.id = 100
    role2 = MagicMock(spec=discord.Role)
    role2.id = 200
    member.roles = [role1, role2]

    return member


class TestIsCogEnabled:
    """Tests for _is_cog_enabled."""

    async def test_cog_enabled(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test when cog is enabled."""
        guild_id = 123

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await session.commit()

        result = await autoname_cog._is_cog_enabled(guild_id)
        assert result is True

    async def test_cog_disabled(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test when cog is disabled."""
        guild_id = 456

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=False
            )
            await session.commit()

        result = await autoname_cog._is_cog_enabled(guild_id)
        assert result is False


class TestGetConfig:
    """Tests for _get_config."""

    async def test_returns_config_dict(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test that returns a configuration dictionary."""
        guild_id = 123

        result = await autoname_cog._get_config(guild_id)

        assert isinstance(result, dict)

    async def test_returns_saved_config(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test that returns saved configuration."""
        guild_id = 789

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id, "autoname", ConfigKey.TAG_FORMAT, "[TEST | {tag}]"
            )
            await session.commit()

        result = await autoname_cog._get_config(guild_id)

        assert result.get(ConfigKey.TAG_FORMAT) == "[TEST | {tag}]"


class TestGetSyncInterval:
    """Tests for _get_sync_interval."""

    async def test_returns_default_when_not_configured(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test that returns 30 by default when cog is enabled."""
        guild_id = 111

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await session.commit()

        result = await autoname_cog._get_sync_interval(guild_id)

        assert result == 30

    async def test_returns_zero_when_cog_disabled(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test that returns 0 when cog is disabled."""
        guild_id = 222

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=False
            )
            await session.commit()

        result = await autoname_cog._get_sync_interval(guild_id)

        assert result == 0

    async def test_returns_configured_interval(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test that returns the configured interval."""
        guild_id = 333

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(guild_id, "autoname", ConfigKey.SYNC_INTERVAL, 60)
            await session.commit()

        result = await autoname_cog._get_sync_interval(guild_id)

        assert result == 60


class TestApplyNickname:
    """Tests for apply_nickname."""

    async def test_skips_bots(self, autoname_cog: AutonameCog, mock_member: MagicMock) -> None:
        """Test that bots are not processed."""
        mock_member.bot = True

        result = await autoname_cog.apply_nickname(mock_member)

        assert result is False
        mock_member.edit.assert_not_called()

    async def test_returns_false_when_no_roles_config(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns False when there is no role configuration."""
        guild_id = mock_member.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await session.commit()

        result = await autoname_cog.apply_nickname(mock_member)

        assert result is False
        mock_member.edit.assert_not_called()

    async def test_applies_nickname_when_config_matches(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that applies nickname when there is a role match."""
        guild_id = mock_member.guild.id
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(guild_id, "autoname", ConfigKey.ROLE_TAGS, tags_config)
            await config_service.set_value(
                guild_id, "autoname", ConfigKey.ROLE_PREFIXES, prefixes_config
            )
            await config_service.set_value(
                guild_id, "autoname", ConfigKey.TAG_FORMAT, "[ABC | {tag}]"
            )
            await session.commit()

        result = await autoname_cog.apply_nickname(mock_member)

        assert result is True
        mock_member.edit.assert_called_once_with(nick="★[ABC | CAP] Xurxo")

    async def test_returns_false_when_no_change_needed(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that returns False when no change is needed."""
        guild_id = mock_member.guild.id
        mock_member.nick = "★[ABC | CAP] Xurxo"
        mock_member.display_name = "★[ABC | CAP] Xurxo"
        tags_config = [{"role_id": 100, "tag": "CAP"}]
        prefixes_config = [{"role_id": 100, "prefix": "★"}]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(guild_id, "autoname", ConfigKey.ROLE_TAGS, tags_config)
            await config_service.set_value(
                guild_id, "autoname", ConfigKey.ROLE_PREFIXES, prefixes_config
            )
            await config_service.set_value(
                guild_id, "autoname", ConfigKey.TAG_FORMAT, "[ABC | {tag}]"
            )
            await session.commit()

        result = await autoname_cog.apply_nickname(mock_member)

        assert result is False
        mock_member.edit.assert_not_called()

    async def test_handles_forbidden_error(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handles permission errors."""
        guild_id = mock_member.guild.id
        mock_member.edit = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(guild_id, "autoname", ConfigKey.ROLE_TAGS, tags_config)
            await session.commit()

        result = await autoname_cog.apply_nickname(mock_member)

        assert result is False

    async def test_handles_http_error(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handles HTTP errors."""
        guild_id = mock_member.guild.id
        mock_member.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "Error"))
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(guild_id, "autoname", ConfigKey.ROLE_TAGS, tags_config)
            await session.commit()

        result = await autoname_cog.apply_nickname(mock_member)

        assert result is False


class TestApplyNicknameRequiredRole:
    """Tests for required_role in apply_nickname."""

    async def test_skips_member_without_required_roles(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that skips members without any of the required roles."""
        guild_id = mock_member.guild.id
        required_roles = [999, 998]  # Roles that the member does NOT have
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(
                guild_id, "autoname", ConfigKey.REQUIRED_ROLES, required_roles
            )
            await config_service.set_value(guild_id, "autoname", ConfigKey.ROLE_TAGS, tags_config)
            await session.commit()

        result = await autoname_cog.apply_nickname(mock_member)

        assert result is False
        mock_member.edit.assert_not_called()

    async def test_processes_member_with_any_required_role(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that processes members with any of the required roles."""
        guild_id = mock_member.guild.id
        required_roles = [999, 100]  # 100 is a role that the member DOES have
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(
                guild_id, "autoname", ConfigKey.REQUIRED_ROLES, required_roles
            )
            await config_service.set_value(guild_id, "autoname", ConfigKey.ROLE_TAGS, tags_config)
            await config_service.set_value(
                guild_id, "autoname", ConfigKey.TAG_FORMAT, "[ABC | {tag}]"
            )
            await session.commit()

        result = await autoname_cog.apply_nickname(mock_member)

        assert result is True
        mock_member.edit.assert_called_once()

    async def test_handles_invalid_required_roles_values(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handles invalid values in the required roles list."""
        guild_id = mock_member.guild.id
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            # List with invalid values and one valid (100)
            await config_service.set_value(
                guild_id, "autoname", ConfigKey.REQUIRED_ROLES, ["invalid", None, 100]
            )
            await config_service.set_value(guild_id, "autoname", ConfigKey.ROLE_TAGS, tags_config)
            await config_service.set_value(
                guild_id, "autoname", ConfigKey.TAG_FORMAT, "[ABC | {tag}]"
            )
            await session.commit()

        # Should continue processing because 100 is valid and the member has it
        result = await autoname_cog.apply_nickname(mock_member)

        assert result is True
        mock_member.edit.assert_called_once()


class TestOnMemberUpdate:
    """Tests for on_member_update."""

    async def test_ignores_same_roles(
        self, autoname_cog: AutonameCog, mock_member: MagicMock
    ) -> None:
        """Test that ignores when roles do not change."""
        before = mock_member
        after = mock_member
        before.roles = after.roles

        with patch.object(autoname_cog, "apply_nickname") as mock_apply:
            await autoname_cog.on_member_update(before, after)
            mock_apply.assert_not_called()

    async def test_ignores_when_cog_disabled(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that ignores when cog is disabled."""
        guild_id = mock_member.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=False
            )
            await session.commit()

        before = MagicMock(spec=discord.Member)
        before.roles = []
        after = mock_member

        with patch.object(autoname_cog, "apply_nickname") as mock_apply:
            await autoname_cog.on_member_update(before, after)
            mock_apply.assert_not_called()

    async def test_applies_nickname_on_role_change(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that applies nickname when roles change."""
        guild_id = mock_member.guild.id

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await session.commit()

        before = MagicMock(spec=discord.Member)
        before.roles = []
        after = mock_member

        with patch.object(autoname_cog, "apply_nickname", new_callable=AsyncMock) as mock_apply:
            await autoname_cog.on_member_update(before, after)
            mock_apply.assert_called_once_with(after)


class TestRunSync:
    """Tests for _run_sync."""

    async def test_skips_guild_with_zero_interval(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test that skips guilds with interval 0."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test"
        cast(MagicMock, autoname_cog.bot).guilds = [mock_guild]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(mock_guild.id, "autoname", ConfigKey.SYNC_INTERVAL, 0)
            await session.commit()

        with patch.object(autoname_cog, "_sync_guild") as mock_sync:
            await autoname_cog._run_sync()
            mock_sync.assert_not_called()

    async def test_syncs_guild_when_due(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test that syncs guild when due."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 456
        mock_guild.name = "Test"
        cast(MagicMock, autoname_cog.bot).guilds = [mock_guild]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(mock_guild.id, "autoname", ConfigKey.SYNC_INTERVAL, 30)
            await session.commit()

        with patch.object(autoname_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync:
            await autoname_cog._run_sync()
            mock_sync.assert_called_once_with(mock_guild)

    async def test_force_all_syncs_all_guilds(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test that force_all syncs all guilds."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 789
        mock_guild.name = "Test"
        cast(MagicMock, autoname_cog.bot).guilds = [mock_guild]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name="autoname", enabled=True
            )
            await session.commit()

        with patch.object(autoname_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync:
            await autoname_cog._run_sync(force_all=True)
            mock_sync.assert_called_once_with(mock_guild)


class TestSyncGuild:
    """Tests for _sync_guild."""

    async def test_skips_when_cog_disabled(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test that skips when cog is disabled."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name="autoname", enabled=False
            )
            await session.commit()

        with patch.object(autoname_cog, "apply_nickname") as mock_apply:
            await autoname_cog._sync_guild(mock_guild)
            mock_apply.assert_not_called()

    async def test_skips_when_no_roles_config(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test that skips when there is no role configuration."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 456

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name="autoname", enabled=True
            )
            await session.commit()

        with patch.object(autoname_cog, "apply_nickname") as mock_apply:
            await autoname_cog._sync_guild(mock_guild)
            mock_apply.assert_not_called()

    async def test_applies_nickname_to_members(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that applies nickname to all members."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = mock_member.guild.id
        mock_guild.name = "Test"
        mock_guild.members = [mock_member]
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(
                mock_guild.id, "autoname", ConfigKey.ROLE_TAGS, tags_config
            )
            await session.commit()

        with patch.object(
            autoname_cog, "apply_nickname", new_callable=AsyncMock, return_value=True
        ) as mock_apply:
            await autoname_cog._sync_guild(mock_guild)
            mock_apply.assert_called_once_with(mock_member)

    async def test_skips_bot_members(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that skips bot members."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = mock_member.guild.id
        mock_guild.name = "Test"

        bot_member = MagicMock(spec=discord.Member)
        bot_member.bot = True

        mock_guild.members = [bot_member, mock_member]
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(
                mock_guild.id, "autoname", ConfigKey.ROLE_TAGS, tags_config
            )
            await session.commit()

        with patch.object(
            autoname_cog, "apply_nickname", new_callable=AsyncMock, return_value=True
        ) as mock_apply:
            await autoname_cog._sync_guild(mock_guild)
            # Should only be called once (for mock_member, not for bot_member)
            mock_apply.assert_called_once_with(mock_member)


class TestOnConfigChanged:
    """Tests for on_config_changed."""

    async def test_resyncs_on_tags_change(self, autoname_cog: AutonameCog) -> None:
        """Test that re-syncs when tags change."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test"

        with patch.object(autoname_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync:
            await autoname_cog.on_config_changed(mock_guild, [ConfigKey.ROLE_TAGS])
            mock_sync.assert_called_once_with(mock_guild)

    async def test_resyncs_on_prefixes_change(self, autoname_cog: AutonameCog) -> None:
        """Test that re-syncs when prefixes change."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test"

        with patch.object(autoname_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync:
            await autoname_cog.on_config_changed(mock_guild, [ConfigKey.ROLE_PREFIXES])
            mock_sync.assert_called_once_with(mock_guild)

    async def test_resyncs_on_format_change(self, autoname_cog: AutonameCog) -> None:
        """Test that re-syncs when format changes."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test"

        with patch.object(autoname_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync:
            await autoname_cog.on_config_changed(mock_guild, [ConfigKey.TAG_FORMAT])
            mock_sync.assert_called_once_with(mock_guild)

    async def test_resyncs_on_required_roles_change(self, autoname_cog: AutonameCog) -> None:
        """Test that re-syncs when required roles change."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test"

        with patch.object(autoname_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync:
            await autoname_cog.on_config_changed(mock_guild, [ConfigKey.REQUIRED_ROLES])
            mock_sync.assert_called_once_with(mock_guild)

    async def test_ignores_interval_change(self, autoname_cog: AutonameCog) -> None:
        """Test that ignores interval changes."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test"

        with patch.object(autoname_cog, "_sync_guild") as mock_sync:
            await autoname_cog.on_config_changed(mock_guild, [ConfigKey.SYNC_INTERVAL])
            mock_sync.assert_not_called()


class TestOnCogToggled:
    """Tests for on_cog_toggled."""

    async def test_syncs_on_enabled(self, autoname_cog: AutonameCog) -> None:
        """Test that syncs when cog is enabled."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test"

        with patch.object(autoname_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync:
            await autoname_cog.on_cog_toggled(mock_guild, enabled=True)
            mock_sync.assert_called_once_with(mock_guild)

    async def test_no_sync_on_disabled(self, autoname_cog: AutonameCog) -> None:
        """Test that does not sync when cog is disabled."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test"

        with patch.object(autoname_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync:
            await autoname_cog.on_cog_toggled(mock_guild, enabled=False)
            mock_sync.assert_not_called()


class TestCogLifecycle:
    """Tests for cog_load and cog_unload."""

    async def test_cog_load_starts_sync_loop(self, autoname_cog: AutonameCog) -> None:
        """Test that cog_load starts the sync loop."""
        with patch.object(autoname_cog.sync_loop, "start") as mock_start:
            await autoname_cog.cog_load()
            mock_start.assert_called_once()

        assert autoname_cog._sync_started is True

    async def test_cog_load_only_starts_once(self, autoname_cog: AutonameCog) -> None:
        """Test that cog_load does not start twice."""
        autoname_cog._sync_started = True

        with patch.object(autoname_cog.sync_loop, "start") as mock_start:
            await autoname_cog.cog_load()
            mock_start.assert_not_called()

    async def test_cog_unload_cancels_sync_loop(self, autoname_cog: AutonameCog) -> None:
        """Test that cog_unload cancels the sync loop."""
        autoname_cog._sync_started = True

        with patch.object(autoname_cog.sync_loop, "cancel") as mock_cancel:
            await autoname_cog.cog_unload()
            mock_cancel.assert_called_once()

        assert autoname_cog._sync_started is False

    async def test_cog_unload_only_cancels_if_started(self, autoname_cog: AutonameCog) -> None:
        """Test that cog_unload does not cancel if not started."""
        autoname_cog._sync_started = False

        with patch.object(autoname_cog.sync_loop, "cancel") as mock_cancel:
            await autoname_cog.cog_unload()
            mock_cancel.assert_not_called()


class TestSendLog:
    """Tests for _send_log."""

    async def test_does_nothing_without_channel(self, autoname_cog: AutonameCog) -> None:
        """Test that does nothing if no channel is configured."""
        mock_guild = MagicMock(spec=discord.Guild)
        config: dict[str, object] = {ConfigKey.LOG_MESSAGE_SUCCESS: "Test {old_name}"}

        # No channel configured - should do nothing
        await autoname_cog._send_log(
            mock_guild, config, ConfigKey.LOG_MESSAGE_SUCCESS, old_name="Test"
        )

        mock_guild.get_channel.assert_not_called()

    async def test_does_nothing_with_empty_message(self, autoname_cog: AutonameCog) -> None:
        """Test that does nothing if message is empty."""
        mock_guild = MagicMock(spec=discord.Guild)
        config: dict[str, object] = {
            ConfigKey.LOG_CHANNEL: "123456",
            ConfigKey.LOG_MESSAGE_SUCCESS: "",
        }

        await autoname_cog._send_log(
            mock_guild, config, ConfigKey.LOG_MESSAGE_SUCCESS, old_name="Test"
        )

        mock_guild.get_channel.assert_not_called()

    async def test_sends_formatted_message(self, autoname_cog: AutonameCog) -> None:
        """Test that sends formatted message to channel."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel.return_value = mock_channel

        config: dict[str, object] = {
            ConfigKey.LOG_CHANNEL: "123456",
            ConfigKey.LOG_MESSAGE_SUCCESS: "Changed from {old_name} to {new_name}",
        }

        await autoname_cog._send_log(
            mock_guild,
            config,
            ConfigKey.LOG_MESSAGE_SUCCESS,
            old_name="OldNick",
            new_name="NewNick",
        )

        mock_guild.get_channel.assert_called_once_with(123456)
        mock_channel.send.assert_called_once_with("Changed from OldNick to NewNick")

    async def test_handles_channel_not_found(self, autoname_cog: AutonameCog) -> None:
        """Test that handles when channel does not exist."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel.return_value = None

        config: dict[str, object] = {
            ConfigKey.LOG_CHANNEL: "123456",
            ConfigKey.LOG_MESSAGE_SUCCESS: "Test message",
        }

        # Should not raise
        await autoname_cog._send_log(mock_guild, config, ConfigKey.LOG_MESSAGE_SUCCESS)

    async def test_handles_non_text_channel(self, autoname_cog: AutonameCog) -> None:
        """Test that ignores non-text channels."""
        mock_channel = MagicMock(spec=discord.VoiceChannel)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel.return_value = mock_channel

        config: dict[str, object] = {
            ConfigKey.LOG_CHANNEL: "123456",
            ConfigKey.LOG_MESSAGE_SUCCESS: "Test message",
        }

        # Should not raise or try to send
        await autoname_cog._send_log(mock_guild, config, ConfigKey.LOG_MESSAGE_SUCCESS)

    async def test_handles_missing_placeholder(self, autoname_cog: AutonameCog) -> None:
        """Test that handles missing placeholders."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel.return_value = mock_channel

        config: dict[str, object] = {
            ConfigKey.LOG_CHANNEL: "123456",
            ConfigKey.LOG_MESSAGE_SUCCESS: "Message with {missing_placeholder}",
        }

        # Should not raise - KeyError is caught
        await autoname_cog._send_log(
            mock_guild, config, ConfigKey.LOG_MESSAGE_SUCCESS, old_name="Test"
        )

        mock_channel.send.assert_not_called()

    async def test_handles_http_exception_on_send(self, autoname_cog: AutonameCog) -> None:
        """Test that handles HTTP errors when sending."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "Error"))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel.return_value = mock_channel

        config: dict[str, object] = {
            ConfigKey.LOG_CHANNEL: "123456",
            ConfigKey.LOG_MESSAGE_SUCCESS: "Test {old_name}",
        }

        # Should not raise
        await autoname_cog._send_log(
            mock_guild, config, ConfigKey.LOG_MESSAGE_SUCCESS, old_name="Test"
        )


class TestApplyNicknameSafetyCheck:
    """Tests for safety check in apply_nickname."""

    async def test_skips_when_new_nick_equals_current_nick(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that skips when new_nickname == member.nick."""
        guild_id = mock_member.guild.id
        # compute_nickname will return "[ABC | CAP] Xurxo"
        # but member.nick already has that value
        mock_member.nick = "[ABC | CAP] Xurxo"
        mock_member.display_name = "Xurxo"  # different display_name
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(guild_id, "autoname", ConfigKey.ROLE_TAGS, tags_config)
            await config_service.set_value(
                guild_id, "autoname", ConfigKey.TAG_FORMAT, "[ABC | {tag}]"
            )
            await session.commit()

        result = await autoname_cog.apply_nickname(mock_member)

        assert result is False
        mock_member.edit.assert_not_called()

    async def test_safety_check_catches_edge_case(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test safety check when compute_nickname returns value that already exists."""
        guild_id = mock_member.guild.id
        mock_member.nick = "[ABC | CAP] Xurxo"
        mock_member.display_name = "[ABC | CAP] Xurxo"
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(guild_id, "autoname", ConfigKey.ROLE_TAGS, tags_config)
            await config_service.set_value(
                guild_id, "autoname", ConfigKey.TAG_FORMAT, "[ABC | {tag}]"
            )
            await session.commit()

        # Mock compute_nickname to return a value (simulates edge case)
        with patch(
            "discord_bot.autoname.cog.compute_nickname",
            return_value="[ABC | CAP] Xurxo",
        ):
            result = await autoname_cog.apply_nickname(mock_member)

        assert result is False
        mock_member.edit.assert_not_called()


class TestSyncLoopMethods:
    """Tests for sync_loop and before_sync."""

    async def test_sync_loop_calls_run_sync(self, autoname_cog: AutonameCog) -> None:
        """Test that sync_loop calls _run_sync."""
        with patch.object(autoname_cog, "_run_sync", new_callable=AsyncMock) as mock_run:
            await autoname_cog.sync_loop()
            mock_run.assert_called_once()

    async def test_before_sync_waits_and_runs(self, autoname_cog: AutonameCog) -> None:
        """Test that before_sync waits and runs sync."""
        with patch.object(autoname_cog, "_run_sync", new_callable=AsyncMock) as mock_run:
            await autoname_cog.before_sync()
            cast(MagicMock, autoname_cog.bot).wait_until_ready.assert_called_once()
            mock_run.assert_called_once_with(force_all=True)


class TestRunSyncIntervalCheck:
    """Tests for interval verification in _run_sync."""

    async def test_skips_when_not_due(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test that skips guild when not enough time has passed."""
        from datetime import UTC, datetime, timedelta

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test"
        cast(MagicMock, autoname_cog.bot).guilds = [mock_guild]

        # Configure 30 minute interval
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(mock_guild.id, "autoname", ConfigKey.SYNC_INTERVAL, 30)
            await session.commit()

        # Simulate that it synced 10 minutes ago
        autoname_cog._last_sync[mock_guild.id] = datetime.now(UTC) - timedelta(minutes=10)

        with patch.object(autoname_cog, "_sync_guild") as mock_sync:
            await autoname_cog._run_sync()
            mock_sync.assert_not_called()

    async def test_handles_exception_in_guild_sync(
        self, autoname_cog: AutonameCog, test_database: DatabaseService
    ) -> None:
        """Test that handles exceptions during guild sync."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 456
        mock_guild.name = "Test"
        cast(MagicMock, autoname_cog.bot).guilds = [mock_guild]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name="autoname", enabled=True
            )
            await session.commit()

        with patch.object(autoname_cog, "_get_sync_interval", side_effect=Exception("Test error")):
            # Should not raise
            await autoname_cog._run_sync()


class TestSyncGuildErrorHandling:
    """Tests for error handling in _sync_guild."""

    async def test_handles_exception_in_apply_nickname(
        self,
        autoname_cog: AutonameCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that handles exceptions when applying nickname."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = mock_member.guild.id
        mock_guild.name = "Test"
        mock_guild.members = [mock_member]
        tags_config = [{"role_id": 100, "tag": "CAP"}]

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name="autoname", enabled=True
            )
            await config_service.set_value(
                mock_guild.id, "autoname", ConfigKey.ROLE_TAGS, tags_config
            )
            await session.commit()

        with patch.object(
            autoname_cog,
            "apply_nickname",
            new_callable=AsyncMock,
            side_effect=Exception("Test error"),
        ):
            # Should not raise
            await autoname_cog._sync_guild(mock_guild)


class TestSetupAndTeardown:
    """Tests for setup and teardown of the cog."""

    async def test_setup_registers_schema_and_adds_cog(self, mock_discord_bot: MagicMock) -> None:
        """Test that setup registers the schema and adds the cog."""
        from discord_bot.autoname.cog import setup
        from discord_bot.common.services.config_schema_service import (
            get_config_schema_service,
        )

        mock_discord_bot.add_cog = AsyncMock()

        await setup(mock_discord_bot)

        mock_discord_bot.add_cog.assert_called_once()
        # Verify that the schema was registered
        schema = get_config_schema_service().get_schema("autoname")
        assert schema == AUTONAME_CONFIG_SCHEMA

    async def test_teardown_unregisters_schema(self, mock_discord_bot: MagicMock) -> None:
        """Test that teardown unregisters the schema."""
        from discord_bot.autoname.cog import setup, teardown
        from discord_bot.common.services.config_schema_service import (
            get_config_schema_service,
        )

        mock_discord_bot.add_cog = AsyncMock()

        # First setup to register
        await setup(mock_discord_bot)
        assert get_config_schema_service().get_schema("autoname") is not None

        # Then teardown
        await teardown(mock_discord_bot)
        assert get_config_schema_service().get_schema("autoname") is None
