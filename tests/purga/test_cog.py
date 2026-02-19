"""Tests para PurgaCog."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.database import DatabaseService
from discord_bot.purga.cog import PurgaCog
from discord_bot.purga.config import COG_NAME, PURGA_CONFIG_SCHEMA
from discord_bot.purga.enums import ConfigKey, PurgaStatus, PurgaType
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
    return guild


@pytest.fixture
def mock_member(mock_guild: MagicMock) -> MagicMock:
    """Crear mock de un miembro de Discord."""
    member = MagicMock(spec=discord.Member)
    member.id = 111222333
    member.bot = False
    member.display_name = "TestUser"
    member.nick = None
    member.guild = mock_guild
    member.guild_permissions = MagicMock()
    member.guild_permissions.manage_guild = True

    # Crear roles mock
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
    """Crear mock de una interaccion de Discord."""
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
def mock_purga_record() -> MagicMock:
    """Crear mock de un registro de purga."""
    record = MagicMock()
    record.id = 1
    record.guild_id = 123456789
    record.purga_type = PurgaType.WAR_END
    record.status = PurgaStatus.PENDING
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
    """Tests para get_config_schema."""

    def test_returns_schema(self, purga_cog: PurgaCog) -> None:
        """Probar que devuelve el esquema correcto."""
        schema = purga_cog.get_config_schema()
        assert schema == PURGA_CONFIG_SCHEMA
        assert schema.cog_name == "purga"


class TestIsCogEnabled:
    """Tests para _is_cog_enabled."""

    async def test_cog_enabled(self, purga_cog: PurgaCog, test_database: DatabaseService) -> None:
        """Probar cuando el cog esta habilitado."""
        guild_id = 123

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await session.commit()

        result = await purga_cog._is_cog_enabled(guild_id)
        assert result is True

    async def test_cog_disabled(self, purga_cog: PurgaCog, test_database: DatabaseService) -> None:
        """Probar cuando el cog esta deshabilitado."""
        guild_id = 456

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=guild_id, cog_name=COG_NAME, enabled=False
            )
            await session.commit()

        result = await purga_cog._is_cog_enabled(guild_id)
        assert result is False


class TestGetConfig:
    """Tests para _get_config."""

    async def test_returns_config_dict(
        self, purga_cog: PurgaCog, test_database: DatabaseService
    ) -> None:
        """Probar que devuelve un diccionario de configuracion."""
        guild_id = 123

        result = await purga_cog._get_config(guild_id)

        assert isinstance(result, dict)

    async def test_returns_saved_config(
        self, purga_cog: PurgaCog, test_database: DatabaseService
    ) -> None:
        """Probar que devuelve configuracion guardada."""
        guild_id = 789

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_CHANNEL, 123456)
            await session.commit()

        result = await purga_cog._get_config(guild_id)

        assert result.get(ConfigKey.MOD_CHANNEL) == 123456


class TestGetAvailablePurgaTypes:
    """Tests para _get_available_purga_types."""

    def test_war_complete_config(self, purga_cog: PurgaCog) -> None:
        """Probar configuracion completa para purga de guerra."""
        config: dict[str, Any] = {
            ConfigKey.MOD_CHANNEL: 123,
            ConfigKey.USER_CHANNEL: 456,
            ConfigKey.WAR_ADMIN_ROLES: [100],
            ConfigKey.WAR_AFFECTED_ROLES: [200],
        }

        result = purga_cog._get_available_purga_types(config)

        assert result["war"] is True
        assert result["global"] is False

    def test_global_complete_config(self, purga_cog: PurgaCog) -> None:
        """Probar configuracion completa para purga global."""
        config: dict[str, Any] = {
            ConfigKey.MOD_CHANNEL: 123,
            ConfigKey.USER_CHANNEL: 456,
            ConfigKey.GLOBAL_ADMIN_ROLES: [100],
        }

        result = purga_cog._get_available_purga_types(config)

        assert result["war"] is False
        assert result["global"] is True

    def test_both_complete_config(self, purga_cog: PurgaCog) -> None:
        """Probar configuracion completa para ambos tipos."""
        config: dict[str, Any] = {
            ConfigKey.MOD_CHANNEL: 123,
            ConfigKey.USER_CHANNEL: 456,
            ConfigKey.WAR_ADMIN_ROLES: [100],
            ConfigKey.WAR_AFFECTED_ROLES: [200],
            ConfigKey.GLOBAL_ADMIN_ROLES: [300],
        }

        result = purga_cog._get_available_purga_types(config)

        assert result["war"] is True
        assert result["global"] is True

    def test_missing_mod_channel(self, purga_cog: PurgaCog) -> None:
        """Probar sin canal de moderacion."""
        config: dict[str, Any] = {
            ConfigKey.USER_CHANNEL: 456,
            ConfigKey.WAR_ADMIN_ROLES: [100],
            ConfigKey.WAR_AFFECTED_ROLES: [200],
            ConfigKey.GLOBAL_ADMIN_ROLES: [300],
        }

        result = purga_cog._get_available_purga_types(config)

        assert result["war"] is False
        assert result["global"] is False

    def test_missing_user_channel(self, purga_cog: PurgaCog) -> None:
        """Probar sin canal de usuarios."""
        config: dict[str, Any] = {
            ConfigKey.MOD_CHANNEL: 123,
            ConfigKey.WAR_ADMIN_ROLES: [100],
            ConfigKey.WAR_AFFECTED_ROLES: [200],
            ConfigKey.GLOBAL_ADMIN_ROLES: [300],
        }

        result = purga_cog._get_available_purga_types(config)

        assert result["war"] is False
        assert result["global"] is False

    def test_war_missing_admin_roles(self, purga_cog: PurgaCog) -> None:
        """Probar guerra sin roles administradores."""
        config: dict[str, Any] = {
            ConfigKey.MOD_CHANNEL: 123,
            ConfigKey.USER_CHANNEL: 456,
            ConfigKey.WAR_AFFECTED_ROLES: [200],
        }

        result = purga_cog._get_available_purga_types(config)

        assert result["war"] is False
        assert result["global"] is False

    def test_war_missing_affected_roles(self, purga_cog: PurgaCog) -> None:
        """Probar guerra sin roles afectados."""
        config: dict[str, Any] = {
            ConfigKey.MOD_CHANNEL: 123,
            ConfigKey.USER_CHANNEL: 456,
            ConfigKey.WAR_ADMIN_ROLES: [100],
        }

        result = purga_cog._get_available_purga_types(config)

        assert result["war"] is False
        assert result["global"] is False

    def test_all_missing(self, purga_cog: PurgaCog) -> None:
        """Probar sin ninguna configuracion."""
        config: dict[str, Any] = {}

        result = purga_cog._get_available_purga_types(config)

        assert result["war"] is False
        assert result["global"] is False


class TestHandleWarPurge:
    """Tests para _handle_purge con PurgaType.WAR_END."""

    async def test_no_guild(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Probar sin guild."""
        mock_interaction.guild = None

        await purga_cog._handle_purge(mock_interaction, 3, PurgaType.WAR_END)

        mock_interaction.response.defer.assert_not_called()

    async def test_no_member(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Probar sin miembro (usuario no es Member)."""
        mock_interaction.user = MagicMock(spec=discord.User)  # No es Member

        await purga_cog._handle_purge(mock_interaction, 3, PurgaType.WAR_END)

        mock_interaction.response.defer.assert_not_called()

    async def test_no_permission(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar sin permisos."""
        guild_id = mock_interaction.guild.id

        # Usuario sin roles de admin
        mock_interaction.user.roles = []
        mock_interaction.user.guild_permissions.manage_guild = False

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [999])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_NO_PERMISSION_TEXT, "Sin permisos"
            )
            await session.commit()

        await purga_cog._handle_purge(mock_interaction, 3, PurgaType.WAR_END)

        mock_interaction.response.defer.assert_called_once()
        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "Sin permisos" in str(call_args)

    async def test_active_purge_exists(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar con purga activa existente."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        # Configurar permisos
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_ACTIVE_PURGE_TEXT, "Purga activa"
            )

            # Crear purga activa
            purga_service = PurgaService(session)
            await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=mock_member.id,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()

        await purga_cog._handle_purge(mock_interaction, 3, PurgaType.WAR_END)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "Purga activa" in str(call_args)


class TestHandleGlobalPurge:
    """Tests para _handle_purge con PurgaType.GLOBAL."""

    async def test_no_guild(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Probar sin guild."""
        mock_interaction.guild = None

        await purga_cog._handle_purge(mock_interaction, 3, PurgaType.GLOBAL)

        mock_interaction.response.defer.assert_not_called()

    async def test_no_member(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Probar sin miembro (usuario no es Member)."""
        mock_interaction.user = MagicMock(spec=discord.User)  # No es Member

        await purga_cog._handle_purge(mock_interaction, 3, PurgaType.GLOBAL)

        mock_interaction.response.defer.assert_not_called()

    async def test_no_permission(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar sin permisos."""
        guild_id = mock_interaction.guild.id

        # Usuario sin roles de admin
        mock_interaction.user.roles = []
        mock_interaction.user.guild_permissions.manage_guild = False

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.GLOBAL_ADMIN_ROLES, [999])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_NO_PERMISSION_TEXT, "Sin permisos"
            )
            await session.commit()

        await purga_cog._handle_purge(mock_interaction, 3, PurgaType.GLOBAL)

        mock_interaction.response.defer.assert_called_once()
        mock_interaction.followup.send.assert_called()

    async def test_active_purge_exists(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar cuando ya hay purga activa."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.GLOBAL_ADMIN_ROLES, [100])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_ACTIVE_PURGE_TEXT, "Purga activa"
            )

            # Crear purga activa
            purga_service = PurgaService(session)
            await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.GLOBAL,
                initiated_by=mock_member.id,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()

        await purga_cog._handle_purge(mock_interaction, 3, PurgaType.GLOBAL)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "Purga activa" in str(call_args)

    async def test_successful_purge_creation(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar creacion exitosa de purga global."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        # Configurar canal de moderacion
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

        await purga_cog._handle_purge(mock_interaction, 3, PurgaType.GLOBAL)

        mock_mod_channel.send.assert_called()
        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "iniciada" in str(call_args).lower()

    async def test_mod_channel_not_configured(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar cuando no hay canal de moderacion configurado."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.GLOBAL_ADMIN_ROLES, [100])
            # No configurar MOD_CHANNEL
            await session.commit()

        await purga_cog._handle_purge(mock_interaction, 3, PurgaType.GLOBAL)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "no configurado" in str(call_args).lower()

    async def test_mod_channel_not_found(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar cuando canal de moderacion no existe."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member
        mock_interaction.guild.get_channel = MagicMock(return_value=None)

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.GLOBAL_ADMIN_ROLES, [100])
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.MOD_CHANNEL, 456)
            await session.commit()

        await purga_cog._handle_purge(mock_interaction, 3, PurgaType.GLOBAL)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "no encontrado" in str(call_args).lower()

    async def test_auto_authorize_in_test_mode(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar auto-autorizacion en modo prueba."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        # Configurar canal de moderacion y usuarios
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

        await purga_cog._handle_purge(mock_interaction, 3, PurgaType.GLOBAL)

        # Debe haber enviado mensaje a usuarios (auto-autorizada)
        mock_user_channel.send.assert_called()


class TestRegisterGlobalCommand:
    """Tests para _register_purga_command con PurgaType.GLOBAL."""

    async def test_registers_command_with_complete_config(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que registra comando con config completa."""
        # Inicializar dict para el guild
        purga_cog._registered_commands[mock_guild.id] = {}

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
                mock_guild.id, COG_NAME, ConfigKey.GLOBAL_COMMAND_NAME, "purga_global"
            )
            await session.commit()

        config = await purga_cog._get_config(mock_guild.id)
        available = purga_cog._get_available_purga_types(config)

        await purga_cog._register_purga_command(
            mock_guild, config, PurgaType.GLOBAL, available["global"]
        )

        mock_discord_bot.tree.add_command.assert_called()
        assert purga_cog._registered_commands[mock_guild.id]["global"] == "purga_global"

    async def test_skips_when_config_incomplete(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no registra con config incompleta."""
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            # No configurar GLOBAL_ADMIN_ROLES
            await session.commit()

        config = await purga_cog._get_config(mock_guild.id)
        available = purga_cog._get_available_purga_types(config)

        await purga_cog._register_purga_command(
            mock_guild, config, PurgaType.GLOBAL, available["global"]
        )

        mock_discord_bot.tree.add_command.assert_not_called()

    async def test_removes_old_command_when_name_changed(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que elimina comando viejo cuando cambia el nombre."""
        # Registrar comando viejo
        purga_cog._registered_commands[mock_guild.id] = {"global": "old_global_command"}

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

        config = await purga_cog._get_config(mock_guild.id)
        available = purga_cog._get_available_purga_types(config)

        await purga_cog._register_purga_command(
            mock_guild, config, PurgaType.GLOBAL, available["global"]
        )

        # Verificar que se elimino el comando viejo
        mock_discord_bot.tree.remove_command.assert_called_with(
            "old_global_command", guild=mock_guild
        )
        # Verificar que se registro el nuevo
        mock_discord_bot.tree.add_command.assert_called()

    async def test_unregisters_when_config_becomes_incomplete(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que elimina comando cuando config se vuelve incompleta."""
        # Registrar comando existente
        purga_cog._registered_commands[mock_guild.id] = {"global": "purga_global"}

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            # No configurar GLOBAL_ADMIN_ROLES (config incompleta)
            await session.commit()

        config = await purga_cog._get_config(mock_guild.id)
        available = purga_cog._get_available_purga_types(config)

        await purga_cog._register_purga_command(
            mock_guild, config, PurgaType.GLOBAL, available["global"]
        )

        # Verificar que se elimino el comando
        mock_discord_bot.tree.remove_command.assert_called_with("purga_global", guild=mock_guild)
        assert "global" not in purga_cog._registered_commands.get(mock_guild.id, {})


class TestHandleAuthorize:
    """Tests para _handle_authorize."""

    async def test_no_guild(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Probar sin guild."""
        mock_interaction.guild = None

        await purga_cog._handle_authorize(mock_interaction, 1)

        mock_interaction.response.defer.assert_not_called()

    async def test_no_permission(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar sin permisos."""
        guild_id = mock_interaction.guild.id

        # Usuario sin roles de admin
        mock_interaction.user.roles = []
        mock_interaction.user.guild_permissions.manage_guild = False

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [999])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_NO_PERMISSION_TEXT, "Sin permisos"
            )
            await session.commit()

            # Crear purga de guerra para probar permisos
            purga_service = PurgaService(session)
            purga = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purga_id = purga.id

        await purga_cog._handle_authorize(mock_interaction, purga_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "Sin permisos" in str(call_args)

    async def test_purga_not_found(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar con purga inexistente."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await session.commit()

        await purga_cog._handle_authorize(mock_interaction, 99999)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "no encontrada" in str(call_args).lower()

    async def test_already_authorized(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar cuando el usuario ya autorizo."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])

            # Crear purga donde el usuario ya autorizo
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=mock_member.id,  # El iniciador auto-autoriza
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()

        await purga_cog._handle_authorize(mock_interaction, record.id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "ya has autorizado" in str(call_args).lower()


class TestHandleCancel:
    """Tests para _handle_cancel."""

    async def test_no_guild(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Probar sin guild."""
        mock_interaction.guild = None

        await purga_cog._handle_cancel(mock_interaction, 1)

        mock_interaction.response.defer.assert_not_called()

    async def test_no_permission(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar sin permisos."""
        guild_id = mock_interaction.guild.id

        # Usuario sin roles de admin
        mock_interaction.user.roles = []
        mock_interaction.user.guild_permissions.manage_guild = False

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [999])
            await config_service.set_value(
                guild_id, COG_NAME, ConfigKey.MOD_NO_PERMISSION_TEXT, "Sin permisos"
            )
            await session.commit()

            # Crear purga de guerra para probar permisos
            purga_service = PurgaService(session)
            purga = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=123,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purga_id = purga.id

        await purga_cog._handle_cancel(mock_interaction, purga_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "Sin permisos" in str(call_args)


class TestHandleConfirm:
    """Tests para _handle_confirm."""

    async def test_no_guild(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
    ) -> None:
        """Probar sin guild."""
        mock_interaction.guild = None

        await purga_cog._handle_confirm(mock_interaction, 1)

        mock_interaction.response.defer.assert_not_called()

    async def test_purga_not_found(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar con purga inexistente."""
        mock_interaction.user = mock_member

        await purga_cog._handle_confirm(mock_interaction, 99999)

        mock_interaction.response.send_message.assert_called()
        call_args = mock_interaction.response.send_message.call_args
        assert "no encontrada" in str(call_args).lower() or "no activa" in str(call_args).lower()


class TestRegisterGuildCommands:
    """Tests para _register_guild_commands."""

    async def test_skips_when_cog_disabled(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no registra comandos cuando el cog esta deshabilitado."""
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=False
            )
            await session.commit()

        await purga_cog._register_guild_commands(mock_guild)

        mock_discord_bot.tree.add_command.assert_not_called()

    async def test_skips_when_config_incomplete(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no registra comandos con config incompleta."""
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            # No configuramos los campos requeridos
            await session.commit()

        await purga_cog._register_guild_commands(mock_guild)

        mock_discord_bot.tree.add_command.assert_not_called()

    async def test_registers_command_with_complete_config(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que registra comandos con config completa."""
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

        await purga_cog._register_guild_commands(mock_guild)

        mock_discord_bot.tree.add_command.assert_called_once()


class TestUnregisterGuildCommands:
    """Tests para _unregister_guild_commands."""

    async def test_removes_registered_command(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar que elimina comandos registrados."""
        purga_cog._registered_commands[mock_guild.id] = {"war": "purga_guerra"}

        await purga_cog._unregister_guild_commands(mock_guild)

        mock_discord_bot.tree.remove_command.assert_called_once_with(
            "purga_guerra", guild=mock_guild
        )
        assert mock_guild.id not in purga_cog._registered_commands

    async def test_removes_multiple_registered_commands(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar que elimina multiples comandos registrados."""
        purga_cog._registered_commands[mock_guild.id] = {
            "war": "purga_guerra",
            "global": "purga_global",
        }

        await purga_cog._unregister_guild_commands(mock_guild)

        assert mock_discord_bot.tree.remove_command.call_count == 2
        assert mock_guild.id not in purga_cog._registered_commands

    async def test_does_nothing_when_no_command(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar que no hace nada si no hay comando registrado."""
        await purga_cog._unregister_guild_commands(mock_guild)

        mock_discord_bot.tree.remove_command.assert_not_called()


class TestCogLifecycle:
    """Tests para ciclo de vida del cog."""

    async def test_cog_unload_cancels_loop(
        self, purga_cog: PurgaCog, mock_discord_bot: MagicMock
    ) -> None:
        """Probar que cog_unload cancela el loop."""
        with patch.object(purga_cog.expiration_check_loop, "cancel") as mock_cancel:
            await purga_cog.cog_unload()
            mock_cancel.assert_called_once()


class TestSetupAndTeardown:
    """Tests para setup y teardown del cog."""

    async def test_setup_registers_schema_and_adds_cog(self, mock_discord_bot: MagicMock) -> None:
        """Probar que setup registra el schema y añade el cog."""
        from discord_bot.common.services.config_schema_service import (
            get_config_schema_service,
        )
        from discord_bot.purga.cog import setup
        from discord_bot.purga.config import PURGA_CONFIG_SCHEMA

        mock_discord_bot.add_cog = AsyncMock()

        await setup(mock_discord_bot)

        mock_discord_bot.add_cog.assert_called_once()
        # Verificar que el schema fue registrado
        schema = get_config_schema_service().get_schema("purga")
        assert schema == PURGA_CONFIG_SCHEMA

    async def test_teardown_unregisters_schema(self, mock_discord_bot: MagicMock) -> None:
        """Probar que teardown desregistra el schema."""
        from discord_bot.common.services.config_schema_service import (
            get_config_schema_service,
        )
        from discord_bot.purga.cog import setup, teardown

        mock_discord_bot.add_cog = AsyncMock()

        # Primero setup para registrar
        await setup(mock_discord_bot)
        assert get_config_schema_service().get_schema("purga") is not None

        # Luego teardown
        await teardown(mock_discord_bot)
        assert get_config_schema_service().get_schema("purga") is None


class TestHandleCancelExtended:
    """Tests extendidos para _handle_cancel."""

    async def test_purga_not_found(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar con purga inexistente."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])
            await session.commit()

        await purga_cog._handle_cancel(mock_interaction, 99999)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "no encontrada" in str(call_args).lower()

    async def test_purga_not_active(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar con purga que no esta activa."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Cambiar estado a cancelado
            await purga_service.update_status(record.id, PurgaStatus.CANCELLED)
            await session.commit()

        await purga_cog._handle_cancel(mock_interaction, record.id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "no puede ser cancelada" in str(call_args).lower()

    async def test_already_voted_cancel(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar cuando el usuario ya voto por cancelar."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
            await config_service.set_value(guild_id, COG_NAME, ConfigKey.WAR_ADMIN_ROLES, [100])

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Añadir voto de cancelacion del usuario
            await purga_service.add_cancellation(record.id, mock_member.id)
            await session.commit()

        await purga_cog._handle_cancel(mock_interaction, record.id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "ya has votado" in str(call_args).lower()


class TestHandleConfirmExtended:
    """Tests extendidos para _handle_confirm."""

    async def test_purga_not_authorized(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar con purga en estado pendiente (no autorizada)."""
        guild_id = mock_interaction.guild.id
        mock_interaction.user = mock_member

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Estado es PENDING por defecto
            await session.commit()

        await purga_cog._handle_confirm(mock_interaction, record.id)

        mock_interaction.response.send_message.assert_called()
        call_args = mock_interaction.response.send_message.call_args
        assert "no está activa" in str(call_args).lower()


class TestScheduleMessageDeletion:
    """Tests para _schedule_message_deletion."""

    def test_schedules_deletion(self, purga_cog: PurgaCog) -> None:
        """Probar que programa eliminacion."""
        purga_cog._schedule_message_deletion(channel_id=123, message_id=456, retention_minutes=30)

        assert (123, 456) in purga_cog._pending_deletions

    def test_does_not_schedule_when_retention_zero(self, purga_cog: PurgaCog) -> None:
        """Probar que no programa cuando retencion es 0."""
        purga_cog._schedule_message_deletion(channel_id=123, message_id=456, retention_minutes=0)

        assert (123, 456) not in purga_cog._pending_deletions


class TestCheckPendingDeletions:
    """Tests para _check_pending_deletions."""

    async def test_deletes_expired_messages(
        self, purga_cog: PurgaCog, mock_discord_bot: MagicMock
    ) -> None:
        """Probar que elimina mensajes expirados."""
        # Programar mensaje con tiempo pasado
        past_time = datetime.now(UTC) - timedelta(minutes=5)
        purga_cog._pending_deletions[(123, 456)] = past_time

        # Mock del canal y mensaje
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.delete = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_discord_bot.get_channel = MagicMock(return_value=mock_channel)

        await purga_cog._check_pending_deletions()

        assert (123, 456) not in purga_cog._pending_deletions
        mock_message.delete.assert_called_once()

    async def test_does_not_delete_future_messages(
        self, purga_cog: PurgaCog, mock_discord_bot: MagicMock
    ) -> None:
        """Probar que no elimina mensajes futuros."""
        # Programar mensaje con tiempo futuro
        future_time = datetime.now(UTC) + timedelta(minutes=30)
        purga_cog._pending_deletions[(123, 456)] = future_time

        await purga_cog._check_pending_deletions()

        assert (123, 456) in purga_cog._pending_deletions


class TestCheckExpiredPurgas:
    """Tests para _check_expired_purgas."""

    async def test_expires_pending_purga(
        self, purga_cog: PurgaCog, test_database: DatabaseService
    ) -> None:
        """Probar que expira purgas pendientes."""
        guild_id = 123

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
                expires_at=datetime.now(UTC) - timedelta(minutes=5),  # Ya expirado
            )
            await session.commit()
            purga_id = record.id

        # Registrar en tracking
        purga_cog._active_purgas[guild_id] = (
            purga_id,
            datetime.now(UTC) - timedelta(minutes=5),
        )

        await purga_cog._check_expired_purgas()

        # Verificar que se quito del tracking
        assert guild_id not in purga_cog._active_purgas


class TestCheckReadyPurgas:
    """Tests para _check_ready_purgas."""

    async def test_executes_ready_purga(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que ejecuta purgas listas."""
        guild_id = 123

        # Mock del guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test"
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [],
                    "test_mode": False,
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),  # Ya pasado
            )
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        # Registrar en tracking
        purga_cog._authorized_purgas[guild_id] = (
            purga_id,
            datetime.now(UTC) - timedelta(minutes=5),
        )

        with patch.object(purga_cog, "_execute_purga", new_callable=AsyncMock) as mock_exec:
            await purga_cog._check_ready_purgas()
            mock_exec.assert_called_once_with(guild_id=guild_id, purga_id=purga_id)

        # Verificar que se quito del tracking
        assert guild_id not in purga_cog._authorized_purgas


class TestExecutePurga:
    """Tests para _execute_purga."""

    async def test_execute_no_guild(self, purga_cog: PurgaCog, mock_discord_bot: MagicMock) -> None:
        """Probar ejecucion sin guild."""
        mock_discord_bot.get_guild = MagicMock(return_value=None)

        # No deberia lanzar excepcion
        await purga_cog._execute_purga(999, 1)

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
        await purga_cog._execute_purga(mock_guild.id, 99999)

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
        await purga_cog._execute_purga(mock_guild.id, purga_id)


class TestUpdateModMessage:
    """Tests para _update_mod_message."""

    async def test_updates_message(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar actualizacion de mensaje."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Test",
            ConfigKey.MOD_STATUS_PENDING: "Pendiente",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        await purga_cog._update_mod_message(
            guild=mock_guild, record=mock_purga_record, config=config
        )

        mock_message.edit.assert_called_once()

    async def test_handles_no_channel(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar cuando no hay canal."""
        mock_purga_record.mod_channel_id = None

        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Test",
            ConfigKey.MOD_STATUS_PENDING: "Pendiente",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        # No deberia lanzar excepcion
        await purga_cog._update_mod_message(
            guild=mock_guild, record=mock_purga_record, config=config
        )


class TestSendUserMessage:
    """Tests para _send_user_message."""

    async def test_sends_message(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar envio de mensaje a usuarios."""
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
            ConfigKey.USER_BUTTON_TEXT: "Confirmar",
            ConfigKey.WAR_AFFECTED_ROLES: [],
            ConfigKey.USER_REACTION_ROLE: None,
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

            await purga_cog._send_user_message(
                guild=mock_guild,
                record=record,
                config=config,
                session=session,
            )

            mock_channel.send.assert_called_once()


class TestOnGuildJoin:
    """Tests para on_guild_join."""

    async def test_registers_commands_on_join(
        self, purga_cog: PurgaCog, mock_guild: MagicMock
    ) -> None:
        """Probar que registra comandos al unirse a guild."""
        with patch.object(
            purga_cog, "_register_guild_commands", new_callable=AsyncMock
        ) as mock_register:
            await purga_cog.on_guild_join(mock_guild)
            mock_register.assert_called_once_with(mock_guild)


class TestOnConfigChanged:
    """Tests para on_config_changed."""

    async def test_triggers_resync_on_config_change(
        self, purga_cog: PurgaCog, mock_guild: MagicMock
    ) -> None:
        """Probar que dispara re-sincronizacion al cambiar config."""
        with patch.object(
            purga_cog, "_debounced_register_and_sync", new_callable=AsyncMock
        ) as mock_register:
            await purga_cog.on_config_changed(mock_guild, ConfigKey.WAR_COMMAND_NAME)
            mock_register.assert_called_once_with(mock_guild)


class TestOnCogToggled:
    """Tests para on_cog_toggled."""

    async def test_registers_commands_when_enabled(
        self, purga_cog: PurgaCog, mock_guild: MagicMock
    ) -> None:
        """Probar que registra comandos al habilitar cog."""
        with patch.object(
            purga_cog, "_register_guild_commands", new_callable=AsyncMock
        ) as mock_register:
            await purga_cog.on_cog_toggled(mock_guild, True)
            mock_register.assert_called_once_with(mock_guild)

    async def test_unregisters_commands_when_disabled(
        self, purga_cog: PurgaCog, mock_guild: MagicMock
    ) -> None:
        """Probar que elimina comandos al deshabilitar cog."""
        with patch.object(
            purga_cog, "_unregister_guild_commands", new_callable=AsyncMock
        ) as mock_unregister:
            await purga_cog.on_cog_toggled(mock_guild, False)
            mock_unregister.assert_called_once_with(mock_guild)


class TestRestoreActivePurgas:
    """Tests para _restore_active_purgas."""

    async def test_restores_pending_purgas(
        self, purga_cog: PurgaCog, test_database: DatabaseService
    ) -> None:
        """Probar restauracion de purgas pendientes."""
        guild_id = 123
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
                expires_at=expires_at,
            )
            await session.commit()

        await purga_cog._restore_active_purgas()

        assert guild_id in purga_cog._active_purgas

    async def test_restores_authorized_purgas(
        self, purga_cog: PurgaCog, test_database: DatabaseService
    ) -> None:
        """Probar restauracion de purgas autorizadas."""
        guild_id = 456
        scheduled_for = datetime.now(UTC) + timedelta(hours=2)

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=789,
                config_snapshot={},
                scheduled_for=scheduled_for,
            )
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()

        await purga_cog._restore_active_purgas()

        assert guild_id in purga_cog._authorized_purgas


class TestSyncGuildCommands:
    """Tests para _sync_guild_commands."""

    async def test_syncs_commands(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar sincronizacion de comandos."""
        await purga_cog._sync_guild_commands(mock_guild)
        mock_discord_bot.tree.sync.assert_called_once_with(guild=mock_guild)

    async def test_handles_sync_error(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar manejo de error en sincronizacion."""
        mock_discord_bot.tree.sync = AsyncMock(side_effect=Exception("Sync error"))

        # No deberia lanzar excepcion
        await purga_cog._sync_guild_commands(mock_guild)


class TestDebouncedRegisterAndSync:
    """Tests para _debounced_register_and_sync."""

    async def test_cancels_pending_sync(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
    ) -> None:
        """Probar que cancela sincronizacion pendiente."""
        import asyncio

        # Crear tarea pendiente mock
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.cancel = MagicMock()
        purga_cog._pending_syncs[mock_guild.id] = mock_task

        await purga_cog._debounced_register_and_sync(mock_guild)

        mock_task.cancel.assert_called_once()


class TestExpirationCheckLoop:
    """Tests para expiration_check_loop."""

    async def test_calls_all_check_methods(self, purga_cog: PurgaCog) -> None:
        """Probar que llama a todos los metodos de verificacion."""
        with (
            patch.object(
                purga_cog, "_check_expired_purgas", new_callable=AsyncMock
            ) as mock_expired,
            patch.object(purga_cog, "_check_ready_purgas", new_callable=AsyncMock) as mock_ready,
            patch.object(
                purga_cog, "_check_pending_deletions", new_callable=AsyncMock
            ) as mock_deletions,
        ):
            await purga_cog.expiration_check_loop()

            mock_expired.assert_called_once()
            mock_ready.assert_called_once()
            mock_deletions.assert_called_once()


class TestExecutePurgaExtended:
    """Tests extendidos para _execute_purga."""

    async def test_execute_with_full_config(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar ejecucion con configuracion completa."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        # Verificar que la purga se ejecuto
        async with test_database.session() as session:
            purga_service = PurgaService(session)
            updated_record = await purga_service.get_purga(purga_id)
            assert updated_record is not None
            assert updated_record.status == PurgaStatus.EXECUTED

    async def test_execute_with_test_mode(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar ejecucion en modo prueba."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={
                    "affected_roles": [],
                    "roles_to_remove": [],
                    "roles_to_add": [],
                    "promotions": [],
                    "default_promotion": None,
                    "test_mode": True,  # Modo prueba
                },
                scheduled_for=datetime.now(UTC) - timedelta(minutes=5),
            )
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            updated_record = await purga_service.get_purga(purga_id)
            assert updated_record is not None
            assert updated_record.status == PurgaStatus.EXECUTED


class TestOnInteraction:
    """Tests para on_interaction."""

    async def test_ignores_non_component_interaction(self, purga_cog: PurgaCog) -> None:
        """Probar que ignora interacciones no de componente."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.application_command

        # No deberia llamar a ningun handler
        with patch.object(purga_cog, "_handle_authorize", new_callable=AsyncMock) as mock_auth:
            await purga_cog.on_interaction(interaction)
            mock_auth.assert_not_called()

    async def test_handles_authorize_button(self, purga_cog: PurgaCog) -> None:
        """Probar manejo de boton de autorizar."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "purga:authorize:123"}

        with patch.object(purga_cog, "_handle_authorize", new_callable=AsyncMock) as mock_auth:
            await purga_cog.on_interaction(interaction)
            mock_auth.assert_called_once_with(interaction=interaction, purga_id=123)

    async def test_handles_cancel_button(self, purga_cog: PurgaCog) -> None:
        """Probar manejo de boton de cancelar."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "purga:cancel:456"}

        with patch.object(purga_cog, "_handle_cancel", new_callable=AsyncMock) as mock_cancel:
            await purga_cog.on_interaction(interaction)
            mock_cancel.assert_called_once_with(interaction=interaction, purga_id=456)

    async def test_handles_confirm_button(self, purga_cog: PurgaCog) -> None:
        """Probar manejo de boton de confirmar."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "purga:confirm:789"}

        with patch.object(purga_cog, "_handle_confirm", new_callable=AsyncMock) as mock_confirm:
            await purga_cog.on_interaction(interaction)
            mock_confirm.assert_called_once_with(interaction=interaction, purga_id=789)

    async def test_ignores_invalid_custom_id(self, purga_cog: PurgaCog) -> None:
        """Probar que ignora custom_id invalido."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "purga:authorize:invalid"}

        with patch.object(purga_cog, "_handle_authorize", new_callable=AsyncMock) as mock_auth:
            await purga_cog.on_interaction(interaction)
            mock_auth.assert_not_called()

    async def test_ignores_unknown_button(self, purga_cog: PurgaCog) -> None:
        """Probar que ignora boton desconocido."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "other:button:123"}

        with patch.object(purga_cog, "_handle_authorize", new_callable=AsyncMock) as mock_auth:
            await purga_cog.on_interaction(interaction)
            mock_auth.assert_not_called()


class TestOnConfigChangedExtended:
    """Tests extendidos para on_config_changed."""

    async def test_triggers_resync_on_essential_key(
        self, purga_cog: PurgaCog, mock_guild: MagicMock
    ) -> None:
        """Probar que dispara re-sincronizacion con clave esencial."""
        with patch.object(
            purga_cog, "_debounced_register_and_sync", new_callable=AsyncMock
        ) as mock_register:
            await purga_cog.on_config_changed(mock_guild, ConfigKey.WAR_COMMAND_NAME)
            mock_register.assert_called_once_with(mock_guild)

    async def test_ignores_non_essential_key(
        self, purga_cog: PurgaCog, mock_guild: MagicMock
    ) -> None:
        """Probar que ignora claves no esenciales."""
        with patch.object(
            purga_cog, "_debounced_register_and_sync", new_callable=AsyncMock
        ) as mock_register:
            await purga_cog.on_config_changed(mock_guild, ConfigKey.PURGE_HOUR)
            mock_register.assert_not_called()

    async def test_triggers_resync_on_global_command_name(
        self, purga_cog: PurgaCog, mock_guild: MagicMock
    ) -> None:
        """Probar que dispara re-sincronizacion con GLOBAL_COMMAND_NAME."""
        with patch.object(
            purga_cog, "_debounced_register_and_sync", new_callable=AsyncMock
        ) as mock_register:
            await purga_cog.on_config_changed(mock_guild, ConfigKey.GLOBAL_COMMAND_NAME)
            mock_register.assert_called_once_with(mock_guild)

    async def test_triggers_resync_on_global_admin_roles(
        self, purga_cog: PurgaCog, mock_guild: MagicMock
    ) -> None:
        """Probar que dispara re-sincronizacion con GLOBAL_ADMIN_ROLES."""
        with patch.object(
            purga_cog, "_debounced_register_and_sync", new_callable=AsyncMock
        ) as mock_register:
            await purga_cog.on_config_changed(mock_guild, ConfigKey.GLOBAL_ADMIN_ROLES)
            mock_register.assert_called_once_with(mock_guild)


class TestCheckPendingDeletionsExtended:
    """Tests extendidos para _check_pending_deletions."""

    async def test_handles_channel_not_found(
        self, purga_cog: PurgaCog, mock_discord_bot: MagicMock
    ) -> None:
        """Probar cuando el canal no existe."""
        past_time = datetime.now(UTC) - timedelta(minutes=5)
        purga_cog._pending_deletions[(123, 456)] = past_time

        mock_discord_bot.get_channel = MagicMock(return_value=None)

        await purga_cog._check_pending_deletions()

        # Should be removed from pending even if channel not found
        assert (123, 456) not in purga_cog._pending_deletions

    async def test_handles_message_not_found(
        self, purga_cog: PurgaCog, mock_discord_bot: MagicMock
    ) -> None:
        """Probar cuando el mensaje no existe."""
        past_time = datetime.now(UTC) - timedelta(minutes=5)
        purga_cog._pending_deletions[(123, 456)] = past_time

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )
        mock_discord_bot.get_channel = MagicMock(return_value=mock_channel)

        await purga_cog._check_pending_deletions()

        assert (123, 456) not in purga_cog._pending_deletions


class TestHandleAuthorizeExtended:
    """Tests extendidos para _handle_authorize."""

    async def test_authorize_adds_authorization(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que añade autorizacion correctamente."""
        guild_id = mock_interaction.guild.id
        # Usar otro usuario para que no sea el iniciador
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

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=mock_member.id,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purga_id = record.id

        await purga_cog._handle_authorize(mock_interaction, purga_id)

        # Verificar mensaje de confirmacion
        mock_interaction.followup.send.assert_called()

        # Verificar que se añadio la autorizacion
        async with test_database.session() as session:
            purga_service = PurgaService(session)
            updated = await purga_service.get_purga(purga_id)
            assert updated is not None
            assert other_member.id in updated.authorized_by


class TestHandleWarPurgeSuccess:
    """Tests para _handle_purge (WAR_END) con creacion exitosa."""

    async def test_successful_purge_creation(
        self,
        purga_cog: PurgaCog,
        test_database: DatabaseService,
    ) -> None:
        """Probar creacion exitosa de purga."""
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

        await purga_cog._handle_purge(mock_interaction, 5, PurgaType.WAR_END)

        mock_channel.send.assert_called_once()
        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "Purga iniciada" in str(call_args)

    async def test_purge_creation_without_mod_channel(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar error cuando no hay canal de moderacion."""
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
            # No configuramos MOD_CHANNEL
            await session.commit()

        await purga_cog._handle_purge(mock_interaction, 5, PurgaType.WAR_END)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "Canal de moderación no configurado" in str(call_args)

    async def test_purge_creation_auto_authorize_test_mode(
        self,
        purga_cog: PurgaCog,
        test_database: DatabaseService,
    ) -> None:
        """Probar auto-autorizacion en modo prueba (1 autorizacion suficiente)."""
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

        await purga_cog._handle_purge(mock_interaction, 5, PurgaType.WAR_END)

        # Deberia estar auto-autorizada
        assert guild_id in purga_cog._authorized_purgas


class TestHandleConfirmToggle:
    """Tests para _handle_confirm con toggle."""

    async def test_confirm_first_time(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar primera confirmacion."""
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
                guild_id, COG_NAME, ConfigKey.USER_FIRST_REACTION_TEXT, "Confirmado"
            )

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        await purga_cog._handle_confirm(mock_interaction, purga_id)

        mock_interaction.response.send_message.assert_called()
        call_args = mock_interaction.response.send_message.call_args
        assert "Confirmado" in str(call_args) or "confirmado" in str(call_args).lower()

        # Verificar que se añadio la confirmacion
        async with test_database.session() as session:
            purga_service = PurgaService(session)
            updated = await purga_service.get_purga(purga_id)
            assert updated is not None
            assert mock_member.id in updated.confirmed_by

    async def test_confirm_toggle_remove(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar retirar confirmacion (toggle)."""
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
                guild_id, COG_NAME, ConfigKey.USER_REMOVED_REACTION_TEXT, "Retirado"
            )

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            # Añadir confirmacion previa
            await purga_service.add_confirmation(record.id, mock_member.id)
            await session.commit()
            purga_id = record.id

        await purga_cog._handle_confirm(mock_interaction, purga_id)

        mock_interaction.response.send_message.assert_called()
        call_args = mock_interaction.response.send_message.call_args
        assert "Retirado" in str(call_args) or "retirad" in str(call_args).lower()

    async def test_confirm_with_role_assignment(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar confirmacion con asignacion de rol."""
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

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        await purga_cog._handle_confirm(mock_interaction, purga_id)

        mock_member.add_roles.assert_called_once_with(mock_role)


class TestHandleCancelExtendedFull:
    """Tests completos para _handle_cancel."""

    async def test_cancel_vote_added(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que se añade voto de cancelacion."""
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

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purga_id = record.id

        await purga_cog._handle_cancel(mock_interaction, purga_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "1/2" in str(call_args) or "añadido" in str(call_args).lower()

    async def test_cancel_completes_cancellation(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar cancelacion completa cuando hay suficientes votos."""
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

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await session.commit()
            purga_id = record.id

        await purga_cog._handle_cancel(mock_interaction, purga_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "cancelada" in str(call_args).lower()

        # Verificar estado
        async with test_database.session() as session:
            purga_service = PurgaService(session)
            updated = await purga_service.get_purga(purga_id)
            assert updated is not None
            assert updated.status == PurgaStatus.CANCELLED


class TestUpdateModMessageExtended:
    """Tests extendidos para _update_mod_message."""

    async def test_updates_with_view_for_pending(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar actualizacion con vista para estado pendiente."""
        channel_id = 123
        message_id = 456

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purga_service.update_mod_message(record.id, channel_id, message_id)
            await session.commit()

            # Refetch to get updated record
            refetched_record = await purga_service.get_purga(record.id)
            assert refetched_record is not None
            record = refetched_record

        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Test",
            ConfigKey.MOD_STATUS_PENDING: "Pendiente",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        await purga_cog._update_mod_message(guild=mock_guild, record=record, config=config)

        mock_message.edit.assert_called_once()
        # Verificar que se paso una vista
        call_kwargs = mock_message.edit.call_args.kwargs
        assert "view" in call_kwargs or "content" in call_kwargs

    async def test_removes_view_for_cancelled(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que elimina vista para estado cancelado."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purga_service.update_mod_message(record.id, 123, 456)
            await purga_service.update_status(record.id, PurgaStatus.CANCELLED)
            await session.flush()

            config: dict[str, Any] = {
                ConfigKey.MOD_MESSAGE_TEMPLATE: "Test",
                ConfigKey.MOD_STATUS_CANCELLED: "Cancelado",
                ConfigKey.MOD_REQUIRED_REACTIONS: 2,
            }

            await purga_cog._update_mod_message(guild=mock_guild, record=record, config=config)

            mock_message.edit.assert_called_once()
            call_kwargs = mock_message.edit.call_args.kwargs
            assert call_kwargs.get("view") is None


class TestExecutePurgaFullExecution:
    """Tests completos para _execute_purga con miembros."""

    async def test_execute_cleans_members(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar ejecucion que limpia miembros."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        # Verificar que se limpio el miembro
        member1.edit.assert_called()

    async def test_execute_with_promotions(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar ejecucion con promociones."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            # Add confirmation for member
            await purga_service.add_confirmation(record.id, 22222)
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        # Verificar promocion
        member1.add_roles.assert_called()


class TestSendUserMessageExtended:
    """Tests extendidos para _send_user_message."""

    async def test_send_user_message_updates_record(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que actualiza el registro con IDs del mensaje."""
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
            ConfigKey.USER_BUTTON_TEXT: "Confirmar",
            ConfigKey.WAR_AFFECTED_ROLES: [],
            ConfigKey.USER_REACTION_ROLE: None,
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

            await purga_cog._send_user_message(
                guild=mock_guild,
                record=record,
                config=config,
                session=session,
            )

            await session.flush()

            # Verificar que se actualizo el registro
            updated = await purga_service.get_purga(record.id)
            assert updated is not None
            assert updated.user_message_id == 456
            assert updated.user_channel_id == 123


class TestOnReady:
    """Tests para on_ready."""

    async def test_registers_commands_for_all_guilds(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar que registra comandos en todos los guilds."""
        guild1 = MagicMock(spec=discord.Guild)
        guild1.id = 111
        guild1.name = "Guild1"
        guild2 = MagicMock(spec=discord.Guild)
        guild2.id = 222
        guild2.name = "Guild2"
        mock_discord_bot.guilds = [guild1, guild2]

        with (
            patch.object(
                purga_cog, "_register_guild_commands", new_callable=AsyncMock
            ) as mock_register,
            patch.object(purga_cog, "_sync_guild_commands", new_callable=AsyncMock),
            patch.object(purga_cog, "_restore_active_purgas", new_callable=AsyncMock),
            patch.object(purga_cog, "_check_expired_purgas", new_callable=AsyncMock),
            patch.object(purga_cog.expiration_check_loop, "is_running", return_value=True),
        ):
            await purga_cog.on_ready()

            assert mock_register.call_count == 2

    async def test_handles_registration_error(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar manejo de error en registro."""
        guild1 = MagicMock(spec=discord.Guild)
        guild1.id = 111
        guild1.name = "Guild1"
        mock_discord_bot.guilds = [guild1]

        with (
            patch.object(
                purga_cog,
                "_register_guild_commands",
                new_callable=AsyncMock,
                side_effect=Exception("Test error"),
            ),
            patch.object(purga_cog, "_restore_active_purgas", new_callable=AsyncMock),
            patch.object(purga_cog, "_check_expired_purgas", new_callable=AsyncMock),
            patch.object(purga_cog.expiration_check_loop, "is_running", return_value=True),
        ):
            # No deberia lanzar excepcion
            await purga_cog.on_ready()

    async def test_starts_loop_if_not_running(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar que inicia el loop si no esta corriendo."""
        mock_discord_bot.guilds = []

        with (
            patch.object(purga_cog, "_restore_active_purgas", new_callable=AsyncMock),
            patch.object(purga_cog, "_check_expired_purgas", new_callable=AsyncMock),
            patch.object(purga_cog.expiration_check_loop, "is_running", return_value=False),
            patch.object(purga_cog.expiration_check_loop, "start") as mock_start,
        ):
            await purga_cog.on_ready()
            mock_start.assert_called_once()


class TestRestoreActivePurgasExtended:
    """Tests extendidos para _restore_active_purgas."""

    async def test_handles_exception(
        self, purga_cog: PurgaCog, mock_discord_bot: MagicMock
    ) -> None:
        """Probar manejo de excepcion."""
        # Make database.session raise an exception
        mock_discord_bot.database.session = MagicMock(side_effect=Exception("DB error"))

        # No deberia lanzar excepcion
        await purga_cog._restore_active_purgas()


class TestCheckExpiredPurgasExtended:
    """Tests extendidos para _check_expired_purgas."""

    async def test_handles_expiration_error(
        self, purga_cog: PurgaCog, test_database: DatabaseService
    ) -> None:
        """Probar manejo de error al expirar purga."""
        guild_id = 999

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
                expires_at=datetime.now(UTC) - timedelta(minutes=5),
            )
            await session.commit()
            purga_id = record.id

        purga_cog._active_purgas[guild_id] = (
            purga_id,
            datetime.now(UTC) - timedelta(minutes=5),
        )

        # Mock _get_config to raise an error
        with patch.object(
            purga_cog, "_get_config", new_callable=AsyncMock, side_effect=Exception("Config error")
        ):
            # No deberia lanzar excepcion
            await purga_cog._check_expired_purgas()


class TestCheckReadyPurgasExtended:
    """Tests extendidos para _check_ready_purgas."""

    async def test_handles_execution_error(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar manejo de error en ejecucion."""
        guild_id = 888

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.name = "Test"
        mock_discord_bot.get_guild = MagicMock(return_value=mock_guild)

        purga_cog._authorized_purgas[guild_id] = (
            1,
            datetime.now(UTC) - timedelta(minutes=5),
        )

        with patch.object(
            purga_cog, "_execute_purga", new_callable=AsyncMock, side_effect=Exception("Exec error")
        ):
            # No deberia lanzar excepcion
            await purga_cog._check_ready_purgas()

        # Deberia haberse quitado del tracking
        assert guild_id not in purga_cog._authorized_purgas


class TestHandleConfirmRoleRemoval:
    """Tests para _handle_confirm con remocion de rol."""

    async def test_confirm_toggle_with_role_removal(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar retirar confirmacion con rol asignado."""
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

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await purga_service.add_confirmation(record.id, mock_member.id)
            await session.commit()
            purga_id = record.id

        await purga_cog._handle_confirm(mock_interaction, purga_id)

        mock_member.remove_roles.assert_called_once_with(mock_role)


class TestHandleCancelWithReactionRole:
    """Tests para _handle_cancel con rol de reaccion."""

    async def test_cancel_removes_reaction_roles(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que cancelacion quita roles de reaccion."""
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

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Add confirmation
            await purga_service.add_confirmation(record.id, confirmed_user_id)
            await session.commit()
            purga_id = record.id

        await purga_cog._handle_cancel(mock_interaction, purga_id)

        # Verificar que se quito el rol
        confirmed_member.remove_roles.assert_called()


class TestRegisterGuildCommandsExtended:
    """Tests extendidos para _register_guild_commands."""

    async def test_removes_old_command_when_name_changed(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que elimina comando viejo cuando cambia el nombre."""
        # Registrar comando viejo
        purga_cog._registered_commands[mock_guild.id] = {"war": "old_command"}

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

        await purga_cog._register_guild_commands(mock_guild)

        # Verificar que se elimino el comando viejo
        mock_discord_bot.tree.remove_command.assert_called_with("old_command", guild=mock_guild)
        # Verificar que se registro el nuevo
        mock_discord_bot.tree.add_command.assert_called()

    async def test_skips_if_same_command_registered(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no re-registra si ya esta el mismo comando."""
        # Registrar comando con mismo nombre
        purga_cog._registered_commands[mock_guild.id] = {"war": "purga_guerra"}

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
            # Mismo nombre por defecto
            await session.commit()

        mock_discord_bot.tree.add_command.reset_mock()

        await purga_cog._register_guild_commands(mock_guild)

        # No deberia añadir comando nuevo
        mock_discord_bot.tree.add_command.assert_not_called()


class TestRegisterWhenDisabled:
    """Tests para _register_guild_commands cuando cog esta deshabilitado."""

    async def test_unregisters_when_cog_disabled(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que elimina comandos cuando cog esta deshabilitado."""
        # Registrar comando existente
        purga_cog._registered_commands[mock_guild.id] = {"war": "purga_guerra"}

        # No habilitar el cog (por defecto esta deshabilitado)
        await purga_cog._register_guild_commands(mock_guild)

        # Verificar que se elimino el comando
        mock_discord_bot.tree.remove_command.assert_called_with("purga_guerra", guild=mock_guild)
        assert mock_guild.id not in purga_cog._registered_commands

    async def test_unregisters_when_config_incomplete(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que elimina comandos cuando config esta incompleta."""
        # Registrar comando existente
        purga_cog._registered_commands[mock_guild.id] = {"war": "purga_guerra"}

        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=mock_guild.id, cog_name=COG_NAME, enabled=True
            )
            # Solo configurar parcialmente (sin WAR_AFFECTED_ROLES)
            await config_service.set_value(mock_guild.id, COG_NAME, ConfigKey.MOD_CHANNEL, 123)
            await session.commit()

        await purga_cog._register_guild_commands(mock_guild)

        # Verificar que se elimino el comando
        mock_discord_bot.tree.remove_command.assert_called()
        assert mock_guild.id not in purga_cog._registered_commands


class TestHandleWarPurgeModChannelNotFound:
    """Tests para _handle_purge (WAR_END) cuando mod_channel no existe."""

    async def test_mod_channel_not_found(
        self,
        purga_cog: PurgaCog,
        mock_interaction: MagicMock,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar error cuando canal de moderacion no existe."""
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

        await purga_cog._handle_purge(mock_interaction, 5, PurgaType.WAR_END)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "no encontrado" in str(call_args).lower()


class TestHandleAuthorizeRevertToPending:
    """Tests para _handle_authorize cuando se revierte a pendiente."""

    async def test_revert_to_pending_when_not_enough_auths(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar reversion a pendiente cuando no hay suficientes autorizaciones."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Ya tenia 2 autorizaciones y estaba autorizado
            # Simular estado autorizado con 2 autorizaciones
            await purga_service.add_authorization(record.id, 111)
            await purga_service.add_authorization(record.id, 222)
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        # Ahora el usuario añade una autorizacion (total 3)
        await purga_cog._handle_authorize(mock_interaction, purga_id)

        # Verificar que funciono
        mock_interaction.followup.send.assert_called()


class TestHandleAuthorizeNotActive:
    """Tests para _handle_authorize cuando purga no esta activa."""

    async def test_purga_not_active(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar error cuando purga no esta activa."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Cambiar a estado cancelado (no activa)
            await purga_service.update_status(record.id, PurgaStatus.CANCELLED)
            await session.commit()
            purga_id = record.id

        await purga_cog._handle_authorize(mock_interaction, purga_id)

        mock_interaction.followup.send.assert_called()
        call_args = mock_interaction.followup.send.call_args
        assert "no está activa" in str(call_args).lower()


class TestHandleConfirmNotAuthorized:
    """Tests para _handle_confirm cuando purga no esta autorizada."""

    async def test_purga_not_authorized(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar error cuando purga no esta autorizada."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            # Dejar en estado pendiente (no autorizada)
            await session.commit()
            purga_id = record.id

        await purga_cog._handle_confirm(mock_interaction, purga_id)

        mock_interaction.response.send_message.assert_called()
        call_args = mock_interaction.response.send_message.call_args
        assert "no está activa" in str(call_args).lower()


class TestHandleConfirmRoleForbidden:
    """Tests para _handle_confirm cuando hay errores de permisos."""

    async def test_add_role_forbidden(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar manejo de error Forbidden al añadir rol."""
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

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        # No deberia lanzar excepcion
        await purga_cog._handle_confirm(mock_interaction, purga_id)

        mock_interaction.response.send_message.assert_called()


class TestUpdateModMessageNotTextChannel:
    """Tests para _update_mod_message cuando canal no es TextChannel."""

    async def test_channel_not_text_channel(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no falla cuando canal no es TextChannel."""
        # Mock un canal que no es TextChannel
        mock_voice_channel = MagicMock(spec=discord.VoiceChannel)
        mock_guild.get_channel = MagicMock(return_value=mock_voice_channel)

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.mod_message_id = 12345
            record.mod_channel_id = 67890
            await session.commit()

            config: dict[str, Any] = {}
            # No deberia lanzar excepcion
            await purga_cog._update_mod_message(mock_guild, record, config)


class TestUpdateModMessageNotFound:
    """Tests para _update_mod_message cuando mensaje no existe."""

    async def test_message_not_found(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no falla cuando mensaje no existe."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.mod_message_id = 12345
            record.mod_channel_id = 67890
            await session.commit()

            config: dict[str, Any] = {}
            # No deberia lanzar excepcion
            await purga_cog._update_mod_message(mock_guild, record, config)


class TestCheckPendingDeletionsException:
    """Tests para _check_pending_deletions con excepciones."""

    async def test_handles_deletion_exception(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar manejo de excepcion al eliminar mensaje."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(side_effect=Exception("Unknown error"))
        mock_discord_bot.get_channel = MagicMock(return_value=mock_channel)

        # Programar eliminacion - key is tuple (channel_id, message_id), value is delete_at
        purga_cog._pending_deletions[(123, 456)] = datetime.now(UTC) - timedelta(minutes=1)

        # No deberia lanzar excepcion
        await purga_cog._check_pending_deletions()


class TestOnInteractionInvalidCustomId:
    """Tests para on_interaction con custom_id invalidos."""

    async def test_authorize_invalid_id(
        self,
        purga_cog: PurgaCog,
    ) -> None:
        """Probar custom_id invalido para authorize."""
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.type = discord.InteractionType.component
        mock_interaction.data = {"custom_id": "purga:authorize:invalid"}

        # No deberia lanzar excepcion
        await purga_cog.on_interaction(mock_interaction)

    async def test_cancel_invalid_id(
        self,
        purga_cog: PurgaCog,
    ) -> None:
        """Probar custom_id invalido para cancel."""
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.type = discord.InteractionType.component
        mock_interaction.data = {"custom_id": "purga:cancel:invalid"}

        # No deberia lanzar excepcion
        await purga_cog.on_interaction(mock_interaction)

    async def test_confirm_invalid_id(
        self,
        purga_cog: PurgaCog,
    ) -> None:
        """Probar custom_id invalido para confirm."""
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.type = discord.InteractionType.component
        mock_interaction.data = {"custom_id": "purga:confirm:invalid"}

        # No deberia lanzar excepcion
        await purga_cog.on_interaction(mock_interaction)


class TestOnCogToggledSync:
    """Tests para on_cog_toggled con sincronizacion."""

    async def test_syncs_when_enabled(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que sincroniza comandos cuando se habilita."""
        # Configurar para que se registre comando
        purga_cog._registered_commands[mock_guild.id] = {"war": "purga_guerra"}

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

        await purga_cog.on_cog_toggled(mock_guild, True)

        mock_discord_bot.tree.sync.assert_called()


class TestTeardown:
    """Tests para teardown."""

    async def test_unregisters_all_commands(
        self,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar que elimina todos los comandos registrados."""
        from discord_bot.purga.cog import teardown

        cog = PurgaCog(mock_discord_bot)
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
            side_effect=lambda gid: mock_guild1
            if gid == 111
            else mock_guild2
            if gid == 222
            else None
        )

        await teardown(mock_discord_bot)

        # Verificar que se eliminaron los comandos (1 de guild1 + 2 de guild2)
        assert mock_discord_bot.tree.remove_command.call_count == 3


class TestBeforeExpirationCheck:
    """Tests para before_expiration_check."""

    async def test_waits_until_ready(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar que espera a que el bot este listo."""
        await purga_cog.before_expiration_check()

        mock_discord_bot.wait_until_ready.assert_called_once()


class TestOnGuildJoinSync:
    """Tests para on_guild_join con sincronizacion."""

    async def test_syncs_if_registered(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que sincroniza si se registro comando."""
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

        await purga_cog.on_guild_join(mock_guild)

        mock_discord_bot.tree.sync.assert_called()


class TestExecutePurgaDefaultPromotion:
    """Tests para _execute_purga con promocion por defecto."""

    async def test_applies_default_promotion(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que aplica promocion por defecto a usuarios confirmados."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await purga_service.add_confirmation(record.id, 55555)
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        # Verificar que se aplico la promocion por defecto
        confirmed_member.add_roles.assert_called_with(default_role)


class TestExecutePurgaReactionRoleRemoval:
    """Tests para _execute_purga con remocion de rol de reaccion."""

    async def test_removes_reaction_role_after_execution(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que quita el rol de reaccion despues de ejecutar."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await purga_service.add_confirmation(record.id, 66666)
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        # Verificar que se quito el rol de reaccion
        confirmed_member.remove_roles.assert_called()


class TestExecutePurgaWithRolesToRemoveAndAdd:
    """Tests para _execute_purga con roles_to_remove y roles_to_add."""

    async def test_removes_and_adds_specific_roles(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que quita y añade roles especificos."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        # Verificar que se quitaron y añadieron los roles
        member.remove_roles.assert_called()
        member.add_roles.assert_called()


class TestExecutePurgaRoleForbidden:
    """Tests para _execute_purga con errores de permisos."""

    async def test_handles_forbidden_on_role_changes(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar manejo de error Forbidden en cambios de rol."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        # No deberia lanzar excepcion
        await purga_cog._execute_purga(guild_id, purga_id)


class TestCheckExpiredPurgasWithUpdate:
    """Tests para _check_expired_purgas con actualizacion de mensaje."""

    async def test_updates_mod_message_and_schedules_deletion(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que actualiza mensaje y programa eliminacion."""
        guild_id = 456456456

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_message.edit = AsyncMock()

        # Mock role para evitar error en _format_roles
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={"affected_roles": [100]},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
                expires_at=datetime.now(UTC) - timedelta(minutes=5),
            )
            record.mod_channel_id = 123
            record.mod_message_id = 456
            await session.commit()
            purga_id = record.id

        purga_cog._active_purgas[guild_id] = (
            purga_id,
            datetime.now(UTC) - timedelta(minutes=5),
        )

        await purga_cog._check_expired_purgas()

        # Verificar que se actualizo el mensaje
        mock_message.edit.assert_called()
        # Verificar que se programo eliminacion
        assert len(purga_cog._pending_deletions) > 0


class TestExecutePurgaWithRetentionDeletion:
    """Tests para _execute_purga con retencion y eliminacion."""

    async def test_deletes_user_message_after_execution(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que elimina mensaje de usuario y programa retencion."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            record.mod_channel_id = 123
            record.mod_message_id = 789
            record.user_channel_id = 456
            record.user_message_id = 111
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        # Verificar que se elimino mensaje de usuario
        mock_user_message.delete.assert_called()
        # Verificar que se programo retencion
        assert len(purga_cog._pending_deletions) > 0


class TestHandleCancelRemovesRoleForbidden:
    """Tests para _handle_cancel cuando falla quitar rol."""

    async def test_handles_forbidden_on_role_removal(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar manejo de Forbidden al quitar rol de reaccion."""
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

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purga_service.add_confirmation(record.id, confirmed_user_id)
            await session.commit()
            purga_id = record.id

        # No deberia lanzar excepcion
        await purga_cog._handle_cancel(mock_interaction, purga_id)

        # Se intento quitar el rol pero fallo
        confirmed_member.remove_roles.assert_called()


class TestUpdateModMessageCancelPending:
    """Tests para _update_mod_message con status CANCEL_PENDING."""

    async def test_updates_with_cancel_pending_status(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar actualizacion con status CANCEL_PENDING (sin view)."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_message.edit = AsyncMock()

        mock_guild.get_channel = MagicMock(return_value=mock_channel)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=None)

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.mod_message_id = 12345
            record.mod_channel_id = 67890
            record.status = PurgaStatus.FAILED
            await session.commit()

            config: dict[str, Any] = {}
            await purga_cog._update_mod_message(mock_guild, record, config)

        # Verificar que se llamo edit (sin view porque es estado terminal)
        mock_message.edit.assert_called()


class TestSendUserMessageNoChannel:
    """Tests para _send_user_message cuando canal no es TextChannel."""

    async def test_channel_not_text_channel(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no falla cuando canal no es TextChannel."""
        mock_voice = MagicMock(spec=discord.VoiceChannel)
        mock_guild.get_channel = MagicMock(return_value=mock_voice)

        config: dict[str, Any] = {
            ConfigKey.USER_CHANNEL: 123,
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

            # No deberia lanzar excepcion ni enviar mensaje
            await purga_cog._send_user_message(
                guild=mock_guild,
                record=record,
                config=config,
                session=session,
            )


class TestOnReadySyncsRegisteredGuilds:
    """Tests para on_ready sincronizando guilds con comandos registrados."""

    async def test_syncs_only_registered_guilds(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
    ) -> None:
        """Probar que solo sincroniza guilds con comandos registrados."""
        guild1 = MagicMock(spec=discord.Guild)
        guild1.id = 111
        guild1.name = "Guild1"
        guild2 = MagicMock(spec=discord.Guild)
        guild2.id = 222
        guild2.name = "Guild2"
        mock_discord_bot.guilds = [guild1, guild2]

        # Solo guild1 tiene comando registrado
        purga_cog._registered_commands[111] = {"war": "purga_guerra"}

        with (
            patch.object(purga_cog, "_register_guild_commands", new_callable=AsyncMock),
            patch.object(purga_cog, "_sync_guild_commands", new_callable=AsyncMock) as mock_sync,
            patch.object(purga_cog, "_restore_active_purgas", new_callable=AsyncMock),
            patch.object(purga_cog, "_check_expired_purgas", new_callable=AsyncMock),
            patch.object(purga_cog.expiration_check_loop, "is_running", return_value=True),
        ):
            await purga_cog.on_ready()

            # Solo deberia sincronizar guild1
            mock_sync.assert_called_once_with(guild1)


class TestExecutePurgaPromotionNotInAffected:
    """Tests para promociones fuera del grupo afectado."""

    async def test_promotion_not_in_affected_group(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar promocion de usuario que no esta en grupo afectado."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await purga_service.add_confirmation(record.id, 44444)
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        # Should be promoted but NOT have from_role removed (not in affected)
        member.add_roles.assert_called_with(to_role)
        # remove_roles should NOT have been called with from_role
        for call in member.remove_roles.call_args_list:
            assert from_role not in call.args


class TestExecutePurgaRemoveReactionRoleForbidden:
    """Tests para error al quitar rol de reaccion en ejecucion."""

    async def test_handles_forbidden_on_reaction_role_removal(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar manejo de Forbidden al quitar rol de reaccion."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await purga_service.add_confirmation(record.id, 33333)
            await session.commit()
            purga_id = record.id

        # No deberia lanzar excepcion
        await purga_cog._execute_purga(guild_id, purga_id)


class TestExecutePurgaPromotionForbidden:
    """Tests para error de permisos en promociones."""

    async def test_handles_forbidden_on_promotion(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar manejo de Forbidden al promocionar."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await purga_service.add_confirmation(record.id, 22222)
            await session.commit()
            purga_id = record.id

        # No deberia lanzar excepcion
        await purga_cog._execute_purga(guild_id, purga_id)


class TestHandleWarPurgeRequiredReactionsMinimum:
    """Tests para _handle_purge (WAR_END) con required_reactions < 2."""

    async def test_required_reactions_minimum_enforced(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que required_reactions tiene minimo 2 en modo normal."""
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

        await purga_cog._handle_purge(mock_interaction, 5, PurgaType.WAR_END)

        # Should have created purga but NOT auto-authorized (needs 2 not 1)
        mock_interaction.followup.send.assert_called()


class TestHandleAuthorizeTestModeExecTime:
    """Tests para _handle_authorize en modo prueba."""

    async def test_authorize_in_test_mode_short_exec_time(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que en modo prueba la ejecucion es en 2 minutos."""
        guild_id = 222444666
        second_user_id = 999111

        # Segundo usuario que autoriza
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=mock_member.id,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=5),
            )
            # First authorization from initiator
            await purga_service.add_authorization(record.id, mock_member.id)
            await session.commit()
            purga_id = record.id

        # Track before
        purga_cog._active_purgas[guild_id] = (purga_id, None)

        await purga_cog._handle_authorize(mock_interaction, purga_id)

        # Should be in authorized_purgas now
        assert guild_id in purga_cog._authorized_purgas


class TestHandleConfirmRemoveRoleForbidden:
    """Tests para _handle_confirm cuando remove_roles falla."""

    async def test_handles_forbidden_on_remove_role(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar manejo de Forbidden al quitar rol."""
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

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            # User already confirmed, now will toggle off
            await purga_service.add_confirmation(record.id, mock_member.id)
            await session.commit()
            purga_id = record.id

        # Should not raise - handles Forbidden gracefully
        await purga_cog._handle_confirm(mock_interaction, purga_id)
        mock_interaction.response.send_message.assert_called()


class TestHandleCancelDeletesUserMessage:
    """Tests para _handle_cancel eliminando mensaje de usuario."""

    async def test_deletes_user_message_on_cancel(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que cancela elimina mensaje de usuario."""
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

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.user_channel_id = 789
            record.user_message_id = 111
            await session.commit()
            purga_id = record.id

        await purga_cog._handle_cancel(mock_interaction, purga_id)

        # Should have deleted user message
        mock_user_message.delete.assert_called()


class TestExecutePurgaMemberAlreadyProcessed:
    """Tests para _execute_purga con miembro ya procesado."""

    async def test_skips_already_processed_member(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no procesa miembro dos veces."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        # Should only be processed once (member.edit called once)
        assert member.edit.call_count == 1


class TestExecutePurgaRoleNotFound:
    """Tests para _execute_purga cuando rol no existe."""

    async def test_skips_nonexistent_role(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que ignora roles que no existen."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        # Should complete without errors
        await purga_cog._execute_purga(guild_id, purga_id)


class TestExecutePurgaPromotionMemberNotConfirmed:
    """Tests para promociones con miembros no confirmados."""

    async def test_skips_unconfirmed_members_in_promotion(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no promociona miembros que no confirmaron."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            # NO confirmation added!
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        # Member should NOT have been promoted (no add_roles called)
        member.add_roles.assert_not_called()


class TestExecutePurgaPromotionMemberAlreadyPromoted:
    """Tests para promociones con miembros ya promocionados."""

    async def test_skips_already_promoted_member(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no promociona miembro dos veces."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await purga_service.add_confirmation(record.id, 55555)
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        # Should only be promoted once
        assert member.add_roles.call_count == 1


class TestDefaultPromotionAlreadyProcessed:
    """Tests para promocion por defecto con usuario ya procesado."""

    async def test_skips_already_promoted_in_default_promotion(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que no aplica promocion por defecto a usuario ya promocionado."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await purga_service.add_confirmation(record.id, 66666)
            await session.commit()
            purga_id = record.id

        await purga_cog._execute_purga(guild_id, purga_id)

        # Should have been promoted to to_role, NOT default_role
        # add_roles should be called once with to_role
        assert member.add_roles.call_count == 1
        member.add_roles.assert_called_with(to_role)


class TestExecutePurgaRemoveRolesForbidden:
    """Tests para error al quitar roles en ejecucion."""

    async def test_handles_forbidden_on_remove_specific_roles(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar manejo de Forbidden al quitar roles especificos."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        # Should not raise
        await purga_cog._execute_purga(guild_id, purga_id)


class TestExecutePurgaAddRolesForbidden:
    """Tests para error al añadir roles en ejecucion."""

    async def test_handles_forbidden_on_add_roles(
        self,
        purga_cog: PurgaCog,
        mock_discord_bot: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar manejo de Forbidden al añadir roles."""
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
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
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
            await purga_service.update_status(record.id, PurgaStatus.AUTHORIZED)
            await session.commit()
            purga_id = record.id

        # Should not raise
        await purga_cog._execute_purga(guild_id, purga_id)


class TestHandleCancelSchedulesDeletion:
    """Tests para _handle_cancel programando eliminacion de mensaje."""

    async def test_schedules_deletion_after_cancel(
        self,
        purga_cog: PurgaCog,
        mock_member: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar que programa eliminacion despues de cancelar."""
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

            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=guild_id,
                purga_type=PurgaType.WAR_END,
                initiated_by=999,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.mod_channel_id = 123
            record.mod_message_id = 456
            await session.commit()
            purga_id = record.id

        await purga_cog._handle_cancel(mock_interaction, purga_id)

        # Should have scheduled deletion
        assert len(purga_cog._pending_deletions) > 0


class TestUpdateModMessageCancelPendingBranch:
    """Tests para _update_mod_message rama CANCEL_PENDING (else branch)."""

    async def test_updates_without_view_for_cancel_pending(
        self,
        purga_cog: PurgaCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Probar actualizacion sin view para status CANCEL_PENDING."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_message.edit = AsyncMock()

        mock_guild.get_channel = MagicMock(return_value=mock_channel)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_member = MagicMock(return_value=None)

        async with test_database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.create_purga(
                guild_id=mock_guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=456,
                config_snapshot={},
                scheduled_for=datetime.now(UTC) + timedelta(days=3),
            )
            record.mod_message_id = 12345
            record.mod_channel_id = 67890
            # Set to CANCEL_PENDING - not terminal but not PENDING/AUTHORIZED
            record.status = PurgaStatus.CANCEL_PENDING
            await session.commit()

            config: dict[str, Any] = {}
            await purga_cog._update_mod_message(mock_guild, record, config)

        # Should call edit without view (line 1488)
        mock_message.edit.assert_called()
