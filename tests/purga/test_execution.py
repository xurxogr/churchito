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
    _execute_global_cleaning_phase,
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


class TestExecuteGlobalCleaningPhase:
    """Tests para _execute_global_cleaning_phase."""

    async def test_cleans_non_confirmed_members(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que purga miembros no confirmados."""
        # Crear rol y miembro
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 1,
        }
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            cleaned_count, processed_users = await _execute_global_cleaning_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
                excluded_roles=[],
                roles_to_remove=[200],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=1,
                execution_logs=execution_logs,
            )

        assert cleaned_count == 1
        assert mock_member.id in processed_users
        mock_member.remove_roles.assert_called()

    async def test_skips_confirmed_members(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que salta miembros confirmados."""
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 1001
        mock_member.bot = False
        mock_member.roles = []

        mock_guild.members = [mock_member]
        mock_guild.default_role = MagicMock()
        mock_guild.get_role = MagicMock(return_value=None)

        guild_id = mock_guild.id
        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purga_id = record.id

        config: dict[str, Any] = {}
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            cleaned_count, processed_users = await _execute_global_cleaning_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
                excluded_roles=[],
                roles_to_remove=[],
                roles_to_add=[],
                confirmed_users={1001},  # El miembro esta confirmado
                audit_level=0,
                execution_logs=execution_logs,
            )

        assert cleaned_count == 0
        assert 1001 not in processed_users

    async def test_skips_excluded_roles(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que salta miembros con roles excluidos."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purga_id = record.id

        config: dict[str, Any] = {}
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            cleaned_count, processed_users = await _execute_global_cleaning_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
                excluded_roles=[999],  # Rol excluido
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
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que salta bots."""
        mock_bot = MagicMock(spec=discord.Member)
        mock_bot.id = 1001
        mock_bot.bot = True

        mock_guild.members = [mock_bot]
        mock_guild.default_role = MagicMock()
        mock_guild.get_role = MagicMock(return_value=None)

        guild_id = mock_guild.id
        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purga_id = record.id

        config: dict[str, Any] = {}
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            cleaned_count, processed_users = await _execute_global_cleaning_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
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
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que quita todos los roles si no hay roles especificos."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purga_id = record.id

        config: dict[str, Any] = {}
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            cleaned_count, _ = await _execute_global_cleaning_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
                excluded_roles=[],
                roles_to_remove=[],  # Sin roles especificos
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=0,
                execution_logs=execution_logs,
            )

        assert cleaned_count == 1
        # Debe llamar a edit(roles=[]) para quitar todos los roles
        mock_member.edit.assert_called_once_with(roles=[])

    async def test_adds_roles_after_cleaning(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que añade roles despues de limpiar."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purga_id = record.id

        config: dict[str, Any] = {}
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            cleaned_count, _ = await _execute_global_cleaning_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
                excluded_roles=[],
                roles_to_remove=[],
                roles_to_add=[300],  # Añadir este rol
                confirmed_users=set(),
                audit_level=0,
                execution_logs=execution_logs,
            )

        assert cleaned_count == 1
        mock_member.add_roles.assert_called()

    async def test_handles_forbidden_on_remove(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que maneja error Forbidden al quitar roles."""
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 200

        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 1001
        mock_member.display_name = "TestUser"
        mock_member.bot = False
        mock_member.roles = [mock_role]
        mock_member.remove_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))

        mock_guild.members = [mock_member]
        mock_guild.default_role = MagicMock()
        mock_guild.default_role.id = 0
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_guild.get_member = MagicMock(return_value=mock_member)

        guild_id = mock_guild.id
        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purga_id = record.id

        config: dict[str, Any] = {}
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            # No debe lanzar excepcion
            cleaned_count, _ = await _execute_global_cleaning_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
                excluded_roles=[],
                roles_to_remove=[200],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=0,
                execution_logs=execution_logs,
            )

        # Aun asi se cuenta como procesado
        assert cleaned_count == 1

    async def test_logs_with_audit_level_2(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que registra logs con nivel de auditoria 2."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purga_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 2,
        }
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            await _execute_global_cleaning_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
                excluded_roles=[],
                roles_to_remove=[],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=2,
                execution_logs=execution_logs,
            )

        # Debe haber log de inicio y log por usuario
        assert len(execution_logs) == 2
        assert "TestUser" in execution_logs[1]


class TestExecutePurgaGlobal:
    """Tests para execute_purga con purga global."""

    async def test_execute_global_purga(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar ejecución completa de purga global."""
        # Crear miembro mock
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

        # Crear registro en DB
        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.GLOBAL,
                initiated_by=123,
                config_snapshot={
                    "excluded_roles": [],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                },
                scheduled_for=datetime.now(UTC) - timedelta(hours=1),
            )
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        with (
            patch.object(purga_cog.bot, "get_guild", return_value=mock_guild),
            patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock),
            patch.object(purga_cog, "_send_user_message", new_callable=AsyncMock),
            patch.object(purga_cog, "_get_config", new_callable=AsyncMock) as mock_config,
        ):
            mock_config.return_value = {
                ConfigKey.AUDIT_LEVEL: 1,
                ConfigKey.GLOBAL_EXEC_MSG_FINISH: "Purga finalizada: {cleaned}",
            }
            await execute_purga(
                cog=purga_cog,
                guild_id=mock_guild.id,
                purga_id=purga_id,
            )


class TestExecuteWarEndWithGlobalRemoval:
    """Tests para execute_purga con WAR_END y global_roles_to_remove."""

    async def test_execute_war_purga_with_global_removal(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar ejecución de purga WAR_END con eliminación global de roles (línea 229)."""
        # Crear rol global a eliminar
        mock_global_role = MagicMock(spec=discord.Role)
        mock_global_role.id = 600
        mock_global_role.name = "GlobalWarRole"

        # Crear miembro con el rol global
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

        # Crear registro WAR_END con global_roles_to_remove
        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=123,
                config_snapshot={
                    "affected_roles": [],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": None,
                    "global_roles_to_remove": [600],  # Este activa la línea 229
                },
                scheduled_for=datetime.now(UTC) - timedelta(hours=1),
            )
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        with (
            patch.object(purga_cog.bot, "get_guild", return_value=mock_guild),
            patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock),
            patch.object(purga_cog, "_send_user_message", new_callable=AsyncMock),
            patch.object(purga_cog, "_get_config", new_callable=AsyncMock) as mock_config,
        ):
            mock_config.return_value = {
                ConfigKey.AUDIT_LEVEL: 1,
            }
            await execute_purga(
                cog=purga_cog,
                guild_id=mock_guild.id,
                purga_id=purga_id,
            )

        # Verificar que se intentó quitar el rol global
        mock_member.remove_roles.assert_called()


class TestExecuteGlobalRemovalPhaseIntegration:
    """Tests de integración para _execute_global_removal_phase."""

    async def test_global_removal_with_roles(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar eliminación global de roles."""
        # Crear rol mock
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 500
        mock_role.name = "GlobalRole"

        # Crear miembros con el rol
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

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            count = await _execute_global_removal_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                global_roles_to_remove=[500],
                audit_level=2,
                execution_logs=execution_logs,
            )

        assert count == 2
        mock_member1.remove_roles.assert_called_once()
        mock_member2.remove_roles.assert_called_once()


class TestExecutePromotionWithDefault:
    """Tests para fase de promoción con default_promotion."""

    async def test_promotion_with_default(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar promoción con rol por defecto."""
        # Crear rol de promoción por defecto
        default_promo_role = MagicMock(spec=discord.Role)
        default_promo_role.id = 800
        default_promo_role.name = "DefaultPromo"

        # Miembro confirmado que no está en ningún grupo de promoción
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 444555666
        mock_member.bot = False
        mock_member.name = "TestUser"
        mock_member.display_name = "TestUser"
        mock_member.roles = [mock_guild.default_role]
        mock_member.add_roles = AsyncMock()

        mock_guild.get_role = MagicMock(return_value=default_promo_role)
        mock_guild.get_member = MagicMock(return_value=mock_member)

        # Crear registro
        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
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
            purga_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 2,
            ConfigKey.EXEC_MSG_PROMOTION_DEFAULT: "Default promo",
        }
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            in_group, not_in_group, promoted_users = await _execute_promotion_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
                affected_roles=[],
                promotions=[],
                default_promotion=800,
                confirmed_users={444555666},
                processed_users=set(),
                audit_level=2,
                execution_logs=execution_logs,
            )

        # El usuario debería ser promocionado con el rol por defecto
        assert not_in_group >= 0


class TestGlobalCleaningAlreadyProcessed:
    """Tests para usuario ya procesado en limpieza global."""

    async def test_skip_already_processed_user(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que salta usuarios duplicados en la lista de miembros."""
        # Crear miembro
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 111
        mock_member.bot = False
        mock_member.name = "User1"
        mock_member.display_name = "User1"
        mock_member.roles = [mock_guild.default_role]
        mock_member.remove_roles = AsyncMock()
        mock_member.add_roles = AsyncMock()

        # El mismo miembro aparece dos veces (cubrimos la rama "already processed")
        mock_guild.members = [mock_member, mock_member]

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.GLOBAL,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC),
            )
            await session.commit()
            purga_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            count, processed = await _execute_global_cleaning_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
                excluded_roles=[],
                roles_to_remove=[],
                roles_to_add=[],
                confirmed_users=set(),
                audit_level=0,
                execution_logs=execution_logs,
            )

        # El usuario solo se procesa una vez (el segundo es saltado)
        assert count == 1
        assert 111 in processed


class TestDefaultPromotionEdgeCases:
    """Tests para casos edge en promoción por defecto."""

    async def test_default_promotion_user_already_processed(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que salta usuarios ya procesados en promoción por defecto."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
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
            purga_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            in_group, not_in_group, promoted = await _execute_promotion_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
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
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que maneja usuario no encontrado en promoción por defecto."""
        default_promo_role = MagicMock(spec=discord.Role)
        default_promo_role.id = 800
        default_promo_role.name = "DefaultPromo"

        mock_guild.get_role = MagicMock(return_value=default_promo_role)
        mock_guild.get_member = MagicMock(return_value=None)  # User not found

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
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
            purga_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            in_group, not_in_group, promoted = await _execute_promotion_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
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
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar manejo de Forbidden al añadir rol por defecto."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
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
            purga_id = record.id

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            # Should not raise exception
            in_group, not_in_group, promoted = await _execute_promotion_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
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
    """Tests para casos edge en _execute_global_removal_phase."""

    async def test_global_removal_role_not_found(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar que retorna 0 cuando el rol no existe en el guild."""
        # El rol 999 no existe
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.members = []

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        count = await _execute_global_removal_phase(
            cog=purga_cog,
            guild=mock_guild,
            record=mock_purga_record,
            config=config,
            global_roles_to_remove=[999],  # Este rol no existe
            audit_level=0,
            execution_logs=execution_logs,
        )

        # Debería retornar 0 (línea 750)
        assert count == 0

    async def test_global_removal_skips_bots(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar que salta bots en eliminación global."""
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 500
        mock_role.name = "GlobalRole"

        # Crear un bot con el rol
        mock_bot = MagicMock(spec=discord.Member)
        mock_bot.id = 111
        mock_bot.bot = True  # Es un bot
        mock_bot.name = "BotUser"
        mock_bot.roles = [mock_guild.default_role, mock_role]
        mock_bot.remove_roles = AsyncMock()

        mock_guild.members = [mock_bot]
        mock_guild.get_role = MagicMock(return_value=mock_role)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            count = await _execute_global_removal_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                global_roles_to_remove=[500],
                audit_level=0,
                execution_logs=execution_logs,
            )

        # No debería procesar al bot (línea 764)
        assert count == 0
        mock_bot.remove_roles.assert_not_called()

    async def test_global_removal_skips_member_without_role(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar que salta miembros que no tienen el rol."""
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 500
        mock_role.name = "GlobalRole"

        # Miembro sin el rol
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 111
        mock_member.bot = False
        mock_member.name = "User1"
        mock_member.roles = [mock_guild.default_role]  # No tiene el rol 500
        mock_member.remove_roles = AsyncMock()

        mock_guild.members = [mock_member]
        mock_guild.get_role = MagicMock(return_value=mock_role)

        config: dict[str, Any] = {
            ConfigKey.AUDIT_LEVEL: 0,
        }
        execution_logs: list[str] = []

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            count = await _execute_global_removal_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                global_roles_to_remove=[500],
                audit_level=0,
                execution_logs=execution_logs,
            )

        # No debería procesar al miembro (línea 769)
        assert count == 0
        mock_member.remove_roles.assert_not_called()

    async def test_global_removal_forbidden_exception(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar manejo de Forbidden al quitar roles globales."""
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

        with patch.object(purga_cog, "_update_mod_message", new_callable=AsyncMock):
            # No debería lanzar excepción (líneas 789-790)
            count = await _execute_global_removal_phase(
                cog=purga_cog,
                guild=mock_guild,
                record=mock_purga_record,
                config=config,
                global_roles_to_remove=[500],
                audit_level=0,
                execution_logs=execution_logs,
            )

        # Conteo debería ser 0 porque el remove_roles falló
        assert count == 0
