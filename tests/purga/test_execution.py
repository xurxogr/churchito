"""Tests para discord_bot/purga/execution.py."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_bot.bot import DiscordBot
from discord_bot.common.services.database import DatabaseService
from discord_bot.purga.cog import PurgaCog
from discord_bot.purga.enums import ConfigKey, PurgaStatus, PurgaType
from discord_bot.purga.execution import (
    _execute_cleaning_phase,
    _execute_global_removal_phase,
    _execute_promotion_phase,
    execute_purga,
)
from discord_bot.purga.service import PurgaService


@pytest.fixture
def mock_discord_bot(test_database: DatabaseService) -> MagicMock:
    """Crear mock del bot con database."""
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
def purga_cog(mock_discord_bot: MagicMock) -> PurgaCog:
    """Crear instancia del cog para tests."""
    return PurgaCog(mock_discord_bot)


@pytest.fixture
def mock_guild() -> MagicMock:
    """Crear mock de un guild."""
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
def mock_purga_record() -> MagicMock:
    """Crear mock de un registro de purga."""
    record = MagicMock()
    record.id = 1
    record.guild_id = 123456789
    record.purga_type = PurgaType.WAR_END
    record.status = PurgaStatus.AUTHORIZED
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


class TestExecutePurga:
    """Tests para execute_purga."""

    async def test_execute_no_guild(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar ejecucion sin guild."""
        mock_discord_bot.get_guild = MagicMock(return_value=None)

        # No deberia lanzar excepcion
        await execute_purga(cog=purga_cog, guild_id=999, purga_id=1)

    async def test_execute_purga_not_found(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar ejecucion con purga no encontrada."""
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        # No deberia lanzar excepcion
        await execute_purga(cog=purga_cog, guild_id=mock_guild.id, purga_id=99999)

    async def test_execute_purga_not_authorized(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar ejecucion con purga no autorizada."""
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Estado es PENDING, no AUTHORIZED
            await session.commit()
            purga_id = record.id

        # No deberia lanzar excepcion
        await execute_purga(cog=purga_cog, guild_id=mock_guild.id, purga_id=purga_id)


class TestExecuteCleaningPhase:
    """Tests para _execute_cleaning_phase."""

    async def test_cleans_non_confirmed_members(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar limpieza de miembros no confirmados."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.flush()

            cleaned_count, processed_users = await _execute_cleaning_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purga_service=purga_service,
                purga_id=record.id,
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
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no limpia miembros confirmados."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.flush()

            cleaned_count, processed_users = await _execute_cleaning_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purga_service=purga_service,
                purga_id=record.id,
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
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar cuando el rol no existe."""
        mock_guild.get_role = MagicMock(return_value=None)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.flush()

            cleaned_count, processed_users = await _execute_cleaning_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purga_service=purga_service,
                purga_id=record.id,
                affected_roles=[100],
                roles_to_remove=[],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=0,
                execution_logs=[],
            )

            assert cleaned_count == 0


class TestExecutePromotionPhase:
    """Tests para _execute_promotion_phase."""

    async def test_promotes_confirmed_members(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar promoción de miembros confirmados."""
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
        member.remove_roles = AsyncMock()
        member.add_roles = AsyncMock()

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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.flush()

            promoted_in, promoted_out, promoted_users = await _execute_promotion_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purga_service=purga_service,
                purga_id=record.id,
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
            member.add_roles.assert_called_once_with(to_role)

    async def test_skips_unconfirmed_members(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no promociona miembros no confirmados."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.flush()

            promoted_in, promoted_out, promoted_users = await _execute_promotion_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purga_service=purga_service,
                purga_id=record.id,
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
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar promoción por defecto."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.flush()

            promoted_in, promoted_out, promoted_users = await _execute_promotion_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purga_service=purga_service,
                purga_id=record.id,
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
    """Tests para _execute_global_removal_phase."""

    async def test_removes_global_roles_from_members(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar eliminación de roles globales."""
        # Setup rol global a eliminar
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

        removed_count = await _execute_global_removal_phase(
            cog=purga_cog,
            guild=mock_guild,
            record=mock_purga_record,
            config=config,
            global_roles_to_remove=[500],
            audit_level=0,
            execution_logs=[],
        )

        assert removed_count == 1
        member.remove_roles.assert_called_once_with(global_role)

    async def test_skips_bots(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar que no afecta a bots."""
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

        removed_count = await _execute_global_removal_phase(
            cog=purga_cog,
            guild=mock_guild,
            record=mock_purga_record,
            config=config,
            global_roles_to_remove=[500],
            audit_level=0,
            execution_logs=[],
        )

        assert removed_count == 0

    async def test_skips_members_without_role(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar que no afecta a miembros sin el rol."""
        global_role = MagicMock(spec=discord.Role)
        global_role.id = 500
        global_role.name = "Global Role"

        member = MagicMock(spec=discord.Member)
        member.id = 111222333
        member.bot = False
        member.roles = []  # No tiene el rol

        mock_guild.members = [member]
        mock_guild.get_role = MagicMock(return_value=global_role)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }

        removed_count = await _execute_global_removal_phase(
            cog=purga_cog,
            guild=mock_guild,
            record=mock_purga_record,
            config=config,
            global_roles_to_remove=[500],
            audit_level=0,
            execution_logs=[],
        )

        assert removed_count == 0

    async def test_role_not_found(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar cuando el rol global no existe."""
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.members = []

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }

        removed_count = await _execute_global_removal_phase(
            cog=purga_cog,
            guild=mock_guild,
            record=mock_purga_record,
            config=config,
            global_roles_to_remove=[999],
            audit_level=0,
            execution_logs=[],
        )

        assert removed_count == 0

    async def test_handles_forbidden_error(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar manejo de error Forbidden."""
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

        # No debería lanzar excepción
        removed_count = await _execute_global_removal_phase(
            cog=purga_cog,
            guild=mock_guild,
            record=mock_purga_record,
            config=config,
            global_roles_to_remove=[500],
            audit_level=0,
            execution_logs=[],
        )

        assert removed_count == 0

    async def test_logs_with_audit_level_2(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar que genera logs con nivel de auditoría 2."""
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

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            removed_count = await _execute_global_removal_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                global_roles_to_remove=[500],
                audit_level=2,
                execution_logs=execution_logs,
            )

        assert removed_count == 1
        # Debe haber log de inicio y log por usuario
        assert len(execution_logs) == 2
        assert "Global Role" in execution_logs[1]
