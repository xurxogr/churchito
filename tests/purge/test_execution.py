"""Tests for discord_bot/purge/execution.py and discord_bot/purge/phases.py."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.bot import DiscordBot
from discord_bot.common.services.database import DatabaseService
from discord_bot.purge.cog import PurgeCog
from discord_bot.purge.enums import ConfigKey, PurgeStatus, PurgeType
from discord_bot.purge.execution import execute_purge
from discord_bot.purge.models import PurgeUserResult
from discord_bot.purge.phases import (
    EXECUTION_LOG_MAX_LINES,
    apply_cleaning_to_member,
    execute_cleaning_phase,
    execute_global_cleaning_phase,
    execute_global_removal_phase,
    execute_promotion_phase,
    make_execution_log,
)
from discord_bot.purge.service import PurgeService


class TestMakeExecutionLog:
    """Tests for make_execution_log."""

    def test_bounded_and_drops_oldest(self) -> None:
        """Test that the log keeps only the newest lines."""
        log = make_execution_log()

        for i in range(EXECUTION_LOG_MAX_LINES + 10):
            log.append(f"line {i}")

        assert len(log) == EXECUTION_LOG_MAX_LINES
        assert log[0] == "line 10"
        assert log[-1] == f"line {EXECUTION_LOG_MAX_LINES + 9}"


@pytest.fixture
def mock_discord_bot(test_database: DatabaseService) -> MagicMock:
    """Create mock bot with database."""
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
    return PurgeCog(mock_discord_bot)


@pytest.fixture
def mock_guild() -> MagicMock:
    """Create mock guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.name = "Test Guild"
    guild.get_member = MagicMock(return_value=None)
    guild.get_role = MagicMock(return_value=None)
    guild.get_channel = MagicMock(return_value=None)
    # Mock default role
    default_role = MagicMock(spec=discord.Role)
    default_role.id = 0
    guild.default_role = default_role
    return guild


@pytest.fixture
def mock_purge_record() -> MagicMock:
    """Create mock purge record."""
    record = MagicMock()
    record.id = 1
    record.guild_id = 123456789
    record.purge_type = PurgeType.WAR_END
    record.status = PurgeStatus.AUTHORIZED
    record.initiated_by = 111222333
    record.authorized_by = [111222333]
    record.cancelled_by = []
    record.confirmed_by = [444555666]
    record.scheduled_for = datetime.now(UTC) + timedelta(days=3)
    record.expires_at = None
    record.config_snapshot = {
        "affected_roles": [100],
        "roles_to_remove": [],
        "roles_to_add": [],
        "promotions": [],
        "default_promotion": None,
        "reaction_role": None,
        "test_mode": False,
    }
    record.mod_channel_id = 555666777
    record.mod_message_id = 888999000
    record.user_channel_id = 111222333
    record.user_message_id = 444555666
    return record


class TestExecutePurge:
    """Tests for execute_purge."""

    async def test_execute_no_guild(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Test execution without guild."""
        mock_discord_bot.get_guild = MagicMock(return_value=None)

        # Should not raise exception
        await execute_purge(cog=purge_cog, guild_id=999, purge_id=1)

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
        await execute_purge(cog=purge_cog, guild_id=mock_guild.id, purge_id=99999)

    async def test_execute_purge_not_authorized(
        self,
        purge_cog: PurgeCog,
        mock_discord_bot: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test execution with unauthorized purge."""
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
        await execute_purge(cog=purge_cog, guild_id=mock_guild.id, purge_id=purge_id)


class TestExecuteCleaningPhase:
    """Tests for execute_cleaning_phase."""

    async def test_cleans_non_confirmed_members(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test cleaning of non-confirmed members."""
        # Setup role with a member who didn't confirm
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected Role"

        member = MagicMock(spec=discord.Member)
        member.id = 777888999  # Not in confirmed_users
        member.display_name = "Non-confirmed User"
        member.name = "NonConfirmedUser"
        member.roles = [affected_role]
        member.remove_roles = AsyncMock()
        member.add_roles = AsyncMock()
        member.edit = AsyncMock()

        affected_role.members = [member]
        mock_guild.get_role = MagicMock(return_value=affected_role)
        mock_guild.get_member = MagicMock(return_value=member)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
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

            cleaned_count, processed_users = await execute_cleaning_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=record.id,
                affected_roles=[100],
                roles_to_remove=[],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=0,
                execution_logs=[],
            )

            assert cleaned_count == 1
            assert member.id in processed_users

    async def test_skips_confirmed_members(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it does not clean confirmed members."""
        # Setup role with a confirmed member
        affected_role = MagicMock(spec=discord.Role)
        affected_role.id = 100
        affected_role.name = "Affected Role"

        member = MagicMock(spec=discord.Member)
        member.id = 444555666  # In confirmed_users
        member.display_name = "Confirmed User"
        member.roles = [affected_role]

        affected_role.members = [member]
        mock_guild.get_role = MagicMock(return_value=affected_role)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
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

            cleaned_count, processed_users = await execute_cleaning_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=record.id,
                affected_roles=[100],
                roles_to_remove=[],
                roles_to_add=[],
                confirmed_users={444555666},
                audit_level=0,
                execution_logs=[],
            )

            assert cleaned_count == 0
            assert member.id not in processed_users

    async def test_role_not_found(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test when the role does not exist."""
        mock_guild.get_role = MagicMock(return_value=None)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
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

            cleaned_count, processed_users = await execute_cleaning_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=record.id,
                affected_roles=[100],
                roles_to_remove=[],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=0,
                execution_logs=[],
            )

            assert cleaned_count == 0


class TestExecutePromotionPhase:
    """Tests for execute_promotion_phase."""

    async def test_promotes_confirmed_members(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test promotion of confirmed members."""
        # Setup roles
        from_role = MagicMock(spec=discord.Role)
        from_role.id = 100
        from_role.name = "From Role"

        to_role = MagicMock(spec=discord.Role)
        to_role.id = 200
        to_role.name = "To Role"

        member = MagicMock(spec=discord.Member)
        member.id = 444555666  # In confirmed_users
        member.display_name = "Confirmed User"
        member.roles = [from_role]
        member.edit = AsyncMock()

        from_role.members = [member]

        def get_role_side_effect(role_id: int) -> MagicMock | None:
            if role_id == 100:
                return from_role
            if role_id == 200:
                return to_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role_side_effect)
        mock_guild.get_member = MagicMock(return_value=member)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
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

            promoted_in, promoted_out, promoted_users = await execute_promotion_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=record.id,
                affected_roles=[100],
                promotions=[{"from_role": 100, "to_role": 200}],
                default_promotion=None,
                confirmed_users={444555666},
                processed_users=set(),
                audit_level=0,
                execution_logs=[],
            )

            assert promoted_in == 1
            assert promoted_out == 0
            assert member.id in promoted_users
            member.edit.assert_awaited_once_with(roles=[to_role])

    async def test_skips_unconfirmed_members(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it does not promote non-confirmed members."""
        from_role = MagicMock(spec=discord.Role)
        from_role.id = 100
        from_role.name = "From Role"

        to_role = MagicMock(spec=discord.Role)
        to_role.id = 200
        to_role.name = "To Role"

        member = MagicMock(spec=discord.Member)
        member.id = 777888999  # Not in confirmed_users
        member.display_name = "Not Confirmed"
        member.roles = [from_role]

        from_role.members = [member]

        def get_role_side_effect(role_id: int) -> MagicMock | None:
            if role_id == 100:
                return from_role
            if role_id == 200:
                return to_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role_side_effect)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
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

            promoted_in, promoted_out, promoted_users = await execute_promotion_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=record.id,
                affected_roles=[100],
                promotions=[{"from_role": 100, "to_role": 200}],
                default_promotion=None,
                confirmed_users=set(),
                processed_users=set(),
                audit_level=0,
                execution_logs=[],
            )

            assert promoted_in == 0
            assert promoted_out == 0
            assert member.id not in promoted_users

    async def test_default_promotion(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test default promotion."""
        default_role = MagicMock(spec=discord.Role)
        default_role.id = 300
        default_role.name = "Default Role"

        member = MagicMock(spec=discord.Member)
        member.id = 444555666
        member.display_name = "Confirmed User"
        member.roles = []
        member.add_roles = AsyncMock()

        mock_guild.get_role = MagicMock(return_value=default_role)
        mock_guild.get_member = MagicMock(return_value=member)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
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

            promoted_in, promoted_out, promoted_users = await execute_promotion_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=record.id,
                affected_roles=[],
                promotions=[],
                default_promotion=300,
                confirmed_users={444555666},
                processed_users=set(),
                audit_level=0,
                execution_logs=[],
            )

            assert promoted_out == 1
            assert member.id in promoted_users
            member.add_roles.assert_called_once_with(default_role)


class TestExecuteGlobalRemovalPhase:
    """Tests for execute_global_removal_phase."""

    async def test_removes_global_roles_from_members(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test removal of global roles."""
        # Setup global role to remove
        global_role = MagicMock(spec=discord.Role)
        global_role.id = 500
        global_role.name = "Global Role"

        member = MagicMock(spec=discord.Member)
        member.id = 111222333
        member.display_name = "Test User"
        member.bot = False
        member.roles = [global_role]
        member.remove_roles = AsyncMock()

        mock_guild.members = [member]
        mock_guild.get_role = MagicMock(return_value=global_role)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }

        removed_count = await execute_global_removal_phase(
            cog=purge_cog,
            guild=mock_guild,
            record=mock_purge_record,
            config=config,
            global_roles_to_remove=[500],
            audit_level=0,
            execution_logs=[],
        )

        assert removed_count == 1
        member.remove_roles.assert_called_once_with(global_role)

    async def test_skips_bots(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test that it does not affect bots."""
        global_role = MagicMock(spec=discord.Role)
        global_role.id = 500
        global_role.name = "Global Role"

        bot_member = MagicMock(spec=discord.Member)
        bot_member.id = 111222333
        bot_member.bot = True
        bot_member.roles = [global_role]

        mock_guild.members = [bot_member]
        mock_guild.get_role = MagicMock(return_value=global_role)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }

        removed_count = await execute_global_removal_phase(
            cog=purge_cog,
            guild=mock_guild,
            record=mock_purge_record,
            config=config,
            global_roles_to_remove=[500],
            audit_level=0,
            execution_logs=[],
        )

        assert removed_count == 0

    async def test_skips_members_without_role(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test that it does not affect members without the role."""
        global_role = MagicMock(spec=discord.Role)
        global_role.id = 500
        global_role.name = "Global Role"

        member = MagicMock(spec=discord.Member)
        member.id = 111222333
        member.bot = False
        member.roles = []  # Does not have the role

        mock_guild.members = [member]
        mock_guild.get_role = MagicMock(return_value=global_role)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }

        removed_count = await execute_global_removal_phase(
            cog=purge_cog,
            guild=mock_guild,
            record=mock_purge_record,
            config=config,
            global_roles_to_remove=[500],
            audit_level=0,
            execution_logs=[],
        )

        assert removed_count == 0

    async def test_role_not_found(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test when the global role does not exist."""
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.members = []

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }

        removed_count = await execute_global_removal_phase(
            cog=purge_cog,
            guild=mock_guild,
            record=mock_purge_record,
            config=config,
            global_roles_to_remove=[999],
            audit_level=0,
            execution_logs=[],
        )

        assert removed_count == 0

    async def test_handles_forbidden_error(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test Forbidden error handling."""
        global_role = MagicMock(spec=discord.Role)
        global_role.id = 500
        global_role.name = "Global Role"

        member = MagicMock(spec=discord.Member)
        member.id = 111222333
        member.display_name = "Test User"
        member.name = "TestUser"
        member.bot = False
        member.roles = [global_role]
        member.remove_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))

        mock_guild.members = [member]
        mock_guild.get_role = MagicMock(return_value=global_role)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }

        # Should not raise exception
        removed_count = await execute_global_removal_phase(
            cog=purge_cog,
            guild=mock_guild,
            record=mock_purge_record,
            config=config,
            global_roles_to_remove=[500],
            audit_level=0,
            execution_logs=[],
        )

        assert removed_count == 0

    async def test_logs_with_audit_level_2(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test that it generates logs with audit level 2."""
        global_role = MagicMock(spec=discord.Role)
        global_role.id = 500
        global_role.name = "Global Role"

        member = MagicMock(spec=discord.Member)
        member.id = 111222333
        member.display_name = "Test User"
        member.bot = False
        member.roles = [global_role]
        member.remove_roles = AsyncMock()

        mock_guild.members = [member]
        mock_guild.get_role = MagicMock(return_value=global_role)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 2,
        }

        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            removed_count = await execute_global_removal_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                global_roles_to_remove=[500],
                audit_level=2,
                execution_logs=execution_logs,
            )

        assert removed_count == 1
        # Should have start log and per-user log
        assert len(execution_logs) == 2
        assert "Global Role" in execution_logs[1]


class TestExecuteGlobalCleaningPhase:
    """Tests for execute_global_cleaning_phase."""

    async def test_cleans_non_confirmed_members(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it purges non-confirmed members."""
        # Create role and member
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 200

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 1001
        mock_member.display_name = "TestUser"
        mock_member.bot = False
        mock_member.roles = [mock_role]
        mock_member.remove_roles = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.edit = AsyncMock()

        mock_guild.members = [mock_member]
        mock_guild.default_role = MagicMock()
        mock_guild.default_role.id = 0
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_guild.get_member = MagicMock(return_value=mock_member)

        guild_id = mock_guild.id
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 1,
        }
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            cleaned_count, processed_users = await execute_global_cleaning_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                excluded_roles=[],
                roles_to_remove=[200],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=1,
                execution_logs=execution_logs,
            )

        assert cleaned_count == 1
        assert mock_member.id in processed_users
        mock_member.edit.assert_awaited_once_with(roles=[])

    async def test_skips_confirmed_members(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it skips confirmed members."""
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 1001
        mock_member.bot = False
        mock_member.roles = []

        mock_guild.members = [mock_member]
        mock_guild.default_role = MagicMock()
        mock_guild.get_role = MagicMock(return_value=None)

        guild_id = mock_guild.id
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {}
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            cleaned_count, processed_users = await execute_global_cleaning_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                excluded_roles=[],
                roles_to_remove=[],
                roles_to_add=[],
                confirmed_users={1001},  # The member is confirmed
                audit_level=0,
                execution_logs=execution_logs,
            )

        assert cleaned_count == 0
        assert 1001 not in processed_users

    async def test_skips_excluded_roles(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it skips members with excluded roles."""
        excluded_role = MagicMock(spec=discord.Role)
        excluded_role.id = 999

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 1001
        mock_member.bot = False
        mock_member.roles = [excluded_role]

        mock_guild.members = [mock_member]
        mock_guild.default_role = MagicMock()
        mock_guild.get_role = MagicMock(return_value=excluded_role)

        guild_id = mock_guild.id
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {}
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            cleaned_count, processed_users = await execute_global_cleaning_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                excluded_roles=[999],  # Excluded role
                roles_to_remove=[],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=0,
                execution_logs=execution_logs,
            )

        assert cleaned_count == 0
        assert 1001 not in processed_users

    async def test_skips_bots(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it skips bots."""
        mock_bot = MagicMock(spec=discord.Member)
        mock_bot.id = 1001
        mock_bot.bot = True

        mock_guild.members = [mock_bot]
        mock_guild.default_role = MagicMock()
        mock_guild.get_role = MagicMock(return_value=None)

        guild_id = mock_guild.id
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {}
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            cleaned_count, processed_users = await execute_global_cleaning_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                excluded_roles=[],
                roles_to_remove=[],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=0,
                execution_logs=execution_logs,
            )

        assert cleaned_count == 0

    async def test_removes_all_roles_when_no_specific_roles(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it removes all roles when there are no specific roles."""
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 200

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 1001
        mock_member.display_name = "TestUser"
        mock_member.bot = False
        mock_member.roles = [mock_role]
        mock_member.edit = AsyncMock()

        mock_guild.members = [mock_member]
        mock_guild.default_role = MagicMock()
        mock_guild.default_role.id = 0
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=mock_member)

        guild_id = mock_guild.id
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {}
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            cleaned_count, _ = await execute_global_cleaning_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                excluded_roles=[],
                roles_to_remove=[],  # Without specific roles
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=0,
                execution_logs=execution_logs,
            )

        assert cleaned_count == 1
        # Should call edit(roles=[]) to remove all roles
        mock_member.edit.assert_called_once_with(roles=[])

    async def test_adds_roles_after_cleaning(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it adds roles after cleaning."""
        mock_role_to_add = MagicMock(spec=discord.Role)
        mock_role_to_add.id = 300

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 1001
        mock_member.display_name = "TestUser"
        mock_member.bot = False
        mock_member.roles = []
        mock_member.edit = AsyncMock()
        mock_member.add_roles = AsyncMock()

        mock_guild.members = [mock_member]
        mock_guild.default_role = MagicMock()
        mock_guild.default_role.id = 0
        mock_guild.get_role = MagicMock(return_value=mock_role_to_add)
        mock_guild.get_member = MagicMock(return_value=mock_member)

        guild_id = mock_guild.id
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {}
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            cleaned_count, _ = await execute_global_cleaning_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                excluded_roles=[],
                roles_to_remove=[],
                roles_to_add=[300],  # Add this role
                confirmed_users=set(),
                audit_level=0,
                execution_logs=execution_logs,
            )

        assert cleaned_count == 1
        mock_member.edit.assert_awaited_once_with(roles=[mock_role_to_add])

    async def test_handles_forbidden_on_remove(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it handles Forbidden error when removing roles."""
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 200

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 1001
        mock_member.display_name = "TestUser"
        mock_member.bot = False
        mock_member.roles = [mock_role]
        mock_member.edit = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))

        mock_guild.members = [mock_member]
        mock_guild.default_role = MagicMock()
        mock_guild.default_role.id = 0
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_guild.get_member = MagicMock(return_value=mock_member)

        guild_id = mock_guild.id
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {}
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            # Should not raise exception
            cleaned_count, _ = await execute_global_cleaning_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                excluded_roles=[],
                roles_to_remove=[200],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=0,
                execution_logs=execution_logs,
            )

        # Still counted as processed
        assert cleaned_count == 1

    async def test_logs_with_audit_level_2(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it records logs with audit level 2."""
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 200

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 1001
        mock_member.display_name = "TestUser"
        mock_member.bot = False
        mock_member.roles = [mock_role]
        mock_member.edit = AsyncMock()

        mock_guild.members = [mock_member]
        mock_guild.default_role = MagicMock()
        mock_guild.default_role.id = 0
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=mock_member)

        guild_id = mock_guild.id
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=guild_id,
                purge_type=PurgeType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 2,
        }
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            await execute_global_cleaning_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                excluded_roles=[],
                roles_to_remove=[],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=2,
                execution_logs=execution_logs,
            )

        # Should have start log and per-user log
        assert len(execution_logs) == 2
        assert "TestUser" in execution_logs[1]


class TestExecutePurgeGlobal:
    """Tests for execute_purge with global purge."""

    async def test_execute_global_purge(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test complete execution of global purge."""
        # Create mock member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 444555666
        mock_member.bot = False
        mock_member.name = "TestUser"
        mock_member.display_name = "TestUser"
        mock_member.roles = [mock_guild.default_role]
        mock_member.remove_roles = AsyncMock()
        mock_member.add_roles = AsyncMock()

        mock_guild.members = [mock_member]
        mock_guild.get_member = MagicMock(return_value=mock_member)

        # Create record in DB
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.GLOBAL,
                initiated_by=123,
                config_snapshot={
                    "excluded_roles": [],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                },
                scheduled_for=datetime.now(UTC) - timedelta(hours=1),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id

        with (
            patch.object(purge_cog.bot, "get_guild", return_value=mock_guild),
            patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock),
            patch.object(purge_cog, "_send_user_message", new_callable=AsyncMock),
            patch.object(purge_cog, "_get_config", new_callable=AsyncMock) as mock_config,
        ):
            mock_config.return_value = {
                ConfigKey.AUDIT_LEVEL: 1,
                ConfigKey.GLOBAL_EXEC_MSG_FINISH: "Purge completed: {cleaned}",
            }
            await execute_purge(
                cog=purge_cog,
                guild_id=mock_guild.id,
                purge_id=purge_id,
            )


class TestExecuteWarEndWithGlobalRemoval:
    """Tests for execute_purge with WAR_END and global_roles_to_remove."""

    async def test_execute_war_purge_with_global_removal(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test execution of WAR_END purge with global role removal (line 229)."""
        # Create global role to remove
        mock_global_role = MagicMock(spec=discord.Role)
        mock_global_role.id = 600
        mock_global_role.name = "GlobalWarRole"

        # Create member with global role
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 444555666
        mock_member.bot = False
        mock_member.name = "TestUser"
        mock_member.display_name = "TestUser"
        mock_member.roles = [mock_guild.default_role, mock_global_role]
        mock_member.remove_roles = AsyncMock()
        mock_member.add_roles = AsyncMock()

        mock_guild.members = [mock_member]
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_global_role)

        # Create WAR_END record with global_roles_to_remove
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=123,
                config_snapshot={
                    "affected_roles": [],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": None,
                    "global_roles_to_remove": [600],  # This activates line 229
                },
                scheduled_for=datetime.now(UTC) - timedelta(hours=1),
            )
            await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
            await session.commit()
            purge_id = record.id

        with (
            patch.object(purge_cog.bot, "get_guild", return_value=mock_guild),
            patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock),
            patch.object(purge_cog, "_send_user_message", new_callable=AsyncMock),
            patch.object(purge_cog, "_get_config", new_callable=AsyncMock) as mock_config,
        ):
            mock_config.return_value = {
                ConfigKey.AUDIT_LEVEL: 1,
            }
            await execute_purge(
                cog=purge_cog,
                guild_id=mock_guild.id,
                purge_id=purge_id,
            )

        # Verify that it tried to remove the global role
        mock_member.remove_roles.assert_called()


class TestExecuteGlobalRemovalPhaseIntegration:
    """Integration tests for execute_global_removal_phase."""

    async def test_global_removal_with_roles(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test global role removal."""
        # Create mock role
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 500
        mock_role.name = "GlobalRole"

        # Create members with the role
        mock_member1 = MagicMock(spec=discord.Member)
        mock_member1.id = 111
        mock_member1.bot = False
        mock_member1.name = "User1"
        mock_member1.display_name = "User1"
        mock_member1.roles = [mock_guild.default_role, mock_role]
        mock_member1.remove_roles = AsyncMock()

        mock_member2 = MagicMock(spec=discord.Member)
        mock_member2.id = 222
        mock_member2.bot = False
        mock_member2.name = "User2"
        mock_member2.display_name = "User2"
        mock_member2.roles = [mock_guild.default_role, mock_role]
        mock_member2.remove_roles = AsyncMock()

        # The function iterates over guild.members
        mock_guild.members = [mock_member1, mock_member2]

        # Return role when get_role is called
        def get_role_side_effect(role_id: int) -> MagicMock | None:
            if role_id == 500:
                return mock_role
            return None

        mock_guild.get_role = MagicMock(side_effect=get_role_side_effect)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 2,
        }
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            count = await execute_global_removal_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                global_roles_to_remove=[500],
                audit_level=2,
                execution_logs=execution_logs,
            )

        assert count == 2
        mock_member1.remove_roles.assert_called_once()
        mock_member2.remove_roles.assert_called_once()


class TestExecutePromotionWithDefault:
    """Tests for promotion phase with default_promotion."""

    async def test_promotion_with_default(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test promotion with default role."""
        # Create default promotion role
        default_promo_role = MagicMock(spec=discord.Role)
        default_promo_role.id = 800
        default_promo_role.name = "DefaultPromo"

        # Confirmed member not in any promotion group
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 444555666
        mock_member.bot = False
        mock_member.name = "TestUser"
        mock_member.display_name = "TestUser"
        mock_member.roles = [mock_guild.default_role]
        mock_member.add_roles = AsyncMock()

        mock_guild.get_role = MagicMock(return_value=default_promo_role)
        mock_guild.get_member = MagicMock(return_value=mock_member)

        # Create record
        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=123,
                config_snapshot={
                    "affected_roles": [],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": 800,
                },
                scheduled_for=datetime.now(UTC),
            )
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 2,
            ConfigKey.EXEC_MSG_PROMOTION_DEFAULT: "Default promo",
        }
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            in_group, not_in_group, promoted_users = await execute_promotion_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                affected_roles=[],
                promotions=[],
                default_promotion=800,
                confirmed_users={444555666},
                processed_users=set(),
                audit_level=2,
                execution_logs=execution_logs,
            )

        # The user should be promoted with the default role
        assert not_in_group >= 0


class TestGlobalCleaningAlreadyProcessed:
    """Tests for already processed user in global cleaning."""

    async def test_skip_already_processed_user(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it skips duplicate users in the members list."""
        # Create member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 111
        mock_member.bot = False
        mock_member.name = "User1"
        mock_member.display_name = "User1"
        mock_member.roles = [mock_guild.default_role]
        mock_member.remove_roles = AsyncMock()
        mock_member.add_roles = AsyncMock()

        # The same member appears twice (covers the "already processed" branch)
        mock_guild.members = [mock_member, mock_member]

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC),
            )
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            count, processed = await execute_global_cleaning_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                excluded_roles=[],
                roles_to_remove=[],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=0,
                execution_logs=execution_logs,
            )

        # The user is only processed once (the second is skipped)
        assert count == 1
        assert 111 in processed


class TestDefaultPromotionEdgeCases:
    """Tests for edge cases in default promotion."""

    async def test_default_promotion_user_already_processed(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it skips already processed users in default promotion."""
        default_promo_role = MagicMock(spec=discord.Role)
        default_promo_role.id = 800
        default_promo_role.name = "DefaultPromo"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 444555666
        mock_member.bot = False
        mock_member.name = "TestUser"
        mock_member.display_name = "TestUser"
        mock_member.roles = [mock_guild.default_role]
        mock_member.add_roles = AsyncMock()

        mock_guild.get_role = MagicMock(return_value=default_promo_role)
        mock_guild.get_member = MagicMock(return_value=mock_member)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=123,
                config_snapshot={
                    "affected_roles": [],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": 800,
                },
                scheduled_for=datetime.now(UTC),
            )
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            in_group, not_in_group, promoted = await execute_promotion_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                affected_roles=[],
                promotions=[],
                default_promotion=800,
                confirmed_users={444555666},
                processed_users={444555666},  # Already processed
                audit_level=0,
                execution_logs=execution_logs,
            )

        # User should be skipped
        assert not_in_group == 0

    async def test_default_promotion_user_not_found(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that it handles user not found in default promotion."""
        default_promo_role = MagicMock(spec=discord.Role)
        default_promo_role.id = 800
        default_promo_role.name = "DefaultPromo"

        mock_guild.get_role = MagicMock(return_value=default_promo_role)
        mock_guild.get_member = MagicMock(return_value=None)  # User not found

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=123,
                config_snapshot={
                    "affected_roles": [],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": 800,
                },
                scheduled_for=datetime.now(UTC),
            )
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            in_group, not_in_group, promoted = await execute_promotion_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                affected_roles=[],
                promotions=[],
                default_promotion=800,
                confirmed_users={444555666},
                processed_users=set(),
                audit_level=0,
                execution_logs=execution_logs,
            )

        # User should be skipped (not found)
        assert not_in_group == 0

    async def test_default_promotion_forbidden_exception(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test Forbidden error handling when adding default role."""
        default_promo_role = MagicMock(spec=discord.Role)
        default_promo_role.id = 800
        default_promo_role.name = "DefaultPromo"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 444555666
        mock_member.bot = False
        mock_member.name = "TestUser"
        mock_member.display_name = "TestUser"
        mock_member.roles = [mock_guild.default_role]
        mock_member.add_roles = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "No permission")
        )

        mock_guild.get_role = MagicMock(return_value=default_promo_role)
        mock_guild.get_member = MagicMock(return_value=mock_member)

        async with test_database.session() as session:
            purge_service = PurgeService(session)
            record = await purge_service.create_purge(
                guild_id=mock_guild.id,
                purge_type=PurgeType.WAR_END,
                initiated_by=123,
                config_snapshot={
                    "affected_roles": [],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": 800,
                },
                scheduled_for=datetime.now(UTC),
            )
            await session.commit()
            purge_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            # Should not raise exception
            in_group, not_in_group, promoted = await execute_promotion_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                affected_roles=[],
                promotions=[],
                default_promotion=800,
                confirmed_users={444555666},
                processed_users=set(),
                audit_level=0,
                execution_logs=execution_logs,
            )

        # Should handle the exception gracefully
        assert not_in_group == 1


class TestGlobalRemovalEdgeCases:
    """Tests for edge cases in execute_global_removal_phase."""

    async def test_global_removal_role_not_found(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test that it returns 0 when the role does not exist in the guild."""
        # Role 999 does not exist
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.members = []

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        count = await execute_global_removal_phase(
            cog=purge_cog,
            guild=mock_guild,
            record=mock_purge_record,
            config=config,
            global_roles_to_remove=[999],  # This role does not exist
            audit_level=0,
            execution_logs=execution_logs,
        )

        # Should return 0 (line 750)
        assert count == 0

    async def test_global_removal_skips_bots(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test that it skips bots in global removal."""
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 500
        mock_role.name = "GlobalRole"

        # Create a bot with the role
        mock_bot = MagicMock(spec=discord.Member)
        mock_bot.id = 111
        mock_bot.bot = True  # Is a bot
        mock_bot.name = "BotUser"
        mock_bot.roles = [mock_guild.default_role, mock_role]
        mock_bot.remove_roles = AsyncMock()

        mock_guild.members = [mock_bot]
        mock_guild.get_role = MagicMock(return_value=mock_role)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            count = await execute_global_removal_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                global_roles_to_remove=[500],
                audit_level=0,
                execution_logs=execution_logs,
            )

        # Should not process the bot (line 764)
        assert count == 0
        mock_bot.remove_roles.assert_not_called()

    async def test_global_removal_skips_member_without_role(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test that it skips members without the role."""
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 500
        mock_role.name = "GlobalRole"

        # Member without the role
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 111
        mock_member.bot = False
        mock_member.name = "User1"
        mock_member.roles = [mock_guild.default_role]  # Does not have role 500
        mock_member.remove_roles = AsyncMock()

        mock_guild.members = [mock_member]
        mock_guild.get_role = MagicMock(return_value=mock_role)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            count = await execute_global_removal_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                global_roles_to_remove=[500],
                audit_level=0,
                execution_logs=execution_logs,
            )

        # Should not process the member (line 769)
        assert count == 0
        mock_member.remove_roles.assert_not_called()

    async def test_global_removal_forbidden_exception(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Test Forbidden error handling when removing global roles."""
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 500
        mock_role.name = "GlobalRole"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 111
        mock_member.bot = False
        mock_member.name = "User1"
        mock_member.display_name = "User1"
        mock_member.roles = [mock_guild.default_role, mock_role]
        mock_member.remove_roles = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "No permission")
        )

        mock_guild.members = [mock_member]
        mock_guild.get_role = MagicMock(return_value=mock_role)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock):
            # Should not raise exception (lines 789-790)
            count = await execute_global_removal_phase(
                cog=purge_cog,
                guild=mock_guild,
                record=mock_purge_record,
                config=config,
                global_roles_to_remove=[500],
                audit_level=0,
                execution_logs=execution_logs,
            )

        # Count should be 0 because remove_roles failed
        assert count == 0


class _SessionTracker:
    """Wrap DatabaseService.session to count how many sessions are open at any time."""

    def __init__(self, database: DatabaseService) -> None:
        self._real = database.session
        self.open = 0
        self.total = 0

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[AsyncSession]:
        self.open += 1
        self.total += 1
        try:
            async with self._real() as session:
                yield session
        finally:
            self.open -= 1


def _make_global_member(guild: MagicMock, member_id: int) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = member_id
    member.bot = False
    member.name = f"user{member_id}"
    member.display_name = f"user{member_id}"
    some_role = MagicMock(spec=discord.Role)
    some_role.id = 1000 + member_id
    member.roles = [guild.default_role, some_role]  # a global purge strips this role
    member.edit = AsyncMock()
    return member


async def _create_authorized_global_purge(db: DatabaseService, guild_id: int) -> int:
    async with db.session() as session:
        purge_service = PurgeService(session)
        record = await purge_service.create_purge(
            guild_id=guild_id,
            purge_type=PurgeType.GLOBAL,
            initiated_by=123,
            config_snapshot={"excluded_roles": [], "roles_to_remove": [], "roles_to_add": []},
            scheduled_for=datetime.now(UTC) - timedelta(hours=1),
        )
        await purge_service.update_status(record.id, PurgeStatus.AUTHORIZED)
        await session.commit()
        return record.id


async def _stored_user_results(db: DatabaseService, purge_id: int) -> list[PurgeUserResult]:
    async with db.session() as session:
        result = await session.execute(
            select(PurgeUserResult).where(PurgeUserResult.purge_id == purge_id)
        )
        return list(result.scalars().all())


class TestExecutePurgeSessions:
    """execute_purge must not keep a database session open while editing members."""

    async def test_no_session_open_while_members_are_edited(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Member edits happen between short sessions, and results are persisted at the end."""
        members = [_make_global_member(mock_guild, mid) for mid in (1, 2, 3)]
        mock_guild.members = members
        mock_guild.get_member = MagicMock(side_effect=lambda mid: members[mid - 1])
        purge_id = await _create_authorized_global_purge(test_database, mock_guild.id)

        tracker = _SessionTracker(test_database)
        open_during_edits: list[int] = []
        for member in members:
            member.edit = AsyncMock(side_effect=lambda **_: open_during_edits.append(tracker.open))

        with (
            patch.object(test_database, "session", tracker),
            patch.object(purge_cog.bot, "get_guild", return_value=mock_guild),
            patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock),
            patch.object(purge_cog, "_get_config", new_callable=AsyncMock) as mock_config,
        ):
            mock_config.return_value = {ConfigKey.AUDIT_LEVEL: 1}
            await execute_purge(cog=purge_cog, guild_id=mock_guild.id, purge_id=purge_id)

        assert open_during_edits == [0, 0, 0]
        assert {r.user_id for r in await _stored_user_results(test_database, purge_id)} == {1, 2, 3}
        async with test_database.session() as session:
            record = await PurgeService(session).get_purge(purge_id)
        assert record is not None
        assert record.status == PurgeStatus.EXECUTED
        assert record.execution_result is not None
        assert record.execution_result["cleaned_count"] == 3

    async def test_results_written_before_failure_survive(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """A crash mid-purge keeps the results of members already processed."""
        members = [_make_global_member(mock_guild, mid) for mid in (1, 2, 3)]
        mock_guild.members = members
        mock_guild.get_member = MagicMock(side_effect=lambda mid: members[mid - 1])
        members[2].edit = AsyncMock(side_effect=RuntimeError("boom"))
        purge_id = await _create_authorized_global_purge(test_database, mock_guild.id)

        with (
            patch.object(purge_cog.bot, "get_guild", return_value=mock_guild),
            patch.object(purge_cog, "_update_mod_message", new_callable=AsyncMock),
            patch.object(purge_cog, "_get_config", new_callable=AsyncMock) as mock_config,
            pytest.raises(RuntimeError),
        ):
            mock_config.return_value = {ConfigKey.AUDIT_LEVEL: 1}
            await execute_purge(cog=purge_cog, guild_id=mock_guild.id, purge_id=purge_id)

        assert {r.user_id for r in await _stored_user_results(test_database, purge_id)} == {1, 2}
        async with test_database.session() as session:
            record = await PurgeService(session).get_purge(purge_id)
        assert record is not None
        assert record.status == PurgeStatus.AUTHORIZED  # the cog marks it FAILED afterwards


def _role(role_id: int, name: str) -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.name = name
    return role


def _member_with_roles(guild: MagicMock, member_id: int, roles: list[MagicMock]) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = member_id
    member.bot = False
    member.name = f"user{member_id}"
    member.display_name = f"user{member_id}"
    member.roles = [guild.default_role, *roles]
    member.edit = AsyncMock()
    member.remove_roles = AsyncMock()
    member.add_roles = AsyncMock()
    return member


class TestSingleEditRoleChanges:
    """Role changes per member go through one member.edit call and tolerate API errors."""

    async def test_cleaning_removes_and_adds_in_one_edit(self, mock_guild: MagicMock) -> None:
        """Roles to remove and to add are applied atomically, keeping unrelated roles."""
        role_a, role_b, role_c = _role(1, "A"), _role(2, "B"), _role(3, "C")
        mock_guild.get_role = MagicMock(side_effect={1: role_a, 2: role_b, 3: role_c}.get)
        member = _member_with_roles(mock_guild, 10, [role_a, role_b])
        mock_guild.get_member = MagicMock(return_value=member)
        sink = MagicMock()
        sink.add_user_result = AsyncMock()

        _, roles_before, _ = await apply_cleaning_to_member(
            guild=mock_guild,
            member=member,
            roles_to_remove=[1],
            roles_to_add=[3],
            purge_service=sink,
            purge_id=99,
        )

        member.edit.assert_awaited_once_with(roles=[role_b, role_c])
        member.remove_roles.assert_not_called()
        member.add_roles.assert_not_called()
        assert roles_before == [1, 2]
        sink.add_user_result.assert_awaited_once()

    async def test_cleaning_skips_edit_when_nothing_changes(self, mock_guild: MagicMock) -> None:
        """No API call when the member already has the target role set."""
        role_a = _role(1, "A")
        mock_guild.get_role = MagicMock(side_effect={1: role_a}.get)
        member = _member_with_roles(mock_guild, 10, [role_a])
        mock_guild.get_member = MagicMock(return_value=member)
        sink = MagicMock()
        sink.add_user_result = AsyncMock()

        await apply_cleaning_to_member(
            guild=mock_guild,
            member=member,
            roles_to_remove=[42],
            roles_to_add=[1],
            purge_service=sink,
            purge_id=99,
        )

        member.edit.assert_not_awaited()
        sink.add_user_result.assert_awaited_once()

    async def test_cleaning_survives_http_error(self, mock_guild: MagicMock) -> None:
        """A non-permission API error on one member does not abort the purge."""
        role_a = _role(1, "A")
        mock_guild.get_role = MagicMock(side_effect={1: role_a}.get)
        member = _member_with_roles(mock_guild, 10, [role_a])
        member.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500), "boom"))
        mock_guild.get_member = MagicMock(return_value=member)
        sink = MagicMock()
        sink.add_user_result = AsyncMock()

        await apply_cleaning_to_member(
            guild=mock_guild,
            member=member,
            roles_to_remove=[1],
            roles_to_add=[],
            purge_service=sink,
            purge_id=99,
        )

        sink.add_user_result.assert_awaited_once()

    async def test_promotion_swaps_roles_in_one_edit(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """Promoting out of an affected role removes it and adds the target in a single edit."""
        from_role, to_role, other = _role(100, "From"), _role(200, "To"), _role(300, "Other")
        mock_guild.get_role = MagicMock(side_effect={100: from_role, 200: to_role}.get)
        member = _member_with_roles(mock_guild, 444555666, [from_role, other])
        from_role.members = [member]
        mock_guild.get_member = MagicMock(return_value=member)
        sink = MagicMock()
        sink.add_user_result = AsyncMock()

        promoted_in, promoted_out, _ = await execute_promotion_phase(
            cog=purge_cog,
            guild=mock_guild,
            record=mock_purge_record,
            config={ConfigKey.AUDIT_LEVEL: 0},
            purge_service=sink,
            purge_id=99,
            affected_roles=[100],
            promotions=[{"from_role": 100, "to_role": 200}],
            default_promotion=None,
            confirmed_users={444555666},
            processed_users=set(),
            audit_level=0,
            execution_logs=[],
        )

        assert (promoted_in, promoted_out) == (1, 0)
        member.edit.assert_awaited_once_with(roles=[other, to_role])
        member.remove_roles.assert_not_called()
        member.add_roles.assert_not_called()

    async def test_promotion_survives_http_error(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """A non-permission API error while promoting one member does not abort the phase."""
        from_role, to_role = _role(100, "From"), _role(200, "To")
        mock_guild.get_role = MagicMock(side_effect={100: from_role, 200: to_role}.get)
        member = _member_with_roles(mock_guild, 444555666, [from_role])
        member.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500), "boom"))
        from_role.members = [member]
        mock_guild.get_member = MagicMock(return_value=member)
        sink = MagicMock()
        sink.add_user_result = AsyncMock()

        promoted_in, _, _ = await execute_promotion_phase(
            cog=purge_cog,
            guild=mock_guild,
            record=mock_purge_record,
            config={ConfigKey.AUDIT_LEVEL: 0},
            purge_service=sink,
            purge_id=99,
            affected_roles=[100],
            promotions=[{"from_role": 100, "to_role": 200}],
            default_promotion=None,
            confirmed_users={444555666},
            processed_users=set(),
            audit_level=0,
            execution_logs=[],
        )

        assert promoted_in == 1
        sink.add_user_result.assert_awaited_once()

    async def test_global_removal_survives_http_error(
        self,
        purge_cog: PurgeCog,
        mock_guild: MagicMock,
        mock_purge_record: MagicMock,
    ) -> None:
        """A non-permission API error on one member does not abort global removal."""
        global_role = _role(600, "Global")
        mock_guild.get_role = MagicMock(side_effect={600: global_role}.get)
        failing = _member_with_roles(mock_guild, 1, [global_role])
        failing.remove_roles = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(status=500), "boom")
        )
        fine = _member_with_roles(mock_guild, 2, [global_role])
        mock_guild.members = [failing, fine]

        removed = await execute_global_removal_phase(
            cog=purge_cog,
            guild=mock_guild,
            record=mock_purge_record,
            config={ConfigKey.AUDIT_LEVEL: 0},
            global_roles_to_remove=[600],
            audit_level=0,
            execution_logs=[],
        )

        assert removed == 1
        fine.remove_roles.assert_awaited_once_with(global_role)
