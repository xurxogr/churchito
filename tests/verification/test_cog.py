"""Tests para VerificationCog."""

from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.database import DatabaseService
from discord_bot.common.utils import delete_message, has_any_role
from discord_bot.verification.cog import VerificationCog
from discord_bot.verification.enums import ConfigKey, VerificationStatus, VerificationType
from discord_bot.verification.service import VerificationService


class AsyncIteratorMock:
    """Mock for async iterators like channel.history()."""

    def __init__(self, items: list[Any]) -> None:  # noqa: D107
        self.items = items

    def __aiter__(self) -> "AsyncIteratorMock":  # noqa: D105
        self._index = 0
        return self

    async def __anext__(self) -> Any:  # noqa: D105
        if self._index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self._index]
        self._index += 1
        return item


@pytest.fixture
def mock_discord_bot(test_database: DatabaseService) -> MagicMock:
    """Crear mock del bot con database."""
    bot = MagicMock(spec=DiscordBot)
    bot.database = test_database
    bot.guilds = []
    bot.add_view = MagicMock()
    bot.get_guild = MagicMock(return_value=None)
    bot.wait_until_ready = AsyncMock()
    # Mock settings for verification API
    bot.settings = MagicMock()
    bot.settings.verification = MagicMock()
    bot.settings.verification.api_url = ""
    bot.settings.verification.api_key = ""
    bot.settings.verification.api_timeout = 30
    return bot


@pytest.fixture
def verification_cog(mock_discord_bot: MagicMock) -> VerificationCog:
    """Crear instancia del cog para tests."""
    cog = VerificationCog(mock_discord_bot)
    # Mock _is_cog_enabled to return True by default (cogs are disabled by default now)
    object.__setattr__(cog, "_is_cog_enabled", AsyncMock(return_value=True))
    return cog


class TestFormatMessage:
    """Tests para _format_message."""

    def test_format_all_placeholders(self, verification_cog: VerificationCog) -> None:
        """Probar reemplazo de todos los placeholders."""
        template = (
            "Hola {username}! Bienvenido a {server_name}. "
            "Tu verificacion ({verification_type}) fue {reason}. "
            "Mencion: {user_mention}"
        )

        result = verification_cog._format_message(
            template,
            username="TestUser",
            user_mention="<@123>",
            server_name="Mi Servidor",
            verification_type="Normal",
            reason="aprobada",
        )

        assert result == (
            "Hola TestUser! Bienvenido a Mi Servidor. "
            "Tu verificacion (Normal) fue aprobada. "
            "Mencion: <@123>"
        )

    def test_format_ally_type(self, verification_cog: VerificationCog) -> None:
        """Probar que verification_type se usa correctamente."""
        template = "Tipo: {verification_type}"
        result = verification_cog._format_message(template, verification_type="Aliado")
        assert result == "Tipo: Aliado"

    def test_format_regular_type(self, verification_cog: VerificationCog) -> None:
        """Probar que verification_type se usa correctamente."""
        template = "Tipo: {verification_type}"
        result = verification_cog._format_message(template, verification_type="Normal")
        assert result == "Tipo: Normal"

    def test_format_empty_placeholders(self, verification_cog: VerificationCog) -> None:
        """Probar con placeholder pasado como None."""
        template = "Usuario: {username}"
        result = verification_cog._format_message(template, username=None)
        assert result == "Usuario: "

    def test_format_unmatched_placeholder(self, verification_cog: VerificationCog) -> None:
        """Probar que placeholders no pasados se mantienen."""
        template = "Usuario: {username}"
        result = verification_cog._format_message(template)
        assert result == "Usuario: {username}"

    def test_format_no_placeholders(self, verification_cog: VerificationCog) -> None:
        """Probar mensaje sin placeholders."""
        template = "Mensaje simple sin placeholders"
        result = verification_cog._format_message(template)
        assert result == template

    def test_format_dynamic_kwargs(self, verification_cog: VerificationCog) -> None:
        """Probar que acepta cualquier placeholder dinamico."""
        template = "Estado: {status}, Moderador: {moderator}"
        result = verification_cog._format_message(template, status="Aprobado", moderator="Admin")
        assert result == "Estado: Aprobado, Moderador: Admin"


class TestHasAnyRole:
    """Tests para has_any_role utility."""

    def test_has_any_role_with_matching_role(self) -> None:
        """Probar con rol que coincide."""
        member = MagicMock(spec=discord.Member)
        role1 = MagicMock(spec=discord.Role)
        role1.id = 111
        role2 = MagicMock(spec=discord.Role)
        role2.id = 222
        member.roles = [role1, role2]

        result = has_any_role(member=member, role_ids=[222, 333])
        assert result is True

    def test_has_any_role_without_matching_role(self) -> None:
        """Probar sin rol que coincida."""
        member = MagicMock(spec=discord.Member)
        role1 = MagicMock(spec=discord.Role)
        role1.id = 111
        member.roles = [role1]

        result = has_any_role(member=member, role_ids=[222, 333])
        assert result is False

    def test_has_any_role_empty_list_with_permission(self) -> None:
        """Probar lista vacia - usa permisos de manage_guild."""
        member = MagicMock(spec=discord.Member)
        member.guild_permissions = MagicMock()
        member.guild_permissions.manage_guild = True

        result = has_any_role(member=member, role_ids=[])
        assert result is True

    def test_has_any_role_empty_list_without_permission(self) -> None:
        """Probar lista vacia sin permisos."""
        member = MagicMock(spec=discord.Member)
        member.guild_permissions = MagicMock()
        member.guild_permissions.manage_guild = False

        result = has_any_role(member=member, role_ids=[])
        assert result is False


class TestHandleVerificationStart:
    """Tests para handle_verification_start."""

    async def test_no_guild(self, verification_cog: VerificationCog) -> None:
        """Probar sin guild."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None

        await verification_cog.handle_verification_start(
            interaction=interaction, verification_type=VerificationType.REGULAR
        )

        # No deberia hacer nada
        interaction.response.defer.assert_not_called()

    async def test_already_pending(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar con verificacion ya pendiente."""
        # Crear solicitud pendiente usando la misma database que el cog
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()

        # Mock interaction
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.guild.name = "Test Guild"
        interaction.user = MagicMock(spec=discord.User)
        interaction.user.id = 456
        interaction.user.name = "TestUser"
        interaction.user.mention = "<@456>"
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = {
                "already_pending_message": "Ya tienes una solicitud pendiente.",
                "verification_type_regular_display": "Normal",
            }

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            interaction.followup.send.assert_called_once()
            call_args = interaction.followup.send.call_args
            assert "pendiente" in call_args[0][0].lower()

    async def test_pending_in_other_server(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar con verificacion pendiente en otro servidor."""
        # Crear solicitud pendiente en guild 111
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.create_request(
                guild_id=111,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()

        # Intentar verificar en guild 222
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 222  # Diferente guild
        interaction.guild.name = "Other Guild"
        interaction.user = MagicMock(spec=discord.User)
        interaction.user.id = 456  # Mismo usuario
        interaction.user.name = "TestUser"
        interaction.user.mention = "<@456>"
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = {
                "pending_in_other_server_message": "Tienes verificación en otro servidor.",
                "verification_type_regular_display": "Normal",
            }

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            interaction.followup.send.assert_called_once()
            call_args = interaction.followup.send.call_args
            assert "otro servidor" in call_args[0][0].lower()

    async def test_dm_disabled(self, verification_cog: VerificationCog) -> None:
        """Probar con DMs deshabilitados."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 999
        interaction.guild.name = "Test Guild"
        interaction.user = MagicMock(spec=discord.User)
        interaction.user.id = 888
        interaction.user.name = "TestUser"
        interaction.user.mention = "<@888>"
        interaction.user.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = {
                "already_pending_message": "Pendiente",
                "dm_instructions_message": "Instrucciones {username}",
                "dm_disabled_message": "DMs deshabilitados",
                "verification_type_regular_display": "Normal",
            }

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            interaction.followup.send.assert_called()
            call_args = interaction.followup.send.call_args
            assert "DMs deshabilitados" in str(call_args)


class TestHandleAccept:
    """Tests para handle_accept."""

    async def test_no_guild(self, verification_cog: VerificationCog) -> None:
        """Probar sin guild."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None

        await verification_cog.handle_accept(interaction=interaction, request_id=1)

        interaction.response.defer.assert_not_called()

    async def test_not_mod(self, verification_cog: VerificationCog) -> None:
        """Probar sin permisos de moderador."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = False
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = {"mod_roles": []}

            await verification_cog.handle_accept(interaction=interaction, request_id=1)

            interaction.response.send_message.assert_called_once()
            call_kwargs = interaction.response.send_message.call_args.kwargs
            assert "permisos" in call_kwargs["content"].lower()
            assert call_kwargs["ephemeral"] is True

    async def test_request_not_found(self, verification_cog: VerificationCog) -> None:
        """Probar con solicitud inexistente."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "Mod"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = {"mod_roles": []}

            await verification_cog.handle_accept(interaction=interaction, request_id=99999)

            interaction.followup.send.assert_called_once()
            call_args = interaction.followup.send.call_args
            assert "no encontrada" in call_args.kwargs["content"].lower()


class TestHandleReject:
    """Tests para handle_reject."""

    async def test_no_guild(self, verification_cog: VerificationCog) -> None:
        """Probar sin guild."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None

        await verification_cog.handle_reject(interaction=interaction, request_id=1, reason="motivo")

        interaction.response.defer.assert_not_called()

    async def test_not_mod(self, verification_cog: VerificationCog) -> None:
        """Probar sin permisos de moderador."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = False
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = {"mod_roles": []}

            await verification_cog.handle_reject(
                interaction=interaction, request_id=1, reason="motivo"
            )

            interaction.response.send_message.assert_called_once()
            call_kwargs = interaction.response.send_message.call_args.kwargs
            assert "permisos" in call_kwargs["content"].lower()
            assert call_kwargs["ephemeral"] is True


class TestShowRejectionSelect:
    """Tests para show_rejection_select."""

    async def test_no_guild(self, verification_cog: VerificationCog) -> None:
        """Probar sin guild."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await verification_cog.show_rejection_select(interaction=interaction, request_id=1)

        interaction.response.send_message.assert_not_called()

    async def test_with_configured_reasons(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar con motivos configurados."""
        # Crear solicitud en la base de datos
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        # Mock del rol de moderador
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        # Mock del usuario como Member con rol de mod
        mock_user = MagicMock(spec=discord.Member)
        mock_user.roles = [mock_role]

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [999],
            "rejection_reason_1": "Motivo 1",
            "rejection_reason_2": "Motivo 2",
            "rejection_reason_3": "",
            "rejection_reason_4": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.show_rejection_select(
                interaction=interaction, request_id=request_id
            )

            interaction.response.send_message.assert_called_once()
            call_kwargs = interaction.response.send_message.call_args[1]
            assert call_kwargs["ephemeral"] is True
            assert call_kwargs["view"] is not None

    async def test_with_no_configured_reasons(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar sin motivos configurados - usa defaults."""
        # Crear solicitud en la base de datos
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        # Mock del rol de moderador
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        # Mock del usuario como Member con rol de mod
        mock_user = MagicMock(spec=discord.Member)
        mock_user.roles = [mock_role]

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [999],
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.show_rejection_select(
                interaction=interaction, request_id=request_id
            )

            interaction.response.send_message.assert_called_once()

    async def test_shard_placeholder_replaced(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que el placeholder {shard} se reemplaza en REJECT_WRONG_SHARD."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()
            request_id = request.id

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        mock_user = MagicMock(spec=discord.Member)
        mock_user.roles = [mock_role]

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        config_values: dict[str, Any] = {
            "mod_roles": [999],
            "reject_wrong_shard": "Usuario en shard incorrecto (esperado: {shard})",
            "verification_shard": "ABLE",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.show_rejection_select(
                interaction=interaction, request_id=request_id
            )

            interaction.response.send_message.assert_called_once()
            call_kwargs = interaction.response.send_message.call_args[1]
            # Verificar que el view tiene las opciones con shard reemplazado
            view = call_kwargs["view"]
            assert view is not None

    async def test_shard_placeholder_skipped_when_no_shard_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que REJECT_WRONG_SHARD se omite si no hay shard configurado."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()
            request_id = request.id

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        mock_user = MagicMock(spec=discord.Member)
        mock_user.roles = [mock_role]

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        config_values: dict[str, Any] = {
            "mod_roles": [999],
            "reject_wrong_shard": "Usuario en shard incorrecto (esperado: {shard})",
            # No verification_shard configurado
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.show_rejection_select(
                interaction=interaction, request_id=request_id
            )

            # Debe funcionar sin error (el motivo se omite)
            interaction.response.send_message.assert_called_once()

    async def test_not_mod(self, verification_cog: VerificationCog) -> None:
        """Probar que usuario sin rol de mod no puede ver el selector."""
        # Mock del usuario sin rol de mod
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 111  # Rol distinto al de mod

        mock_user = MagicMock(spec=discord.Member)
        mock_user.roles = [mock_role]
        mock_user.guild_permissions = MagicMock()
        mock_user.guild_permissions.administrator = False

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [999],
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.show_rejection_select(interaction=interaction, request_id=1)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "No tienes permisos" in call_args[1]["content"]
            assert call_args[1]["ephemeral"] is True

    async def test_request_from_different_guild(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que rechaza solicitud de otro guild (seguridad cross-guild)."""
        # Crear solicitud en guild 999 (diferente al guild del interaction)
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=999,  # Guild diferente
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        # Mock del rol de moderador
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        # Mock del usuario como Member con rol de mod
        mock_user = MagicMock(spec=discord.Member)
        mock_user.roles = [mock_role]

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123  # Guild diferente al de la solicitud
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [999],
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.show_rejection_select(
                interaction=interaction, request_id=request_id
            )

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            # Debe rechazar como si no encontrara la solicitud
            assert "no encontrada" in call_args[1]["content"].lower()
            assert call_args[1]["ephemeral"] is True


class TestOnMemberRemove:
    """Tests para on_member_remove."""

    async def test_cancels_pending_verification(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que cancela verificaciones pendientes."""
        # Crear solicitud pendiente usando la misma database que el cog
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        # Simular que el usuario esta en pending_dm_verifications
        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Mock member
        member = MagicMock(spec=discord.Member)
        member.id = 456
        member.name = "TestUser"
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 123
        member.guild.name = "Test Guild"

        await verification_cog.on_member_remove(member)

        # Verificar que se elimino de pending
        assert 456 not in verification_cog._pending_dm_verifications

        # Verificar que se cancelo en la base de datos (nueva sesion)
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.CANCELLED

    async def test_no_pending_verification(self, verification_cog: VerificationCog) -> None:
        """Probar cuando no hay verificacion pendiente."""
        member = MagicMock(spec=discord.Member)
        member.id = 999
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 123

        # No deberia fallar
        await verification_cog.on_member_remove(member)

    async def test_updates_mod_message_on_leave(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que actualiza el mensaje de moderación cuando el usuario sale."""
        # Crear solicitud con mod_message_id
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)
            await session.commit()

        # Mock member con guild que tiene canal de moderación
        member = MagicMock(spec=discord.Member)
        member.id = 456
        member.name = "TestUser"
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 123
        member.guild.name = "Test Guild"

        # Mock canal de moderación
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [MagicMock(description="Test content\n⏳ Pendiente de revisión")]
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_message.edit = AsyncMock()
        member.guild.get_channel = MagicMock(return_value=mock_channel)

        # Mock la función update_mod_message_cancelled
        with patch("discord_bot.verification.cog.update_mod_message_cancelled") as mock_update:
            mock_update.return_value = None
            await verification_cog.on_member_remove(member)

            # Verificar que se llamó a update_mod_message_cancelled
            mock_update.assert_called_once()
            call_args = mock_update.call_args
            assert call_args[1]["guild"] == member.guild


class TestRestorePendingVerifications:
    """Tests para restauracion de verificaciones pendientes."""

    async def test_restore_pending_verifications(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que restaura verificaciones pendientes desde la DB."""
        # Crear verificaciones pendientes en la base de datos
        async with test_database.session() as session:
            service = VerificationService(session)
            request1 = await service.create_request(
                guild_id=111,
                user_id=456,
                username="User1",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            request2 = await service.create_request(
                guild_id=222,
                user_id=789,
                username="User2",
                guild_name="Test Guild",
                verification_type=VerificationType.ALLY,
            )
            await session.commit()
            request1_id = request1.id
            request2_id = request2.id

        # Limpiar estado en memoria
        verification_cog._pending_dm_verifications.clear()

        # Restaurar
        await verification_cog._restore_pending_verifications()

        # Verificar que se restauraron
        assert 456 in verification_cog._pending_dm_verifications
        assert 789 in verification_cog._pending_dm_verifications
        assert verification_cog._pending_dm_verifications[456] == (111, request1_id)
        assert verification_cog._pending_dm_verifications[789] == (222, request2_id)

    async def test_restore_ignores_pending_review(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que no restaura verificaciones en estado PENDING_REVIEW."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=111,
                user_id=456,
                username="User1",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            # Actualizar a PENDING_REVIEW
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()

        verification_cog._pending_dm_verifications.clear()
        await verification_cog._restore_pending_verifications()

        # No debe restaurar porque ya tiene capturas
        assert 456 not in verification_cog._pending_dm_verifications


class TestCleanupStaleVerifications:
    """Tests para limpieza de verificaciones obsoletas al iniciar."""

    async def test_cancels_verification_when_user_not_in_guild(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que cancela verificaciones si el usuario ya no está en el servidor."""
        # Crear solicitud pendiente
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)
            await session.commit()
            request_id = request.id

        # Añadir a pending_dm_verifications para verificar que se limpia
        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Mock guild sin el miembro
        mock_guild = MagicMock()
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = None  # Usuario no está
        mock_guild.get_channel.return_value = None  # Sin canal de mod
        verification_cog.bot.get_guild.return_value = mock_guild  # type: ignore[attr-defined]

        await verification_cog._cleanup_stale_verifications()

        # Verificar que se canceló en la base de datos
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.CANCELLED

        # Verificar que se limpió de memoria
        assert 456 not in verification_cog._pending_dm_verifications

    async def test_skips_verification_when_guild_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que ignora verificaciones si el guild no está disponible."""
        # Crear solicitud pendiente
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=999,  # Guild que no existe
                user_id=456,
                username="TestUser",
                guild_name="Unknown Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        # Bot no encuentra el guild
        verification_cog.bot.get_guild.return_value = None  # type: ignore[attr-defined]

        await verification_cog._cleanup_stale_verifications()

        # Verificar que NO se canceló (el guild no está disponible)
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_SCREENSHOTS

    async def test_skips_verification_when_user_still_in_guild(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que no cancela verificaciones si el usuario sigue en el servidor."""
        # Crear solicitud pendiente
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        # Mock guild con el miembro presente
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 456
        mock_guild = MagicMock()
        mock_guild.id = 123
        mock_guild.get_member.return_value = mock_member  # Usuario está
        verification_cog.bot.get_guild.return_value = mock_guild  # type: ignore[attr-defined]

        await verification_cog._cleanup_stale_verifications()

        # Verificar que NO se canceló
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_SCREENSHOTS

    async def test_handles_mod_message_update_error(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que continúa si falla la actualización del mensaje de mod."""
        # Crear solicitud pendiente
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)
            await session.commit()
            request_id = request.id

        # Mock guild sin el miembro
        mock_guild = MagicMock()
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = None
        mock_guild.get_channel.return_value = None
        verification_cog.bot.get_guild.return_value = mock_guild  # type: ignore[attr-defined]

        # Mock update_mod_message_cancelled para que falle
        with patch(
            "discord_bot.verification.cog.update_mod_message_cancelled",
            side_effect=Exception("Discord API error"),
        ):
            # No debe lanzar excepción
            await verification_cog._cleanup_stale_verifications()

        # Verificar que se canceló en la base de datos a pesar del error
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.CANCELLED


class TestInitializeTrackers:
    """Tests para inicialización de trackers al iniciar."""

    async def test_initializes_tracker_for_guild_with_pending(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que inicializa tracker para guilds con verificaciones pendientes."""
        # Crear solicitud pendiente y configuración
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            # Guardar configuración con mod_notification_channel
            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "mod_notification_channel", 888)
            await config_service.set_value(
                123, "verification", "tracker_title", "📋 Verificaciones Pendientes"
            )
            await session.commit()

        # Mock guild
        mock_tracker_message = MagicMock()
        mock_tracker_message.id = 9999

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.send = AsyncMock(return_value=mock_tracker_message)
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([]))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        verification_cog.bot.get_guild.return_value = mock_guild  # type: ignore[attr-defined]

        await verification_cog._initialize_trackers()

        # Verificar que se envió el mensaje del tracker
        mock_mod_channel.send.assert_called_once()

    async def test_skips_guild_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que ignora guilds no encontrados."""
        # Crear solicitud pendiente
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.create_request(
                guild_id=999,
                user_id=456,
                username="TestUser",
                guild_name="Unknown Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()

        # Bot no encuentra el guild
        verification_cog.bot.get_guild.return_value = None  # type: ignore[attr-defined]

        # No debe lanzar excepción
        await verification_cog._initialize_trackers()

    async def test_skips_disabled_cog(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que ignora guilds con cog deshabilitado."""
        # Crear solicitud pendiente
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        verification_cog.bot.get_guild.return_value = mock_guild  # type: ignore[attr-defined]

        # Cog deshabilitado
        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog._initialize_trackers()

            # No debe llamar a get_all_config (porque el cog está deshabilitado)
            mock_guild.get_channel.assert_not_called()

    async def test_no_pending_returns_early(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que retorna temprano si no hay verificaciones pendientes."""
        # Sin verificaciones pendientes

        # No debe lanzar excepción
        await verification_cog._initialize_trackers()


class TestOnMessage:
    """Tests para on_message (DM screenshots)."""

    async def test_ignores_guild_messages(self, verification_cog: VerificationCog) -> None:
        """Probar que ignora mensajes de guild."""
        message = MagicMock(spec=discord.Message)
        message.guild = MagicMock(spec=discord.Guild)

        await verification_cog.on_message(message)

        # No deberia procesar nada

    async def test_ignores_bot_messages(self, verification_cog: VerificationCog) -> None:
        """Probar que ignora mensajes de bots."""
        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = True

        await verification_cog.on_message(message)

    async def test_responds_to_user_without_pending(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que responde a usuarios sin verificacion pendiente."""
        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 999
        message.reply = AsyncMock()

        # Configurar mock del bot para que no encuentre servidor comun
        verification_cog.bot.guilds = []  # type: ignore[misc]

        # Mock para que no encuentre en base de datos
        with patch.object(
            verification_cog, "_get_pending_verification", new_callable=AsyncMock
        ) as mock_get_pending:
            mock_get_pending.return_value = None

            await verification_cog.on_message(message)

            # Debe responder con el mensaje por defecto
            message.reply.assert_called_once()
            args = message.reply.call_args[0]
            assert "No tienes ninguna verificación en curso" in args[0]

    async def test_responds_to_user_without_pending_with_config(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que responde con config de servidor comun."""
        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 999
        message.reply = AsyncMock()

        # Mock de servidor comun
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_member = MagicMock(return_value=MagicMock())
        verification_cog.bot.guilds = [mock_guild]  # type: ignore[misc]

        config_values = {
            "no_pending_verification_message": "Mensaje personalizado sin verificación",
        }

        with (
            patch.object(
                verification_cog, "_get_pending_verification", new_callable=AsyncMock
            ) as mock_get_pending,
            patch.object(
                verification_cog, "_is_cog_enabled", new_callable=AsyncMock
            ) as mock_enabled,
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
        ):
            mock_get_pending.return_value = None
            mock_enabled.return_value = True
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            message.reply.assert_called_once()
            args = message.reply.call_args[0]
            assert "Mensaje personalizado sin verificación" in args[0]

    async def test_no_response_when_forbidden(self, verification_cog: VerificationCog) -> None:
        """Probar que no falla si no puede responder al usuario."""
        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 999
        message.reply = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Forbidden"))

        verification_cog.bot.guilds = []  # type: ignore[misc]

        with patch.object(
            verification_cog, "_get_pending_verification", new_callable=AsyncMock
        ) as mock_get_pending:
            mock_get_pending.return_value = None

            # No deberia lanzar excepcion
            await verification_cog.on_message(message)

    async def test_restores_pending_from_database(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que restaura verificacion pendiente desde la base de datos."""
        # Crear verificacion pendiente en DB
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        # El usuario NO esta en _pending_dm_verifications
        assert 456 not in verification_cog._pending_dm_verifications

        # Buscar verificacion pendiente
        result = await verification_cog._get_pending_verification(456)

        # Debe encontrarla en la DB y restaurarla en memoria
        assert result is not None
        assert result == (123, request_id)
        assert 456 in verification_cog._pending_dm_verifications
        assert verification_cog._pending_dm_verifications[456] == (123, request_id)

    async def test_returns_memory_before_database(self, verification_cog: VerificationCog) -> None:
        """Probar que busca primero en memoria antes de ir a la DB."""
        # Agregar a memoria
        verification_cog._pending_dm_verifications[456] = (123, 999)

        # Buscar verificacion pendiente (no debe ir a la DB)
        result = await verification_cog._get_pending_verification(456)

        assert result == (123, 999)

    async def test_wrong_image_count(self, verification_cog: VerificationCog) -> None:
        """Probar con numero incorrecto de imagenes."""
        verification_cog._pending_dm_verifications[456] = (123, 1)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        # Solo 1 imagen
        attachment = MagicMock()
        attachment.content_type = "image/png"
        message.attachments = [attachment]

        config_values = {
            "wrong_images_message": "Debes enviar 2 imagenes",
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            message.channel.send.assert_called_once()
            # Usuario sigue en pending
            assert 456 in verification_cog._pending_dm_verifications

    async def test_non_image_attachments_ignored(self, verification_cog: VerificationCog) -> None:
        """Probar que adjuntos no-imagen son ignorados."""
        verification_cog._pending_dm_verifications[456] = (123, 1)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        # 2 archivos pero no son imagenes
        attachment1 = MagicMock()
        attachment1.content_type = "application/pdf"
        attachment2 = MagicMock()
        attachment2.content_type = "text/plain"
        message.attachments = [attachment1, attachment2]

        config_values = {
            "wrong_images_message": "Debes enviar 2 imagenes",
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            # Deberia pedir imagenes porque no detecto ninguna
            message.channel.send.assert_called_once()

    async def test_valid_screenshots_processed(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar procesamiento exitoso de capturas."""
        # Crear solicitud pendiente
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test Guild"
        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        # 2 imagenes validas
        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values = {
            "screenshots_received_message": "Capturas recibidas",
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            # Usuario removido de pending
            assert 456 not in verification_cog._pending_dm_verifications
            # Confirmacion enviada
            message.channel.send.assert_called()

        # Verificar estado en DB
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_REVIEW
            assert (
                updated.screenshot_1_url == "https://cdn.discordapp.com/attachments/123/456/1.png"
            )
            assert (
                updated.screenshot_2_url == "https://cdn.discordapp.com/attachments/123/456/2.jpg"
            )

    async def test_invalid_discord_url_rejected(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que URLs no de Discord CDN son rechazadas."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        # URLs de un dominio externo (no Discord CDN)
        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://example.com/image1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://example.com/image2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "wrong_images_message": "URLs inválidas",
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            # Se envió mensaje de error
            message.channel.send.assert_called_once()
            # Usuario sigue en pending (no se procesó)
            assert 456 in verification_cog._pending_dm_verifications

    async def test_auto_reject_on_api_422(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar auto-rechazo cuando la API devuelve 422 (imágenes inválidas)."""
        from discord_bot.verification.api_client import VerificationAPIResult
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            # Añadir mod_message_id para que se procese el auto-rechazo
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Mock mod message
        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        # Mock member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        # Mock mod channel (after guild so we can link them)
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        # Mock bot user
        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        # Mock settings con API configurada
        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,
            "reject_wrong_captures": "Capturas inválidas",
            "rejection_message": "Tu verificación fue rechazada: {reason}",
            "delete_processed_messages": True,
        }

        # Mock API devuelve 422
        api_result = VerificationAPIResult(
            success=False,
            status_code=422,
            error_message="Invalid images",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar estado en DB - debe estar rechazado
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.REJECTED
            assert updated.reviewed_by_username == "Auto"

    async def test_auto_approve_when_checks_pass(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar auto-aprobación cuando todas las verificaciones pasan."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Mock mod message
        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        # Mock role
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        # Mock member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        # Mock mod channel (after guild so we can link them)
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        # Mock bot user
        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Verificación aprobada",
            "delete_processed_messages": True,
        }

        # Mock API devuelve respuesta exitosa que pasa todas las verificaciones
        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",  # Sin regimiento
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar estado en DB - debe estar aprobado
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED
            assert updated.reviewed_by_username == "Auto"

    async def test_auto_reject_when_checks_fail(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar auto-rechazo cuando las verificaciones fallan (ej: tiene regimiento)."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Mock mod message
        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        # Mock member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        # Mock mod channel (after guild so we can link them)
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        # Mock bot user
        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "reject_has_regiment": "Ya perteneces a un regimiento",
            "rejection_message": "Tu verificación fue rechazada: {reason}",
            "delete_processed_messages": True,
        }

        # Mock API devuelve respuesta con regimiento (falla verificación para REGULAR)
        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="82DK",  # Tiene regimiento - debe rechazarse para REGULAR
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar estado en DB - debe estar rechazado
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.REJECTED
            assert updated.reviewed_by_username == "Auto"


class TestHandleAcceptHappyPath:
    """Tests para handle_accept flujo exitoso."""

    async def test_accept_approves_and_adds_roles(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar aprobacion exitosa con roles."""
        # Crear solicitud pendiente de revision
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request.id,
                "https://cdn.discordapp.com/attachments/123/456/1.png",
                "https://cdn.discordapp.com/attachments/123/456/2.png",
                "Test Guild",
            )
            await session.commit()
            request_id = request.id

        # Mock role
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        # Mock member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_guild.get_channel = MagicMock(return_value=None)

        # Mock interaction
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, request_id=request_id)

            # Rol agregado
            mock_member.add_roles.assert_called_once_with(mock_role)
            # DM enviado
            mock_member.send.assert_called_once()
            # Confirmacion
            interaction.followup.send.assert_called()

        # Verificar estado en DB
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED
            assert updated.reviewed_by_id == 789

    async def test_accept_already_processed(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar aprobacion de solicitud ya procesada."""
        # Crear solicitud ya aprobada
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await service.approve(
                request_id=request.id, reviewer_id=111, reviewer_username="OtherMod"
            )
            await session.commit()
            request_id = request.id

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, request_id=request_id)

            call_args = interaction.followup.send.call_args
            assert "ya fue procesada" in call_args.kwargs["content"].lower()


class TestHandleRejectHappyPath:
    """Tests para handle_reject flujo exitoso."""

    async def test_reject_updates_status_and_notifies(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar rechazo exitoso."""
        # Crear solicitud pendiente de revision
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()
            request_id = request.id

        # Mock member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "rejection_message": "Rechazado: {reason}",
            "mod_notification_channel": None,
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Aliado",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_reject(
                interaction=interaction, request_id=request_id, reason="Capturas invalidas"
            )

            # DM enviado con motivo
            mock_member.send.assert_called_once()
            sent_message = mock_member.send.call_args.kwargs["content"]
            assert "Capturas invalidas" in sent_message

        # Verificar estado en DB
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.REJECTED
            assert updated.rejection_reason == "Capturas invalidas"


class TestHealthCheck:
    """Tests para health check."""

    async def test_check_verification_message_no_channel(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar health check sin canal configurado (cog habilitado)."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        # Habilitar cog pero NO configurar canal
        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        # No deberia fallar - retorna temprano en linea 85
        await verification_cog._check_verification_message(mock_guild)

    async def test_check_verification_message_disabled(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar health check desactivado."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        # Configurar interval = 0
        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "health_check_interval", 0)
            await session.commit()

        # No deberia hacer nada
        await verification_cog._check_verification_message(mock_guild)

    async def test_run_health_check_iterates_guilds(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que health check itera sobre guilds."""
        mock_guild1 = MagicMock(spec=discord.Guild)
        mock_guild1.id = 111
        mock_guild2 = MagicMock(spec=discord.Guild)
        mock_guild2.id = 222

        object.__setattr__(verification_cog.bot, "guilds", [mock_guild1, mock_guild2])

        with (
            patch.object(
                verification_cog, "_get_health_check_interval", new_callable=AsyncMock
            ) as mock_interval,
            patch.object(
                verification_cog, "_check_verification_message", new_callable=AsyncMock
            ) as mock_check,
        ):
            mock_interval.return_value = 30  # Health check habilitado

            await verification_cog._run_health_check(force_all=True)

            assert mock_check.call_count == 2

    async def test_run_health_check_handles_exception(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que health check maneja excepciones por guild."""
        mock_guild1 = MagicMock(spec=discord.Guild)
        mock_guild1.id = 111
        mock_guild2 = MagicMock(spec=discord.Guild)
        mock_guild2.id = 222

        object.__setattr__(verification_cog.bot, "guilds", [mock_guild1, mock_guild2])

        with (
            patch.object(
                verification_cog, "_get_health_check_interval", new_callable=AsyncMock
            ) as mock_interval,
            patch.object(
                verification_cog, "_check_verification_message", new_callable=AsyncMock
            ) as mock_check,
        ):
            mock_interval.return_value = 30
            # Primer guild falla, segundo deberia continuar
            mock_check.side_effect = [Exception("Error"), None]

            await verification_cog._run_health_check(force_all=True)

            # Ambos fueron llamados
            assert mock_check.call_count == 2

    async def test_run_health_check_skips_disabled_guilds(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que health check omite guilds con intervalo 0."""
        mock_guild1 = MagicMock(spec=discord.Guild)
        mock_guild1.id = 111
        mock_guild2 = MagicMock(spec=discord.Guild)
        mock_guild2.id = 222

        object.__setattr__(verification_cog.bot, "guilds", [mock_guild1, mock_guild2])

        with (
            patch.object(
                verification_cog, "_get_health_check_interval", new_callable=AsyncMock
            ) as mock_interval,
            patch.object(
                verification_cog, "_check_verification_message", new_callable=AsyncMock
            ) as mock_check,
        ):
            # Guild 1 desactivado, Guild 2 activado
            mock_interval.side_effect = [0, 30]

            await verification_cog._run_health_check(force_all=True)

            # Solo guild 2 fue verificado
            assert mock_check.call_count == 1
            mock_check.assert_called_once_with(guild=mock_guild2)

    async def test_run_health_check_respects_interval(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que health check respeta el intervalo por guild."""
        from datetime import UTC, datetime, timedelta

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 111

        object.__setattr__(verification_cog.bot, "guilds", [mock_guild])

        with (
            patch.object(
                verification_cog, "_get_health_check_interval", new_callable=AsyncMock
            ) as mock_interval,
            patch.object(
                verification_cog, "_check_verification_message", new_callable=AsyncMock
            ) as mock_check,
        ):
            mock_interval.return_value = 30  # 30 minutos

            # Simular que se verifico hace 10 minutos
            verification_cog._last_health_check[111] = datetime.now(UTC) - timedelta(minutes=10)

            await verification_cog._run_health_check()

            # No deberia verificar (solo pasaron 10 de 30 minutos)
            assert mock_check.call_count == 0

            # Simular que se verifico hace 35 minutos
            verification_cog._last_health_check[111] = datetime.now(UTC) - timedelta(minutes=35)

            await verification_cog._run_health_check()

            # Ahora si deberia verificar
            assert mock_check.call_count == 1

    async def test_run_health_check_updates_last_check(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que health check actualiza el timestamp al verificar."""
        from datetime import datetime

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 111

        object.__setattr__(verification_cog.bot, "guilds", [mock_guild])

        with (
            patch.object(
                verification_cog, "_get_health_check_interval", new_callable=AsyncMock
            ) as mock_interval,
            patch.object(verification_cog, "_check_verification_message", new_callable=AsyncMock),
        ):
            mock_interval.return_value = 30

            # Sin timestamp previo
            assert 111 not in verification_cog._last_health_check

            await verification_cog._run_health_check(force_all=True)

            # Ahora debe tener timestamp
            assert 111 in verification_cog._last_health_check
            assert isinstance(verification_cog._last_health_check[111], datetime)

    async def test_get_health_check_interval_returns_configured_value(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que _get_health_check_interval retorna el valor configurado."""
        guild_id = 123

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id, "verification", True)
            await config_service.set_value(guild_id, "verification", "health_check_interval", 15)
            await session.commit()

        interval = await verification_cog._get_health_check_interval(guild_id)
        assert interval == 15

    async def test_get_health_check_interval_returns_default(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que _get_health_check_interval retorna 30 por defecto."""
        guild_id = 456

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id, "verification", True)
            await session.commit()

        interval = await verification_cog._get_health_check_interval(guild_id)
        assert interval == 30

    async def test_get_health_check_interval_returns_zero_when_disabled(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que _get_health_check_interval retorna 0 cuando cog deshabilitado."""
        guild_id = 789

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id, "verification", False)
            await session.commit()

        interval = await verification_cog._get_health_check_interval(guild_id)
        assert interval == 0

    async def test_check_verification_message_no_panel_message_id(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar health check sin panel message ID."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        # Configurar canal pero no panel message ID
        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await session.commit()

        await verification_cog._check_verification_message(mock_guild)

    async def test_check_verification_message_channel_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar health check con canal no encontrado."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=None)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await session.commit()

        # Debe retornar temprano con warning (lineas 89-90)
        await verification_cog._check_verification_message(mock_guild)

    async def test_check_verification_message_message_not_found_restores(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar health check restaura panel cuando mensaje no existe."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        with patch.object(
            verification_cog, "_create_verification_message", new_callable=AsyncMock
        ) as mock_create:
            await verification_cog._check_verification_message(mock_guild)
            mock_create.assert_called_once()

    async def test_check_verification_message_forbidden(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar health check con permisos denegados (lineas 167-168)."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Forbidden")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        # No deberia fallar - maneja Forbidden con warning (lineas 167-168)
        await verification_cog._check_verification_message(mock_guild)

    async def test_check_verification_message_no_components_restores(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar health check restaura panel sin botones."""
        mock_message = MagicMock()
        mock_message.components = []  # Sin componentes

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        with patch.object(
            verification_cog, "_create_verification_message", new_callable=AsyncMock
        ) as mock_create:
            await verification_cog._check_verification_message(mock_guild)
            mock_create.assert_called_once()

    async def test_check_verification_message_auto_creates_when_no_panel(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que se crea panel automaticamente si no existe."""
        mock_channel = MagicMock(spec=discord.TextChannel)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            # Solo canal configurado, sin panel existente
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await session.commit()

        with patch.object(
            verification_cog, "_create_verification_message", new_callable=AsyncMock
        ) as mock_create:
            await verification_cog._check_verification_message(mock_guild)
            mock_create.assert_called_once()

    async def test_check_verification_message_moves_when_channel_changes(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que mueve panel cuando cambia el canal."""
        # Canal viejo (donde estaba el panel)
        mock_old_channel = MagicMock(spec=discord.TextChannel)
        mock_old_channel.name = "old-verification"
        mock_old_message = MagicMock()
        mock_old_channel.fetch_message = AsyncMock(return_value=mock_old_message)
        mock_old_message.delete = AsyncMock()

        # Canal nuevo (donde debe ir el panel)
        mock_new_channel = MagicMock(spec=discord.TextChannel)
        mock_new_channel.name = "new-verification"

        def get_channel(channel_id: int) -> MagicMock | None:
            if channel_id == 111:
                return mock_old_channel
            if channel_id == 222:
                return mock_new_channel
            return None

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(side_effect=get_channel)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            # Canal configurado: 222 (nuevo)
            await config_service.set_value(123, "verification", "verification_channel", 222)
            # Panel existente en canal 111 (viejo)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        with patch.object(
            verification_cog, "_create_verification_message", new_callable=AsyncMock
        ) as mock_create:
            await verification_cog._check_verification_message(mock_guild)

            # Debe eliminar panel viejo
            mock_old_message.delete.assert_called_once()
            # Debe crear panel nuevo
            mock_create.assert_called_once()


class TestDeleteMessage:
    """Tests para delete_message utility."""

    async def test_delete_message_success(self) -> None:
        """Probar eliminacion exitosa de mensaje."""
        mock_message = MagicMock()
        mock_message.delete = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.name = "old-channel"
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        result = await delete_message(guild=mock_guild, channel_id=111, message_id=999)

        assert result is True
        mock_message.delete.assert_called_once()

    async def test_delete_message_channel_not_found(self) -> None:
        """Probar eliminacion cuando canal no existe."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=None)

        result = await delete_message(guild=mock_guild, channel_id=111, message_id=999)

        assert result is False

    async def test_delete_message_not_found(self) -> None:
        """Probar eliminacion cuando mensaje ya no existe."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        result = await delete_message(guild=mock_guild, channel_id=111, message_id=999)

        assert result is False

    async def test_delete_message_forbidden(self) -> None:
        """Probar eliminacion sin permisos."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Forbidden")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        result = await delete_message(guild=mock_guild, channel_id=111, message_id=999)

        assert result is False


class TestCreateVerificationMessage:
    """Tests para _create_verification_message."""

    async def test_create_verification_message_success(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar creacion exitosa de panel con canal de moderacion configurado."""
        mock_new_message = MagicMock()
        mock_new_message.id = 12345

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.name = "verification"
        mock_channel.send = AsyncMock(return_value=mock_new_message)

        # Mock del canal de moderacion
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 222

        # Mock de permisos del bot en el canal de moderacion
        mock_permissions = MagicMock()
        mock_permissions.send_messages = True
        mock_mod_channel.permissions_for = MagicMock(return_value=mock_permissions)

        # Mock del miembro del bot
        mock_bot_member = MagicMock(spec=discord.Member)
        mock_bot_member.id = 999

        # Configurar bot.user.id
        mock_user = MagicMock()
        mock_user.id = 999
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)
        mock_guild.get_member = MagicMock(return_value=mock_bot_member)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)

            # Configurar valores necesarios
            await config_service.set_value(123, "verification", "mod_notification_channel", 222)
            await config_service.set_value(123, "verification", "verify_button_text", "Verificar")
            await config_service.set_value(123, "verification", "verify_ally_button_text", "Aliado")
            await config_service.set_value(
                123, "verification", "verification_panel_message", "Bienvenido"
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()
            # Verificar que se envio con view (botones habilitados)
            call_kwargs = mock_channel.send.call_args.kwargs
            assert call_kwargs["view"] is not None

    async def test_create_verification_message_disabled_no_mod_channel(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar panel deshabilitado cuando no hay canal de moderacion."""
        mock_new_message = MagicMock()
        mock_new_message.id = 12345

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.name = "verification"
        mock_channel.send = AsyncMock(return_value=mock_new_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)

            # NO configurar mod_notification_channel
            await config_service.set_value(
                123,
                "verification",
                "verification_disabled_message",
                "La verificacion esta deshabilitada",
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()
            # Verificar que se envio sin view (botones deshabilitados)
            call_kwargs = mock_channel.send.call_args.kwargs
            assert "view" not in call_kwargs
            # El contenido ahora está en el embed
            assert "embed" in call_kwargs
            assert "deshabilitada" in call_kwargs["embed"].description

    async def test_create_verification_message_forbidden(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar creacion con permisos denegados en canal de verificacion."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Forbidden"))

        # Mock del canal de moderacion
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 222

        # Mock de permisos del bot
        mock_permissions = MagicMock()
        mock_permissions.send_messages = True
        mock_mod_channel.permissions_for = MagicMock(return_value=mock_permissions)

        # Mock del miembro del bot
        mock_bot_member = MagicMock(spec=discord.Member)
        mock_bot_member.id = 999

        # Configurar bot.user.id
        mock_user = MagicMock()
        mock_user.id = 999
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)
        mock_guild.get_member = MagicMock(return_value=mock_bot_member)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)

            # Configurar valores necesarios
            await config_service.set_value(123, "verification", "mod_notification_channel", 222)
            await config_service.set_value(123, "verification", "verify_button_text", "Verificar")
            await config_service.set_value(123, "verification", "verify_ally_button_text", "Aliado")
            await config_service.set_value(
                123, "verification", "verification_panel_message", "Bienvenido"
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            # No deberia fallar
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

    async def test_create_verification_message_with_embed_and_view(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar creacion de panel con embed e imagen (linea 227)."""
        mock_new_message = MagicMock()
        mock_new_message.id = 12345

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.name = "verification"
        mock_channel.send = AsyncMock(return_value=mock_new_message)

        # Mock del canal de moderacion
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 222

        # Mock de permisos del bot en el canal de moderacion
        mock_permissions = MagicMock()
        mock_permissions.send_messages = True
        mock_mod_channel.permissions_for = MagicMock(return_value=mock_permissions)

        # Mock del miembro del bot
        mock_bot_member = MagicMock(spec=discord.Member)
        mock_bot_member.id = 999

        # Configurar bot.user.id
        mock_user = MagicMock()
        mock_user.id = 999
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)
        mock_guild.get_member = MagicMock(return_value=mock_bot_member)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)

            # Configurar con URL de imagen para crear embed
            await config_service.set_value(123, "verification", "mod_notification_channel", 222)
            await config_service.set_value(123, "verification", "verify_button_text", "Verificar")
            await config_service.set_value(123, "verification", "verify_ally_button_text", "Aliado")
            await config_service.set_value(
                123,
                "verification",
                "verification_panel_message",
                "Bienvenido\nhttps://example.com/image.png",
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()
            # Verificar que se envio con embed y view
            call_kwargs = mock_channel.send.call_args.kwargs
            assert "embed" in call_kwargs
            assert call_kwargs["view"] is not None

    async def test_create_verification_message_with_embed_only(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar creacion de panel con embed sin botones (linea 229)."""
        mock_new_message = MagicMock()
        mock_new_message.id = 12345

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.name = "verification"
        mock_channel.send = AsyncMock(return_value=mock_new_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        # Sin canal de moderacion configurado

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)

            # NO configurar mod_notification_channel (deshabilitado)
            # Pero SI poner URL de imagen para crear embed
            await config_service.set_value(
                123,
                "verification",
                "verification_disabled_message",
                "Verificacion deshabilitada\nhttps://example.com/image.png",
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()
            # Verificar que se envio solo con embed (sin view)
            call_kwargs = mock_channel.send.call_args.kwargs
            assert "embed" in call_kwargs
            assert "view" not in call_kwargs or call_kwargs.get("view") is None


class TestHandleVerificationStartHappyPath:
    """Tests para handle_verification_start flujo exitoso."""

    async def test_starts_verification_successfully(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar inicio exitoso de verificacion."""
        # Mock mod channel
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_channel.send = AsyncMock(return_value=mock_mod_message)

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        # Mock user
        mock_user = MagicMock(spec=discord.User)
        mock_user.id = 456
        mock_user.name = "NewUser"
        mock_user.mention = "<@456>"
        mock_user.send = AsyncMock()

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "already_pending_message": "Pendiente",
            "dm_instructions_message": "Instrucciones para {username}",
            "mod_notification_channel": 888,
            "mod_message_template": "Nueva verificacion de {username}",
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Aliado",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            # DM enviado
            mock_user.send.assert_called_once()
            # Mensaje a mods enviado (+ tracker message)
            assert mock_mod_channel.send.call_count >= 1
            # Confirmacion
            interaction.followup.send.assert_called()

        # Verificar que se creo la solicitud
        async with test_database.session() as session:
            service = VerificationService(session)
            pending = await service.get_pending_by_user(123, 456)
            assert pending is not None
            assert pending.status == VerificationStatus.PENDING_SCREENSHOTS


class TestRoleOperations:
    """Tests para operaciones de roles."""

    async def test_accept_role_add_forbidden(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar aprobacion cuando agregar rol falla."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()
            request_id = request.id

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Forbidden"))
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            # No deberia fallar aunque el rol falle
            await verification_cog.handle_accept(interaction=interaction, request_id=request_id)

            interaction.followup.send.assert_called()

    async def test_accept_role_remove_forbidden(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar aprobacion cuando quitar rol falla."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()
            request_id = request.id

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Forbidden")
        )
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [999],
            "approval_message_regular": "Aprobado!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, request_id=request_id)

            interaction.followup.send.assert_called()

    async def test_accept_dm_forbidden(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar aprobacion cuando DM falla."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()
            request_id = request.id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Forbidden"))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            # No deberia fallar
            await verification_cog.handle_accept(interaction=interaction, request_id=request_id)

            interaction.followup.send.assert_called()


class TestModMessageEditing:
    """Tests para edicion de mensajes de moderacion."""

    async def test_accept_edits_mod_message(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que aceptar edita el mensaje de moderacion."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            request_id = request.id

        pending_status = "🔍 **Estado:** Pendiente de revision"

        # Crear mock del embed existente
        mock_embed = MagicMock()
        mock_embed.description = f"Solicitud\n\n{pending_status}"

        mock_mod_message = MagicMock()
        mock_mod_message.embeds = [mock_embed]
        mock_mod_message.edit = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado!",
            "mod_notification_channel": 888,
            "status_pending_review": pending_status,
            "status_approved": "✅ **Estado:** Aprobado por {moderator}",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, request_id=request_id)

            mock_mod_message.edit.assert_called_once()
            edit_kwargs = mock_mod_message.edit.call_args[1]
            # El contenido ahora está en el primer embed
            assert "embeds" in edit_kwargs
            main_embed = edit_kwargs["embeds"][0]
            assert "Aprobado" in (main_embed.description or "")
            assert edit_kwargs["view"] is None

    async def test_accept_mod_message_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar aceptar cuando mensaje de mod no existe."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            request_id = request.id

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado!",
            "mod_notification_channel": 888,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            # No deberia fallar
            await verification_cog.handle_accept(interaction=interaction, request_id=request_id)

            interaction.followup.send.assert_called()

    async def test_reject_edits_mod_message(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que rechazar edita el mensaje de moderacion."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            request_id = request.id

        pending_status = "🔍 **Estado:** Pendiente de revision"

        # Crear mock del embed existente
        mock_embed = MagicMock()
        mock_embed.description = f"Solicitud\n\n{pending_status}"

        mock_mod_message = MagicMock()
        mock_mod_message.embeds = [mock_embed]
        mock_mod_message.edit = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "rejection_message": "Rechazado: {reason}",
            "mod_notification_channel": 888,
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Aliado",
            "status_pending_review": pending_status,
            "status_rejected": "❌ **Estado:** Rechazado por {moderator}\n**Motivo:** {reason}",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_reject(
                interaction=interaction, request_id=request_id, reason="Capturas invalidas"
            )

            mock_mod_message.edit.assert_called_once()
            edit_kwargs = mock_mod_message.edit.call_args[1]
            # El contenido ahora está en el primer embed
            assert "embeds" in edit_kwargs
            main_embed = edit_kwargs["embeds"][0]
            assert "Rechazado" in (main_embed.description or "")
            assert "Capturas invalidas" in (main_embed.description or "")


class TestUpdateModMessageForReview:
    """Tests para _update_mod_message_for_review."""

    async def test_update_with_history(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar actualizacion con historial de verificaciones."""
        # Crear historial
        async with test_database.session() as session:
            service = VerificationService(session)
            # Solicitud anterior aprobada
            old_request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(old_request.id, "old1", "old2", "Test Guild")
            await service.approve(old_request.id, 111, "OldMod")

            # Solicitud actual
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.ALLY,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()

            # Refrescar request
            refreshed = await service.get_request(request.id)
            assert refreshed is not None
            request = refreshed

            mock_mod_message = MagicMock()
            mock_mod_message.edit = AsyncMock()

            mock_channel = MagicMock(spec=discord.TextChannel)
            mock_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

            config = {
                "mod_message_template": "Template {username}",
                "verification_type_regular_display": "Normal",
                "verification_type_ally_display": "Aliado",
                "accept_button_text": "Aceptar",
                "reject_button_text": "Rechazar",
            }

            await verification_cog._update_mod_message_for_review(
                channel=mock_channel,
                request=request,
                verification_service=service,
                config=config,
            )

            mock_mod_message.edit.assert_called_once()
            edit_kwargs = mock_mod_message.edit.call_args[1]
            # El contenido ahora está en el primer embed
            assert "embeds" in edit_kwargs
            main_embed = edit_kwargs["embeds"][0]
            # Historial ahora es un campo, no parte de la descripción
            history_field = next(
                (f for f in main_embed.fields if f.name == "Historial"),
                None,
            )
            assert history_field is not None

    async def test_update_message_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar actualizacion cuando mensaje no existe."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            refreshed = await service.get_request(request.id)
            assert refreshed is not None
            request = refreshed

            mock_channel = MagicMock(spec=discord.TextChannel)
            mock_channel.fetch_message = AsyncMock(
                side_effect=discord.NotFound(MagicMock(), "Not found")
            )

            config = {
                "mod_message_template": "Template {username}",
                "verification_type_regular_display": "Normal",
                "verification_type_ally_display": "Aliado",
                "accept_button_text": "Aceptar",
                "reject_button_text": "Rechazar",
            }

            # No deberia fallar
            await verification_cog._update_mod_message_for_review(
                channel=mock_channel,
                request=request,
                verification_service=service,
                config=config,
            )


class TestOnMessageScreenshots:
    """Tests adicionales para on_message con screenshots."""

    async def test_request_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar cuando la solicitud no existe en DB."""
        # Registrar pending pero sin crear en DB
        verification_cog._pending_dm_verifications[456] = (123, 99999)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=None))

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values = {
            "request_not_found_message": "Error: No se encontro tu solicitud.",
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            # Deberia enviar error
            message.channel.send.assert_called()
            call_args = message.channel.send.call_args
            assert "error" in call_args.kwargs["content"].lower()


class TestCogLifecycle:
    """Tests para cog_load y cog_unload."""

    async def test_cog_load_starts_health_check(self, mock_discord_bot: MagicMock) -> None:
        """Probar que cog_load inicia health check."""
        cog = VerificationCog(mock_discord_bot)

        # Mock the task
        cog.health_check_loop = MagicMock()
        cog.health_check_loop.start = MagicMock()

        await cog.cog_load()

        mock_discord_bot.add_view.assert_called_once()
        cog.health_check_loop.start.assert_called_once()
        assert cog._health_check_started is True

    async def test_cog_unload_stops_health_check(self, mock_discord_bot: MagicMock) -> None:
        """Probar que cog_unload detiene health check."""
        cog = VerificationCog(mock_discord_bot)
        cog._health_check_started = True

        cog.health_check_loop = MagicMock()
        cog.health_check_loop.cancel = MagicMock()

        await cog.cog_unload()

        cog.health_check_loop.cancel.assert_called_once()
        assert cog._health_check_started is False


class TestHealthCheckTaskMethods:
    """Tests para metodos del task loop de health check."""

    async def test_health_check_loop_calls_run_health_check(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que el loop llama a _run_health_check."""
        with patch.object(
            verification_cog, "_run_health_check", new_callable=AsyncMock
        ) as mock_run:
            await verification_cog.health_check_loop()

            mock_run.assert_called_once()

    async def test_before_health_check_waits_and_runs(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que before_health_check espera al bot y ejecuta health check."""
        with patch.object(
            verification_cog, "_run_health_check", new_callable=AsyncMock
        ) as mock_run:
            await verification_cog.before_health_check()

            wait_until_ready_mock = cast(AsyncMock, verification_cog.bot.wait_until_ready)
            wait_until_ready_mock.assert_called_once()
            # Debe ejecutar health check inmediatamente
            mock_run.assert_called_once()


class TestGetAllConfig:
    """Tests para _get_all_config."""

    async def test_get_all_config_returns_values(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que _get_all_config devuelve los valores configurados."""
        from discord_bot.common.services.config_service import ConfigService

        async with test_database.session() as session:
            config_service = ConfigService(session=session)
            await config_service.set_value(
                guild_id=123,
                cog_name="verification",
                key="verify_button_text",
                value="Mi Boton",
            )
            await session.commit()

        result = await verification_cog._get_all_config(guild_id=123)
        assert result.get("verify_button_text") == "Mi Boton"

    async def test_get_all_config_returns_empty_dict_for_missing(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que _get_all_config devuelve dict vacio para guild sin config."""
        result = await verification_cog._get_all_config(guild_id=999)
        assert isinstance(result, dict)


class TestHandleAcceptAllyRoles:
    """Tests para handle_accept con verificacion de aliado."""

    async def test_accept_ally_uses_ally_roles(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que aceptar aliado usa roles de aliado."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.ALLY,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()
            request_id = request.id

        mock_ally_role = MagicMock(spec=discord.Role)
        mock_ally_role.id = 777

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_ally_role)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [111],
            "regular_roles_remove": [],
            "ally_roles_add": [777],
            "ally_roles_remove": [222],
            "approval_message_ally": "Aprobado como aliado!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, request_id=request_id)

            # Debe usar rol de aliado, no regular
            mock_member.add_roles.assert_called_once_with(mock_ally_role)


class TestModMessageEditFallback:
    """Tests para edicion de mensaje de mod cuando no tiene estado pendiente."""

    async def test_accept_appends_status_when_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que aceptar añade estado al final si no encuentra pendiente."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            request_id = request.id

        # Mensaje sin "Pendiente de revision" - ahora como embed
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.description = "Solicitud de verificacion"
        mock_mod_message = MagicMock()
        mock_mod_message.embeds = [mock_embed]
        mock_mod_message.edit = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado!",
            "mod_notification_channel": 888,
            "status_pending_review": "Pendiente",
            "status_approved": "✅ **Estado:** Aprobado por {moderator}",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, request_id=request_id)

            mock_mod_message.edit.assert_called_once()
            edit_kwargs = mock_mod_message.edit.call_args[1]
            # El contenido ahora está en el primer embed
            assert "embeds" in edit_kwargs
            main_embed = edit_kwargs["embeds"][0]
            # Debe añadir al final
            assert "Solicitud de verificacion" in (main_embed.description or "")
            assert "Aprobado" in (main_embed.description or "")

    async def test_reject_appends_status_when_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que rechazar añade estado al final si no encuentra pendiente."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            request_id = request.id

        # Mensaje sin "Pendiente de revision" - ahora como embed
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.description = "Solicitud de verificacion"
        mock_mod_message = MagicMock()
        mock_mod_message.embeds = [mock_embed]
        mock_mod_message.edit = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "rejection_message": "Rechazado: {reason}",
            "mod_notification_channel": 888,
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Aliado",
            "status_pending_review": "Pendiente",
            "status_rejected": "❌ **Estado:** Rechazado por {moderator}\n**Motivo:** {reason}",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_reject(
                interaction=interaction, request_id=request_id, reason="Motivo test"
            )

            mock_mod_message.edit.assert_called_once()
            edit_kwargs = mock_mod_message.edit.call_args[1]
            # El contenido ahora está en el primer embed
            assert "embeds" in edit_kwargs
            main_embed = edit_kwargs["embeds"][0]
            # Debe añadir al final
            assert "Solicitud de verificacion" in (main_embed.description or "")
            assert "Rechazado" in (main_embed.description or "")
            assert "Motivo test" in (main_embed.description or "")


class TestHandleRejectEdgeCases:
    """Tests para handle_reject casos edge."""

    async def test_reject_request_not_found(self, verification_cog: VerificationCog) -> None:
        """Probar rechazo con solicitud inexistente."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "Mod"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_reject(
                interaction=interaction, request_id=99999, reason="motivo"
            )

            call_args = interaction.followup.send.call_args
            assert "no encontrada" in call_args.kwargs["content"].lower()

    async def test_reject_already_processed(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar rechazo de solicitud ya procesada."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await service.reject(
                request_id=request.id,
                reviewer_id=111,
                reviewer_username="OtherMod",
                reason="Ya rechazada",
            )
            await session.commit()
            request_id = request.id

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_reject(
                interaction=interaction, request_id=request_id, reason="motivo"
            )

            call_args = interaction.followup.send.call_args
            assert "ya fue procesada" in call_args.kwargs["content"].lower()

    async def test_reject_dm_forbidden(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar rechazo cuando DM falla."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()
            request_id = request.id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Forbidden"))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "rejection_message": "Rechazado: {reason}",
            "mod_notification_channel": None,
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Aliado",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            # No deberia fallar aunque el DM falle
            await verification_cog.handle_reject(
                interaction=interaction, request_id=request_id, reason="Capturas invalidas"
            )

            interaction.followup.send.assert_called()

    async def test_reject_mod_message_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar rechazo cuando mensaje de mod no existe."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            request_id = request.id

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "rejection_message": "Rechazado: {reason}",
            "mod_notification_channel": 888,
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Aliado",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            # No deberia fallar
            await verification_cog.handle_reject(
                interaction=interaction, request_id=request_id, reason="Capturas invalidas"
            )

            interaction.followup.send.assert_called()


class TestOnMessageUpdateModMessage:
    """Tests para on_message actualizando mensaje de moderacion."""

    async def test_screenshots_updates_mod_message(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que screenshots actualiza mensaje de mod."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.edit = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        # Mock for tracker message
        mock_tracker_message = MagicMock()
        mock_tracker_message.id = 9999
        mock_mod_channel.send = AsyncMock(return_value=mock_tracker_message)
        # Mock history for tracker positioning
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([]))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, object] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "mod_message_template": "Verificacion de {username}",
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Aliado",
            "accept_button_text": "Aceptar",
            "reject_button_text": "Rechazar",
            "tracker_title": "📋 Verificaciones Pendientes",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            # Mod message fue editado
            mock_mod_message.edit.assert_called_once()


class TestUpdateModMessageNoMessageId:
    """Tests para _update_mod_message_for_review sin mod_message_id."""

    async def test_early_return_when_no_mod_message_id(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que retorna temprano sin mod_message_id."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            # NO establecemos mod_message_id
            await session.commit()
            refreshed = await service.get_request(request.id)
            assert refreshed is not None
            request = refreshed

            mock_channel = MagicMock(spec=discord.TextChannel)
            mock_channel.fetch_message = AsyncMock()

            await verification_cog._update_mod_message_for_review(
                mock_channel, request, service, {}
            )

            # No deberia intentar fetch
            mock_channel.fetch_message.assert_not_called()


class TestSetupAndTeardown:
    """Tests para funciones setup y teardown del modulo."""

    async def test_setup_registers_schema_and_adds_cog(self, mock_discord_bot: MagicMock) -> None:
        """Probar que setup registra schema y añade cog."""
        from discord_bot.common.services.config_schema_service import (
            get_config_schema_service,
        )
        from discord_bot.verification.cog import setup

        mock_discord_bot.add_cog = AsyncMock()

        await setup(mock_discord_bot)

        # Verificar que el cog fue añadido
        mock_discord_bot.add_cog.assert_called_once()

        # Verificar que el schema fue registrado
        schema_service = get_config_schema_service()
        schema = schema_service.get_schema("verification")
        assert schema is not None

    async def test_teardown_unregisters_schema(self, mock_discord_bot: MagicMock) -> None:
        """Probar que teardown desregistra el schema."""
        from discord_bot.common.services.config_schema_service import (
            get_config_schema_service,
        )
        from discord_bot.verification.cog import setup, teardown

        mock_discord_bot.add_cog = AsyncMock()

        # Primero setup
        await setup(mock_discord_bot)

        # Luego teardown
        await teardown(mock_discord_bot)

        # Schema ya no debe existir
        schema_service = get_config_schema_service()
        schema = schema_service.get_schema("verification")
        assert schema is None


class TestOnConfigChanged:
    """Tests para on_config_changed."""

    async def test_updates_panel_on_relevant_key(self, verification_cog: VerificationCog) -> None:
        """Probar que actualiza panel cuando cambia una clave relevante."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test Guild"

        with patch.object(
            verification_cog, "_check_verification_message", new_callable=AsyncMock
        ) as mock_check:
            await verification_cog.on_config_changed(mock_guild, ["verification_channel"])

            mock_check.assert_called_once_with(guild=mock_guild, recreate=True)

    async def test_ignores_irrelevant_key(self, verification_cog: VerificationCog) -> None:
        """Probar que ignora claves no relacionadas con el panel."""
        mock_guild = MagicMock(spec=discord.Guild)

        with patch.object(
            verification_cog, "_check_verification_message", new_callable=AsyncMock
        ) as mock_check:
            await verification_cog.on_config_changed(mock_guild, ["some_other_key"])

            mock_check.assert_not_called()


class TestCheckVerificationMessageRecreate:
    """Tests para _check_verification_message con recreate=True."""

    async def test_no_channel_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar cuando no hay canal configurado."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        with patch(
            "discord_bot.verification.cog.delete_message", new_callable=AsyncMock
        ) as mock_delete:
            await verification_cog._check_verification_message(guild=mock_guild, recreate=True)

            # No debe intentar eliminar panel si no hay canal
            mock_delete.assert_not_called()

    async def test_channel_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar cuando el canal no existe."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=None)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "verification_channel", 999)
            await session.commit()

        with patch(
            "discord_bot.verification.cog.delete_message", new_callable=AsyncMock
        ) as mock_delete:
            await verification_cog._check_verification_message(guild=mock_guild, recreate=True)

            mock_delete.assert_not_called()

    async def test_deletes_old_and_creates_new(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que elimina panel viejo y crea uno nuevo."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "_panel_message_id", 777)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        with (
            patch(
                "discord_bot.verification.panel.delete_message", new_callable=AsyncMock
            ) as mock_delete,
            patch.object(
                verification_cog, "_create_verification_message", new_callable=AsyncMock
            ) as mock_create,
        ):
            await verification_cog._check_verification_message(guild=mock_guild, recreate=True)

            mock_delete.assert_called_once()
            mock_create.assert_called_once()


class TestCreateVerificationMessagePermissions:
    """Tests para _create_verification_message con diferentes estados de permisos."""

    async def test_disabled_manually(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar panel con verificacion deshabilitada manualmente."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.send = AsyncMock(return_value=MagicMock(id=888))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "verification_enabled", False)
            await config_service.set_value(
                123, "verification", "verification_disabled_message", "Deshabilitado"
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()
            call_kwargs = mock_channel.send.call_args.kwargs
            # El mensaje ahora es un embed
            assert "embed" in call_kwargs
            assert "Deshabilitado" in (call_kwargs["embed"].description or "")

    async def test_mod_channel_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar panel cuando canal de moderacion no existe."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.send = AsyncMock(return_value=MagicMock(id=888))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=None)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "verification_enabled", True)
            await config_service.set_value(123, "verification", "mod_notification_channel", 999)
            await config_service.set_value(
                123, "verification", "verification_disabled_message", "Canal no encontrado"
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()

    async def test_no_send_permissions(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar panel cuando bot no tiene permisos de enviar."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.send = AsyncMock(return_value=MagicMock(id=888))

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.name = "mod-channel"

        mock_permissions = MagicMock()
        mock_permissions.send_messages = False
        mock_mod_channel.permissions_for = MagicMock(return_value=mock_permissions)

        mock_bot_member = MagicMock(spec=discord.Member)
        mock_bot_member.id = 999

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)
        mock_guild.get_member = MagicMock(return_value=mock_bot_member)

        mock_user = MagicMock()
        mock_user.id = 999
        object.__setattr__(verification_cog.bot, "user", mock_user)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "verification_enabled", True)
            await config_service.set_value(123, "verification", "mod_notification_channel", 222)
            await config_service.set_value(
                123, "verification", "verification_disabled_message", "Sin permisos"
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()


class TestHandleVerificationStartExtended:
    """Tests adicionales para handle_verification_start."""

    async def test_verification_disabled(self, verification_cog: VerificationCog) -> None:
        """Probar inicio cuando verificacion esta deshabilitada."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.name = "TestUser"
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "verification_enabled": False,
            "verification_disabled_message": "La verificacion esta deshabilitada",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args
            assert "deshabilitada" in args[0][0]

    async def test_already_verified_regular(self, verification_cog: VerificationCog) -> None:
        """Probar inicio cuando usuario ya tiene rol de verificacion regular."""
        mock_role = MagicMock()
        mock_role.id = 100

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.name = "TestUser"
        interaction.user.roles = [mock_role]
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "verification_enabled": True,
            "block_already_verified": True,
            "regular_roles_add": [100],
            "ally_roles_add": [200],
            "already_verified_message": "Ya estas verificado",
        }

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = config_values

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args
            assert "Ya estas verificado" in args[0][0]

    async def test_already_verified_ally(self, verification_cog: VerificationCog) -> None:
        """Probar inicio cuando usuario ya tiene rol de verificacion aliado."""
        mock_role = MagicMock()
        mock_role.id = 200

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.name = "TestUser"
        interaction.user.roles = [mock_role]
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "verification_enabled": True,
            "block_already_verified": True,
            "regular_roles_add": [100],
            "ally_roles_add": [200],
            "already_verified_message": "Ya estas verificado como aliado",
        }

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = config_values

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.ALLY
            )

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args
            assert "Ya estas verificado" in args[0][0]

    async def test_already_verified_cross_regular_to_ally(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que usuario con rol regular no puede verificarse como aliado."""
        mock_role = MagicMock()
        mock_role.id = 100  # Rol de miembro regular

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.name = "TestUser"
        interaction.user.roles = [mock_role]
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "verification_enabled": True,
            "block_already_verified": True,
            "regular_roles_add": [100],
            "ally_roles_add": [200],
            "already_verified_message": "Ya estas verificado",
        }

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = config_values

            # Intentar verificar como aliado teniendo rol de miembro
            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.ALLY
            )

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args
            assert "Ya estas verificado" in args[0][0]

    async def test_already_verified_cross_ally_to_regular(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que usuario con rol aliado no puede verificarse como regular."""
        mock_role = MagicMock()
        mock_role.id = 200  # Rol de aliado

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.name = "TestUser"
        interaction.user.roles = [mock_role]
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "verification_enabled": True,
            "block_already_verified": True,
            "regular_roles_add": [100],
            "ally_roles_add": [200],
            "already_verified_message": "Ya estas verificado",
        }

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = config_values

            # Intentar verificar como regular teniendo rol de aliado
            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args
            assert "Ya estas verificado" in args[0][0]


class TestOnInteraction:
    """Tests para on_interaction listener."""

    async def test_ignores_non_component_interaction(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que ignora interacciones que no son de componentes."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.application_command

        with patch.object(verification_cog, "handle_accept", new_callable=AsyncMock) as mock_accept:
            await verification_cog.on_interaction(interaction)

            mock_accept.assert_not_called()

    async def test_handles_accept_button(self, verification_cog: VerificationCog) -> None:
        """Probar manejo de boton de aceptar."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:accept:123"}

        with patch.object(verification_cog, "handle_accept", new_callable=AsyncMock) as mock_accept:
            await verification_cog.on_interaction(interaction)

            mock_accept.assert_called_once_with(interaction=interaction, request_id=123)

    async def test_handles_reject_button(self, verification_cog: VerificationCog) -> None:
        """Probar manejo de boton de rechazar."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:reject:456"}

        with patch.object(
            verification_cog, "show_rejection_select", new_callable=AsyncMock
        ) as mock_reject:
            await verification_cog.on_interaction(interaction)

            mock_reject.assert_called_once_with(interaction=interaction, request_id=456)

    async def test_handles_invalid_accept_id(self, verification_cog: VerificationCog) -> None:
        """Probar manejo de ID invalido en aceptar."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:accept:invalid"}

        with patch.object(verification_cog, "handle_accept", new_callable=AsyncMock) as mock_accept:
            # Should not raise, just log error
            await verification_cog.on_interaction(interaction)

            mock_accept.assert_not_called()

    async def test_handles_invalid_reject_id(self, verification_cog: VerificationCog) -> None:
        """Probar manejo de ID invalido en rechazar."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:reject:not_a_number"}

        with patch.object(
            verification_cog, "show_rejection_select", new_callable=AsyncMock
        ) as mock_reject:
            await verification_cog.on_interaction(interaction)

            mock_reject.assert_not_called()

    async def test_ignores_unrelated_custom_id(self, verification_cog: VerificationCog) -> None:
        """Probar que ignora custom_ids no relacionados."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "other:button:123"}

        with (
            patch.object(verification_cog, "handle_accept", new_callable=AsyncMock) as mock_accept,
            patch.object(
                verification_cog, "show_rejection_select", new_callable=AsyncMock
            ) as mock_reject,
        ):
            await verification_cog.on_interaction(interaction)

            mock_accept.assert_not_called()
            mock_reject.assert_not_called()

    async def test_handles_no_data(self, verification_cog: VerificationCog) -> None:
        """Probar manejo cuando interaction.data es None."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = None
        interaction.response.is_done.return_value = False

        with patch.object(verification_cog, "handle_accept", new_callable=AsyncMock) as mock_accept:
            await verification_cog.on_interaction(interaction)

            mock_accept.assert_not_called()


class TestOnCogToggled:
    """Tests para on_cog_toggled."""

    async def test_enabled_creates_panel(self, verification_cog: VerificationCog) -> None:
        """Probar que habilitar el cog crea el panel."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.name = "Test Guild"

        with patch.object(
            verification_cog, "_check_verification_message", new_callable=AsyncMock
        ) as mock_check:
            await verification_cog.on_cog_toggled(guild, enabled=True)

            mock_check.assert_called_once_with(guild=guild, recreate=True)

    async def test_disabled_deletes_panel(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que deshabilitar el cog elimina el panel."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.name = "Test Guild"

        # Configurar panel existente
        async with test_database.session() as session:
            config_service = ConfigService(session=session)
            await config_service.set_value(
                guild_id=123, cog_name="verification", key=ConfigKey.PANEL_MESSAGE_ID, value=999
            )
            await config_service.set_value(
                guild_id=123, cog_name="verification", key=ConfigKey.PANEL_CHANNEL_ID, value=888
            )
            await session.commit()

        with patch(
            "discord_bot.verification.cog.delete_message", new_callable=AsyncMock
        ) as mock_delete:
            mock_delete.return_value = True
            await verification_cog.on_cog_toggled(guild, enabled=False)

            mock_delete.assert_called_once_with(guild=guild, channel_id=888, message_id=999)

    async def test_disabled_no_panel_configured(self, verification_cog: VerificationCog) -> None:
        """Probar deshabilitar cuando no hay panel configurado."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.name = "Test Guild"

        # No deberia fallar
        await verification_cog.on_cog_toggled(guild, enabled=False)


class TestCheckVerificationMessageCogDisabled:
    """Tests para _check_verification_message cuando el cog esta deshabilitado."""

    async def test_returns_early_when_cog_disabled(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que retorna temprano si el cog esta deshabilitado."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123

        # Deshabilitar explicitamente el cog (por defecto esta habilitado)
        async with test_database.session() as session:
            config_service = ConfigService(session=session)
            await config_service.set_cog_enabled(
                guild_id=123, cog_name="verification", enabled=False
            )
            await session.commit()

        with patch.object(
            verification_cog, "_create_verification_message", new_callable=AsyncMock
        ) as mock_create:
            await verification_cog._check_verification_message(guild, recreate=False)

            # No deberia crear mensaje si el cog esta deshabilitado
            mock_create.assert_not_called()


class TestGetAllConfigWithService:
    """Tests para _get_all_config con config_service proporcionado."""

    async def test_uses_provided_config_service(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que usa el config_service proporcionado."""
        async with test_database.session() as session:
            config_service = ConfigService(session=session)

            # Llamar con config_service proporcionado
            result = await verification_cog._get_all_config(
                guild_id=123, config_service=config_service
            )

            assert isinstance(result, dict)


class TestGetModChannelEdgeCases:
    """Tests para _get_mod_channel casos extremos."""

    def test_bot_user_none(self, verification_cog: VerificationCog) -> None:
        """Probar cuando bot.user es None."""
        with patch.object(verification_cog.bot, "user", None):
            guild = MagicMock(spec=discord.Guild)
            mod_channel = MagicMock(spec=discord.TextChannel)
            guild.get_channel = MagicMock(return_value=mod_channel)

            config = {"mod_notification_channel": 123}

            result = verification_cog._get_mod_channel(guild, config)

            assert result is None

    def test_bot_member_not_found(self, verification_cog: VerificationCog) -> None:
        """Probar cuando el bot no es miembro del guild."""
        mock_user = MagicMock()
        mock_user.id = 999

        with patch.object(verification_cog.bot, "user", mock_user):
            guild = MagicMock(spec=discord.Guild)
            mod_channel = MagicMock(spec=discord.TextChannel)
            guild.get_channel = MagicMock(return_value=mod_channel)
            guild.get_member = MagicMock(return_value=None)

            config = {"mod_notification_channel": 123}

            result = verification_cog._get_mod_channel(guild, config)

            assert result is None


class TestValidateModActionEdgeCases:
    """Tests para _validate_mod_action casos extremos."""

    async def test_no_guild(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar cuando no hay guild."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None

        async with test_database.session() as session:
            result = await verification_cog._validate_mod_action(
                interaction=interaction,
                request_id=1,
                session=session,
                permission_error_key=ConfigKey.NO_PERMISSION_APPROVE_MESSAGE,
                permission_error_default="Sin permisos",
            )

        assert result is None

    async def test_user_not_member(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar cuando el usuario no es Member."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.user = MagicMock(spec=discord.User)  # User, no Member

        async with test_database.session() as session:
            result = await verification_cog._validate_mod_action(
                interaction=interaction,
                request_id=1,
                session=session,
                permission_error_key=ConfigKey.NO_PERMISSION_APPROVE_MESSAGE,
                permission_error_default="Sin permisos",
            )

        assert result is None


class TestHandleVerificationStartCogDisabled:
    """Tests para handle_verification_start cuando el cog esta deshabilitado."""

    async def test_cog_disabled_returns_early(self, verification_cog: VerificationCog) -> None:
        """Probar que retorna temprano si el cog esta deshabilitado."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()

        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            # No deberia hacer defer si el cog esta deshabilitado
            interaction.response.defer.assert_not_called()

    async def test_mod_channel_not_accessible(self, verification_cog: VerificationCog) -> None:
        """Probar cuando el canal de moderacion no es accesible."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values = {
            "verification_enabled": True,
            "mod_notification_channel": 999,
            "verification_disabled_message": "Sistema no disponible",
        }

        with (
            patch.object(
                verification_cog, "_is_cog_enabled", new_callable=AsyncMock
            ) as mock_enabled,
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel") as mock_mod_channel,
        ):
            mock_enabled.return_value = True
            mock_config.return_value = config_values
            mock_mod_channel.return_value = None  # Canal no accesible

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            # Deberia enviar mensaje de sistema no disponible
            interaction.followup.send.assert_called_once()


class TestOnMessageCogDisabled:
    """Tests para on_message cuando el cog esta deshabilitado."""

    async def test_cog_disabled_returns_early(self, verification_cog: VerificationCog) -> None:
        """Probar que retorna temprano si el cog esta deshabilitado."""
        verification_cog._pending_dm_verifications[456] = (123, 1)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog.on_message(message)

            # No deberia enviar nada si el cog esta deshabilitado
            message.channel.send.assert_not_called()


class TestUpdateModMessageWithRejectionReason:
    """Tests para _update_mod_message_for_review con historial de rechazo."""

    async def test_history_includes_rejection_reason(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que el historial incluye el motivo de rechazo."""
        # Crear una verificacion rechazada previamente
        async with test_database.session() as session:
            service = VerificationService(session)
            old_request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(old_request.id, "url1", "url2", "Test Guild")
            await service.reject(old_request.id, 789, "ModUser", "Capturas incorrectas")
            await session.commit()

        # Crear nueva verificacion con mod_message_id
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url3", url2="url4", guild_name="Test Guild"
            )
            request.mod_message_id = 777  # Necesario para que el metodo no retorne temprano
            await session.commit()
            request_id = request.id

        # Mock del mensaje de moderacion
        mod_message = MagicMock()
        mod_message.content = "Mensaje original"
        mod_message.edit = AsyncMock()

        # Mock del canal
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mod_message)

        config_values: dict[str, Any] = {
            "mod_message_template": "{username} - {status}",
            "status_pending_review": "Pendiente",
            "accept_button_text": "Aceptar",
            "reject_button_text": "Rechazar",
        }

        async with test_database.session() as session:
            service = VerificationService(session)
            fetched_request = await service.get_request(request_id)
            assert fetched_request is not None

            await verification_cog._update_mod_message_for_review(
                channel=mock_channel,
                request=fetched_request,
                verification_service=service,
                config=config_values,
            )

            # Verificar que el mensaje editado contiene el motivo de rechazo
            call_args = mod_message.edit.call_args
            # El contenido ahora está en el primer embed
            assert "embeds" in call_args.kwargs
            main_embed = call_args.kwargs["embeds"][0]
            # Historial ahora es un campo con el motivo de rechazo
            history_field = next(
                (f for f in main_embed.fields if f.name == "Historial"),
                None,
            )
            assert history_field is not None
            assert "Capturas incorrectas" in history_field.value


class TestHandleAcceptCogDisabled:
    """Tests para handle_accept cuando el cog esta deshabilitado."""

    async def test_cog_disabled_returns_early(self, verification_cog: VerificationCog) -> None:
        """Probar que retorna temprano si el cog esta deshabilitado."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()

        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog.handle_accept(interaction, request_id=1)

            # No deberia hacer nada si el cog esta deshabilitado
            interaction.response.defer.assert_not_called()


class TestHandleAcceptRoleNotFound:
    """Tests para handle_accept cuando el rol no se encuentra."""

    async def test_role_add_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar cuando un rol a agregar no existe en el guild."""
        from discord_bot.verification.enums import VerificationType

        # Crear solicitud
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()
            request_id = request.id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)  # Rol no encontrado
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values = {
            "mod_roles": [],
            "regular_roles_add": [999],  # Este rol no existe
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, request_id=request_id)

            # No deberia intentar agregar roles ya que no existe
            mock_member.add_roles.assert_not_called()

    async def test_role_remove_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar cuando un rol a quitar no existe en el guild."""
        from discord_bot.verification.enums import VerificationType

        # Crear solicitud
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()
            request_id = request.id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)  # Rol no encontrado
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [999],  # Este rol no existe
            "approval_message_regular": "Aprobado!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, request_id=request_id)

            # No deberia intentar quitar roles ya que no existe
            mock_member.remove_roles.assert_not_called()


class TestHandleAcceptDeleteModMessage:
    """Tests para handle_accept eliminando mensaje de moderacion."""

    async def test_deletes_mod_message_when_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que elimina el mensaje de mod cuando esta configurado."""
        from discord_bot.verification.enums import VerificationType

        # Crear solicitud con mod_message_id
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            request.mod_message_id = 777
            await session.commit()
            request_id = request.id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_mod_message = MagicMock()
        mock_mod_message.delete = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado!",
            "mod_notification_channel": 888,
            "delete_processed_messages": True,  # Configurado para eliminar
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, request_id=request_id)

            # Deberia eliminar el mensaje
            mock_mod_message.delete.assert_called_once()


class TestShowRejectionSelectCogDisabled:
    """Tests para show_rejection_select cuando el cog esta deshabilitado."""

    async def test_cog_disabled_returns_early(self, verification_cog: VerificationCog) -> None:
        """Probar que retorna temprano si el cog esta deshabilitado."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog.show_rejection_select(interaction, request_id=1)

            # No deberia enviar nada si el cog esta deshabilitado
            interaction.response.send_message.assert_not_called()


class TestHandleRejectCogDisabled:
    """Tests para handle_reject cuando el cog esta deshabilitado."""

    async def test_cog_disabled_returns_early(self, verification_cog: VerificationCog) -> None:
        """Probar que retorna temprano si el cog esta deshabilitado."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()

        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog.handle_reject(
                interaction=interaction, request_id=1, reason="Test"
            )

            # No deberia hacer nada si el cog esta deshabilitado
            interaction.response.defer.assert_not_called()


class TestHandleRejectDeleteModMessage:
    """Tests para handle_reject eliminando mensaje de moderacion."""

    async def test_deletes_mod_message_when_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que elimina el mensaje de mod cuando esta configurado."""
        from discord_bot.verification.enums import VerificationType

        # Crear solicitud con mod_message_id
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            request.mod_message_id = 777
            await session.commit()
            request_id = request.id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_mod_message = MagicMock()
        mock_mod_message.delete = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values = {
            "mod_roles": [],
            "rejection_message": "Tu verificacion fue rechazada: {reason}",
            "verification_type_regular_display": "Normal",
            "mod_notification_channel": 888,
            "delete_processed_messages": True,  # Configurado para eliminar
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_reject(
                interaction, request_id, reason="Capturas incorrectas"
            )

            # Deberia eliminar el mensaje
            mock_mod_message.delete.assert_called_once()


class TestHandleReview:
    """Tests para handle_review (revisión de auto-rechazos)."""

    async def test_review_no_guild(self, verification_cog: VerificationCog) -> None:
        """Probar que revisa que hay guild."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None

        await verification_cog.handle_review(interaction, request_id=1)

    async def test_review_not_mod(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que requiere permisos de moderador."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = False
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        # Habilitar cog
        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        config_values = {
            "mod_roles": [999],  # Usuario no tiene este rol
            "no_permission_reject_message": "No tienes permisos",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_review(interaction, request_id=1)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert call_args.kwargs["ephemeral"] is True

    async def test_review_not_auto_rejected(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que solo permite revisar auto-rechazos."""
        # Crear solicitud rechazada manualmente (no Auto)
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.reject(
                request_id=request.id,
                reviewer_id=789,
                reviewer_username="ModUser",
                reason="Motivo manual",
            )
            await session.commit()
            request_id = request.id

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        config_values: dict[str, Any] = {"mod_roles": []}

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_review(interaction, request_id)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "no fue auto-rechazada" in call_args.kwargs["content"]
            assert call_args.kwargs["ephemeral"] is True

    async def test_review_not_latest(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que solo permite revisar la última verificación."""
        # Crear dos solicitudes, rechazar ambas
        async with test_database.session() as session:
            service = VerificationService(session)
            request1 = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.reject(request1.id, 0, "Auto", "Razon auto")

            request2 = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.ALLY,
            )
            await service.reject(request2.id, 0, "Auto", "Otra razon auto")
            await session.commit()
            old_request_id = request1.id

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        config_values: dict[str, Any] = {"mod_roles": []}

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            # Intentar revisar la solicitud antigua
            await verification_cog.handle_review(interaction, old_request_id)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "última verificación" in call_args.kwargs["content"]
            assert call_args.kwargs["ephemeral"] is True

    async def test_review_success(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar revisión exitosa de auto-rechazo."""
        # Crear solicitud auto-rechazada
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            # Rechazar con Auto
            await service.reject(
                request_id=request.id,
                reviewer_id=0,
                reviewer_username="Auto",
                reason="Razon automatica",
            )
            await session.commit()
            request_id = request.id

        # Mock del mensaje de moderación
        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.description = "Solicitud de TestUser\n❌ Auto-rechazado"
        mock_mod_message.embeds = [mock_embed]
        mock_mod_message.edit = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        # Mock for tracker message
        mock_tracker_message = MagicMock()
        mock_tracker_message.id = 9999
        mock_mod_channel.send = AsyncMock(return_value=mock_tracker_message)
        # Mock history for tracker positioning
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([]))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        config_values = {
            "mod_roles": [],
            "mod_notification_channel": 888,
            "status_pending_review": "⏳ Pendiente",
            "status_rejected": "❌ Auto-rechazado",
            "accept_button_text": "Aceptar",
            "reject_button_text": "Rechazar",
            "tracker_title": "📋 Verificaciones Pendientes",
        }

        # Guardar mod_message_id en la solicitud
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.set_mod_message_id(request_id, 999)
            await session.commit()

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_review(interaction, request_id)

            # Verificar respuesta exitosa
            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "revisión manual" in call_args.kwargs["content"]
            assert call_args.kwargs["ephemeral"] is True

            # Verificar que se editó el mensaje de moderación
            mock_mod_message.edit.assert_called_once()
            edit_kwargs = mock_mod_message.edit.call_args.kwargs
            assert edit_kwargs["view"] is not None  # Tiene botones

        # Verificar estado en DB
        async with test_database.session() as session:
            service = VerificationService(session)
            updated_request = await service.get_request(request_id)
            assert updated_request is not None
            assert updated_request.status == VerificationStatus.PENDING_REVIEW
            assert updated_request.reviewed_by_id is None
            assert updated_request.reviewed_by_username is None

    async def test_review_cog_disabled(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que handle_review retorna si el cog está deshabilitado."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        # Mockear cog deshabilitado
        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog.handle_review(interaction, request_id=1)

            # No debería llamar a send_message
            interaction.response.send_message.assert_not_called()

    async def test_review_request_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que handle_review maneja solicitud no encontrada."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        # Habilitar cog
        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        config_values: dict[str, Any] = {
            "mod_roles": [],
            "request_not_found_message": "Solicitud no existe",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_review(interaction, request_id=99999)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "no existe" in call_args.kwargs["content"]
            assert call_args.kwargs["ephemeral"] is True


class TestAutoProcessingEdgeCases:
    """Tests para casos edge de auto-procesamiento."""

    async def test_api_error_non_422_shows_error(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que errores API no-422 muestran mensaje de error."""
        from discord_bot.verification.api_client import VerificationAPIResult
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild
        mock_mod_channel.send = AsyncMock(return_value=mock_mod_message)

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.NONE,  # No auto-process
        }

        # Mock API devuelve 500 (error interno)
        api_result = VerificationAPIResult(
            success=False,
            status_code=500,
            error_message="Internal server error",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que la solicitud quedó en PENDING_REVIEW
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_REVIEW

    async def test_player_info_template_formatted(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que player_info_template se formatea correctamente."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild
        mock_mod_channel.send = AsyncMock(return_value=mock_mod_message)

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.NONE,
            "player_info_template": "Nombre: {name}, Nivel: {level}",
        }

        api_response = VerificationAPIResponse(
            name="TestPlayer",
            level=15,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que la solicitud quedó en PENDING_REVIEW
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_REVIEW

    async def test_legacy_boolean_true_auto_mode(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar compatibilidad con valor booleano True para verification_automatic."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": True,  # Legacy boolean
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado",
            "delete_processed_messages": True,
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que se auto-aprobó (True = BOTH)
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED

    async def test_auto_approve_ally_uses_ally_roles(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que auto-aprobación de aliado usa los roles de aliado."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.ALLY,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_ally_role = MagicMock(spec=discord.Role)
        mock_ally_role.id = 888
        mock_ally_role.name = "Ally"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_ally_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "ally_roles_add": [888],
            "ally_roles_remove": [],
            "approval_message_ally": "Bienvenido aliado",
            "delete_processed_messages": True,
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="82DK",  # Tiene regimiento - OK para aliado
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que se auto-aprobó
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED

        # Verificar que se añadió el rol de aliado
        mock_member.add_roles.assert_called_once_with(mock_ally_role)

    async def test_auto_approve_forbidden_on_add_roles(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que Forbidden en add_roles no rompe el flujo."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.name = "TestUser"
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Missing permissions")
        )
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado",
            "delete_processed_messages": True,
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            # No debería lanzar excepción
            await verification_cog.on_message(message)

        # Verificar que la solicitud fue aprobada de todos modos
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED

    async def test_auto_approve_forbidden_on_send_dm(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que Forbidden en send DM no rompe el flujo."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Cannot send DM"))
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado",
            "delete_processed_messages": True,
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que la solicitud fue aprobada
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED

    async def test_auto_approve_no_delete_edits_message(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que auto-aprobación sin delete_processed_messages edita el mensaje."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado",
            "delete_processed_messages": False,  # No borrar, editar
            "status_pending_review": "⏳ Pendiente",
            "status_approved": "✅ Aprobado por {moderator}",
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que se editó en lugar de borrar
        mock_mod_message.delete.assert_not_called()
        mock_mod_message.edit.assert_called_once()

    async def test_auto_reject_no_delete_edits_with_review_button(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que auto-rechazo sin delete añade botón de revisión."""
        from discord_bot.verification.api_client import VerificationAPIResult
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,
            "reject_wrong_captures": "Capturas inválidas",
            "rejection_message": "Rechazado: {reason}",
            "delete_processed_messages": False,  # No borrar
            "status_pending_review": "⏳ Pendiente",
            "status_rejected": "❌ Rechazado: {reason}",
            "auto_reject_review_window": 30,  # 30 minutos para revisión
            "review_button_text": "Revisar",
        }

        api_result = VerificationAPIResult(
            success=False,
            status_code=422,
            error_message="Invalid images",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que se editó con view
        mock_mod_message.delete.assert_not_called()
        mock_mod_message.edit.assert_called_once()
        edit_kwargs = mock_mod_message.edit.call_args.kwargs
        assert edit_kwargs["view"] is not None

    async def test_auto_reject_forbidden_on_send_dm(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que Forbidden en DM de rechazo no rompe el flujo."""
        from discord_bot.verification.api_client import VerificationAPIResult
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Cannot send DM"))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,
            "reject_wrong_captures": "Capturas inválidas",
            "rejection_message": "Rechazado: {reason}",
            "delete_processed_messages": True,
        }

        api_result = VerificationAPIResult(
            success=False,
            status_code=422,
            error_message="Invalid images",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que la solicitud fue rechazada
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.REJECTED

    async def test_ready_for_manual_approval_reject_only_mode(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar listo para aprobación manual cuando modo es REJECT_ONLY."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_mod_role = MagicMock(spec=discord.Role)
        mock_mod_role.mention = "<@&999>"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_mod_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild
        mock_mod_channel.send = AsyncMock(return_value=mock_mod_message)

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,  # Solo rechaza, no aprueba
            "mod_roles": [999],
            "status_pending_review": "⏳ Pendiente",
            "status_ready_for_approval": "✅ Listo - {roles}",
        }

        # API devuelve respuesta exitosa que pasa todas las verificaciones
        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que la solicitud quedó en PENDING_REVIEW (no auto-aprobada)
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_REVIEW

    async def test_auto_approve_forbidden_on_remove_roles(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que Forbidden en remove_roles no rompe el flujo."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_role_add = MagicMock(spec=discord.Role)
        mock_role_add.id = 999
        mock_role_add.name = "Verified"

        mock_role_remove = MagicMock(spec=discord.Role)
        mock_role_remove.id = 888
        mock_role_remove.name = "Unverified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.name = "TestUser"
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Missing permissions")
        )

        def get_role_side_effect(role_id: int) -> MagicMock | None:
            if role_id == 999:
                return mock_role_add
            elif role_id == 888:
                return mock_role_remove
            return None

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(side_effect=get_role_side_effect)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [888],  # Tiene roles a remover
            "approval_message_regular": "Aprobado",
            "delete_processed_messages": True,
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            # No debería lanzar excepción
            await verification_cog.on_message(message)

        # Verificar que la solicitud fue aprobada
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED

    async def test_auto_approve_no_pending_status_appends(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que sin status_pending_review se añade al final."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado",
            "delete_processed_messages": False,
            "status_pending_review": "",  # Sin status pendiente
            "status_approved": "✅ Aprobado por {moderator}",
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que se editó
        mock_mod_message.edit.assert_called_once()

    async def test_auto_reject_no_review_window(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar auto-rechazo sin ventana de revisión (view=None)."""
        from discord_bot.verification.api_client import VerificationAPIResult
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,
            "reject_wrong_captures": "Capturas inválidas",
            "rejection_message": "Rechazado: {reason}",
            "delete_processed_messages": False,
            "status_pending_review": "⏳ Pendiente",
            "status_rejected": "❌ Rechazado: {reason}",
            "auto_reject_review_window": 0,  # Sin ventana de revisión
        }

        api_result = VerificationAPIResult(
            success=False,
            status_code=422,
            error_message="Invalid images",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que se editó sin view
        mock_mod_message.edit.assert_called_once()
        edit_kwargs = mock_mod_message.edit.call_args.kwargs
        assert edit_kwargs["view"] is None

    async def test_auto_reject_no_pending_status_appends(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que sin status_pending_review se añade al final para rechazo."""
        from discord_bot.verification.api_client import VerificationAPIResult
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,
            "reject_wrong_captures": "Capturas inválidas",
            "rejection_message": "Rechazado: {reason}",
            "delete_processed_messages": False,
            "status_pending_review": "",  # Sin status pendiente
            "status_rejected": "❌ Rechazado: {reason}",
            "auto_reject_review_window": 0,
        }

        api_result = VerificationAPIResult(
            success=False,
            status_code=422,
            error_message="Invalid images",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que se editó
        mock_mod_message.edit.assert_called_once()


class TestOnInteractionReview:
    """Tests para on_interaction con botón de revisión."""

    async def test_review_button_invalid_id(self, verification_cog: VerificationCog) -> None:
        """Probar manejo de ID inválido en botón de revisión."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:review:invalid"}

        # Habilitar cog
        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = True

            # No debería lanzar excepción
            await verification_cog.on_interaction(interaction)

    async def test_review_button_missing_parts(self, verification_cog: VerificationCog) -> None:
        """Probar manejo de custom_id con partes faltantes."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:review"}  # Sin request_id

        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = True

            # No debería lanzar excepción
            await verification_cog.on_interaction(interaction)

    async def test_review_button_valid_id(self, verification_cog: VerificationCog) -> None:
        """Probar manejo de ID válido en botón de revisión."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:review:42"}

        with (
            patch.object(
                verification_cog, "_is_cog_enabled", new_callable=AsyncMock
            ) as mock_enabled,
            patch.object(
                verification_cog, "handle_review", new_callable=AsyncMock
            ) as mock_handle_review,
        ):
            mock_enabled.return_value = True

            await verification_cog.on_interaction(interaction)

            mock_handle_review.assert_called_once_with(interaction=interaction, request_id=42)


class TestGetPendingVerification:
    """Tests para _get_pending_verification."""

    async def test_returns_none_when_no_pending(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que retorna None cuando no hay verificación pendiente."""
        result = await verification_cog._get_pending_verification(user_id=99999)
        assert result is None


class TestHandleReviewRevertFails:
    """Tests para handle_review cuando revert falla."""

    async def test_revert_fails(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar manejo cuando revert_to_pending_review falla."""
        # Crear solicitud auto-rechazada
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.reject(
                request_id=request.id,
                reviewer_id=0,
                reviewer_username="Auto",
                reason="Razon auto",
            )
            await session.commit()
            request_id = request.id

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        config_values: dict[str, Any] = {"mod_roles": []}

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.VerificationService.revert_to_pending_review",
                new_callable=AsyncMock,
            ) as mock_revert,
        ):
            mock_config.return_value = config_values
            mock_revert.return_value = False  # Revert falla

            await verification_cog.handle_review(interaction, request_id)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "No se pudo revertir" in call_args.kwargs["content"]


class TestLegacyBooleanAutoMode:
    """Tests para compatibilidad con legacy boolean verification_automatic."""

    async def test_legacy_false_disables_auto(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que False legacy desactiva auto-procesamiento."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild
        mock_mod_channel.send = AsyncMock(return_value=mock_mod_message)

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": False,  # Legacy boolean False
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # No debería auto-aprobar, queda en PENDING_REVIEW
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_request(request_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_REVIEW


class TestStatusReplacementInFormatted:
    """Tests para reemplazo de status cuando SÍ está en formatted."""

    async def test_auto_approve_replaces_pending_status(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que auto-aprobación reemplaza el status pendiente."""
        from discord_bot.verification.api_client import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # El mensaje ya tiene el status pendiente
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.description = "Solicitud de TestUser\n\n⏳ Pendiente de revisión"

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = [mock_embed]

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Aprobado",
            "delete_processed_messages": False,
            "mod_message_template": "Solicitud de {username}\n\n{status}",  # Template con status
            "status_pending_review": "⏳ Pendiente de revisión",
            "status_approved": "✅ Aprobado por {moderator}",
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que se editó
        mock_mod_message.edit.assert_called_once()

    async def test_auto_reject_replaces_pending_status(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que auto-rechazo reemplaza el status pendiente."""
        from discord_bot.verification.api_client import VerificationAPIResult
        from discord_bot.verification.enums import AutoProcessMode

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # El mensaje ya tiene el status pendiente
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.description = "Solicitud de TestUser\n\n⏳ Pendiente"

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = [mock_embed]

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,
            "reject_wrong_captures": "Capturas inválidas",
            "rejection_message": "Rechazado: {reason}",
            "delete_processed_messages": False,
            "mod_message_template": "Solicitud de {username}\n\n{status}",  # Template con status
            "status_pending_review": "⏳ Pendiente",
            "status_rejected": "❌ Rechazado: {reason}",
            "auto_reject_review_window": 0,
        }

        api_result = VerificationAPIResult(
            success=False,
            status_code=422,
            error_message="Invalid images",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verificar que se editó
        mock_mod_message.edit.assert_called_once()


class TestHandleReviewRegexFallback:
    """Tests para regex fallback en _update_mod_message_for_review."""

    @pytest.mark.asyncio
    async def test_regex_fallback_finds_auto_reject_pattern(
        self, mock_discord_guild: MagicMock
    ) -> None:
        """Probar que regex encuentra patrón de auto-rechazo."""
        request = MagicMock()
        request.mod_message_id = 999
        request.username = "TestUser"
        request.user_id = 456
        request.verification_type = VerificationType.REGULAR

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.guild = mock_discord_guild

        mock_mod_message = MagicMock(spec=discord.Message)
        mock_mod_message.content = "Info\n\n❌ Auto-rechazado: razón\n\nMás info"
        mock_mod_message.embeds = []
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_message.edit = AsyncMock()

        mock_discord_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        config: dict[str, Any] = {
            "mod_notification_channel": 888,
            "status_pending_review": "⏳ Pendiente de revisión",
            "status_rejected": "ESTADO DIFERENTE",
        }

        from discord_bot.verification.handlers import _update_mod_message_for_review

        await _update_mod_message_for_review(
            guild=mock_discord_guild,
            request=request,
            config=config,
            request_id=1,
        )

        mock_mod_message.edit.assert_called_once()

    @pytest.mark.asyncio
    async def test_regex_fallback_appends_when_no_match(
        self, mock_discord_guild: MagicMock
    ) -> None:
        """Probar que añade estado pendiente si no hay match."""
        request = MagicMock()
        request.mod_message_id = 999
        request.username = "TestUser"
        request.user_id = 456
        request.verification_type = VerificationType.REGULAR

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.guild = mock_discord_guild

        mock_mod_message = MagicMock(spec=discord.Message)
        mock_mod_message.content = "Info sin estado de rechazo"
        mock_mod_message.embeds = []
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_message.edit = AsyncMock()

        mock_discord_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        config: dict[str, Any] = {
            "mod_notification_channel": 888,
            "status_pending_review": "⏳ Pendiente de revisión",
            "status_rejected": "",
        }

        from discord_bot.verification.handlers import _update_mod_message_for_review

        await _update_mod_message_for_review(
            guild=mock_discord_guild,
            request=request,
            config=config,
            request_id=1,
        )

        mock_mod_message.edit.assert_called_once()


class TestGetLockedOptions:
    """Tests para get_locked_options."""

    def test_returns_empty_dict(self, verification_cog: VerificationCog) -> None:
        """Probar que retorna un diccionario vacío."""
        result = verification_cog.get_locked_options()
        assert result == {}


class TestIsCogEnabled:
    """Tests para _is_cog_enabled."""

    async def test_returns_true_when_enabled(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que retorna True cuando el cog está habilitado."""
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=123, cog_name="verification", enabled=True
            )
            await session.commit()

        cog = VerificationCog(verification_cog.bot)
        result = await cog._is_cog_enabled(123)
        assert result is True

    async def test_returns_false_when_disabled(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que retorna False cuando el cog está deshabilitado."""
        cog = VerificationCog(verification_cog.bot)
        result = await cog._is_cog_enabled(999)
        assert result is False


class TestCreatePanelEmbed:
    """Tests para _create_panel_embed."""

    def test_creates_embed_with_text(self, verification_cog: VerificationCog) -> None:
        """Probar que crea un embed con el texto proporcionado."""
        text = "Panel de verificación"
        embed = verification_cog._create_panel_embed(text)
        assert embed is not None
        assert isinstance(embed, discord.Embed)


class TestRebuildSingleEmbed:
    """Tests para _rebuild_single_embed."""

    async def test_returns_false_without_mod_message_id(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que retorna False si no hay mod_message_id."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_request = MagicMock()
        mock_request.mod_message_id = None

        result = await verification_cog._rebuild_single_embed(
            guild=mock_guild,
            channel=mock_channel,
            request=mock_request,
            config={},
        )
        assert result is False

    async def test_returns_false_when_message_not_found(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que retorna False si el mensaje no existe."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test Guild"

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        mock_request = MagicMock()
        mock_request.mod_message_id = 789

        result = await verification_cog._rebuild_single_embed(
            guild=mock_guild,
            channel=mock_channel,
            request=mock_request,
            config={},
        )
        assert result is False

    async def test_rebuilds_embed_successfully(self, verification_cog: VerificationCog) -> None:
        """Probar que reconstruye el embed correctamente."""
        mock_member = MagicMock(spec=discord.Member)
        mock_member.mention = "<@456>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_embed = MagicMock()
        mock_embed.description = "Usuario: Test\n⏳ Estado: Esperando"

        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [mock_embed]
        mock_message.edit = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_request = MagicMock()
        mock_request.id = 1
        mock_request.mod_message_id = 789
        mock_request.username = "TestUser"
        mock_request.user_id = 456
        mock_request.guild_id = 123
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.created_at = datetime.now(UTC)
        mock_request.player_info = None

        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "sections": [{"type": "text", "content": "Usuario: {username}\n{status}"}]
            },
            ConfigKey.MOD_EMBED_ALLY: {
                "sections": [{"type": "text", "content": "Usuario: {username}\n{status}"}]
            },
            ConfigKey.STATUS_AWAITING_SCREENSHOTS: "⏳ Esperando capturas",
            ConfigKey.ACCEPT_BUTTON_TEXT: "Aceptar",
            ConfigKey.REJECT_BUTTON_TEXT: "Rechazar",
        }

        # Mock database session for history lookup
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(verification_cog.bot.database, "session", return_value=mock_session),
            patch("discord_bot.verification.cog.VerificationService") as mock_service_class,
        ):
            mock_service = MagicMock()
            mock_service.get_user_history = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            result = await verification_cog._rebuild_single_embed(
                guild=mock_guild,
                channel=mock_channel,
                request=mock_request,
                config=config,
            )

        assert result is True
        mock_message.edit.assert_called_once()

    async def test_preserves_screenshot_embeds(self, verification_cog: VerificationCog) -> None:
        """Probar que preserva los embeds de capturas de pantalla."""
        mock_member = MagicMock(spec=discord.Member)
        mock_member.mention = "<@456>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        main_embed = MagicMock()
        main_embed.description = "Usuario: Test\n⏳ Estado"
        main_embed.image = MagicMock()
        main_embed.image.url = None  # Main embed has no image

        screenshot_embed1 = MagicMock()
        screenshot_embed1.image = MagicMock()
        screenshot_embed1.image.url = "https://example.com/screenshot1.png"

        screenshot_embed2 = MagicMock()
        screenshot_embed2.image = MagicMock()
        screenshot_embed2.image.url = "https://example.com/screenshot2.png"

        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [main_embed, screenshot_embed1, screenshot_embed2]
        mock_message.edit = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_request = MagicMock()
        mock_request.id = 1
        mock_request.mod_message_id = 789
        mock_request.username = "TestUser"
        mock_request.user_id = 456
        mock_request.guild_id = 123
        mock_request.verification_type = VerificationType.ALLY
        mock_request.status = VerificationStatus.PENDING_REVIEW
        mock_request.created_at = datetime.now(UTC)
        mock_request.player_info = None

        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "sections": [{"type": "text", "content": "Usuario: {username}\n{status}"}]
            },
            ConfigKey.MOD_EMBED_ALLY: {
                "sections": [{"type": "text", "content": "Usuario: {username}\n{status}"}]
            },
            ConfigKey.STATUS_PENDING_REVIEW: "⏳ Pendiente",
            ConfigKey.ACCEPT_BUTTON_TEXT: "Aceptar",
            ConfigKey.REJECT_BUTTON_TEXT: "Rechazar",
        }

        # Mock database session for history lookup
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(verification_cog.bot.database, "session", return_value=mock_session),
            patch("discord_bot.verification.cog.VerificationService") as mock_service_class,
        ):
            mock_service = MagicMock()
            mock_service.get_user_history = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            result = await verification_cog._rebuild_single_embed(
                guild=mock_guild,
                channel=mock_channel,
                request=mock_request,
                config=config,
            )

        assert result is True
        call_args = mock_message.edit.call_args
        embeds = call_args.kwargs.get("embeds", [])
        assert len(embeds) == 3

    async def test_handles_empty_embeds(self, verification_cog: VerificationCog) -> None:
        """Probar que maneja mensajes sin embeds."""
        mock_member = MagicMock(spec=discord.Member)
        mock_member.mention = "<@456>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = []
        mock_message.edit = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_request = MagicMock()
        mock_request.id = 1
        mock_request.mod_message_id = 789
        mock_request.username = "TestUser"
        mock_request.user_id = 456
        mock_request.guild_id = 123
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.created_at = datetime.now(UTC)
        mock_request.player_info = None

        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "sections": [{"type": "text", "content": "Usuario: {username}\n{status}"}]
            },
            ConfigKey.MOD_EMBED_ALLY: {
                "sections": [{"type": "text", "content": "Usuario: {username}\n{status}"}]
            },
            ConfigKey.STATUS_AWAITING_SCREENSHOTS: "⏳ Esperando",
        }

        # Mock database session for history lookup
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(verification_cog.bot.database, "session", return_value=mock_session),
            patch("discord_bot.verification.cog.VerificationService") as mock_service_class,
        ):
            mock_service = MagicMock()
            mock_service.get_user_history = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            result = await verification_cog._rebuild_single_embed(
                guild=mock_guild,
                channel=mock_channel,
                request=mock_request,
                config=config,
            )

        assert result is True
        mock_message.edit.assert_called_once()


class TestRebuildPendingEmbedsForGuild:
    """Tests para _rebuild_pending_embeds_for_guild."""

    async def test_no_pending_for_guild(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que no hace nada si no hay verificaciones para el guild."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        await verification_cog._rebuild_pending_embeds_for_guild(mock_guild)

    async def test_rebuilds_only_guild_verifications(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que solo reconstruye verificaciones del guild especificado."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id,
                url1="https://cdn.discordapp.com/test1.png",
                url2="https://cdn.discordapp.com/test2.png",
                guild_name="Test Guild",
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)

            request2 = await service.create_request(
                guild_id=999,
                user_id=789,
                username="OtherUser",
                guild_name="Other Guild",
                verification_type=VerificationType.ALLY,
            )
            await service.update_screenshots(
                request_id=request2.id,
                url1="https://cdn.discordapp.com/other1.png",
                url2="https://cdn.discordapp.com/other2.png",
                guild_name="Other Guild",
            )
            await service.set_mod_message_id(request_id=request2.id, message_id=999)
            await session.commit()

        mock_member = MagicMock(spec=discord.Member)
        mock_member.mention = "<@456>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [MagicMock(description="Usuario: Test\n⏳ Pendiente")]
        mock_message.edit = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        config: dict[str, Any] = {
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 888,
            ConfigKey.MOD_EMBED_REGULAR: {
                "sections": [{"type": "text", "content": "Usuario: {username}\n{status}"}]
            },
            ConfigKey.MOD_EMBED_ALLY: {
                "sections": [{"type": "text", "content": "Usuario: {username}\n{status}"}]
            },
            ConfigKey.STATUS_PENDING_REVIEW: "⏳ Pendiente",
            ConfigKey.ACCEPT_BUTTON_TEXT: "Aceptar",
            ConfigKey.REJECT_BUTTON_TEXT: "Rechazar",
        }

        with patch.object(
            ConfigService,
            "get_all_config",
            new_callable=AsyncMock,
            return_value=config,
        ):
            await verification_cog._rebuild_pending_embeds_for_guild(mock_guild)

        mock_message.edit.assert_called_once()

    async def test_skips_no_mod_channel_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que no hace nada si no hay canal de mod configurado."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id,
                url1="https://cdn.discordapp.com/test1.png",
                url2="https://cdn.discordapp.com/test2.png",
                guild_name="Test Guild",
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)
            await session.commit()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        with patch.object(
            ConfigService,
            "get_all_config",
            new_callable=AsyncMock,
            return_value={},  # Sin MOD_NOTIFICATION_CHANNEL
        ):
            await verification_cog._rebuild_pending_embeds_for_guild(mock_guild)

    async def test_skips_invalid_mod_channel(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que no hace nada si el canal de mod no es válido."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id,
                url1="https://cdn.discordapp.com/test1.png",
                url2="https://cdn.discordapp.com/test2.png",
                guild_name="Test Guild",
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)
            await session.commit()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=None)

        with patch.object(
            ConfigService,
            "get_all_config",
            new_callable=AsyncMock,
            return_value={ConfigKey.MOD_NOTIFICATION_CHANNEL: 888},
        ):
            await verification_cog._rebuild_pending_embeds_for_guild(mock_guild)

    async def test_handles_rebuild_error(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar que continúa si falla la reconstrucción de un embed."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id,
                url1="https://cdn.discordapp.com/test1.png",
                url2="https://cdn.discordapp.com/test2.png",
                guild_name="Test Guild",
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)
            await session.commit()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(side_effect=Exception("Discord API error"))
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        with patch.object(
            ConfigService,
            "get_all_config",
            new_callable=AsyncMock,
            return_value={ConfigKey.MOD_NOTIFICATION_CHANNEL: 888},
        ):
            await verification_cog._rebuild_pending_embeds_for_guild(mock_guild)


class TestOnConfigChangedModEmbed:
    """Tests para on_config_changed con claves de embed de moderación."""

    async def test_rebuilds_on_mod_embed_color_change(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que reconstruye embeds al cambiar color."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        with patch.object(
            verification_cog,
            "_rebuild_pending_embeds_for_guild",
            new_callable=AsyncMock,
        ) as mock_rebuild:
            await verification_cog.on_config_changed(mock_guild, [ConfigKey.MOD_EMBED_REGULAR])
            mock_rebuild.assert_called_once_with(mock_guild)

    async def test_rebuilds_on_mod_embed_icon_change(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que reconstruye embeds al cambiar icono."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        with patch.object(
            verification_cog,
            "_rebuild_pending_embeds_for_guild",
            new_callable=AsyncMock,
        ) as mock_rebuild:
            await verification_cog.on_config_changed(mock_guild, [ConfigKey.MOD_EMBED_ALLY])
            mock_rebuild.assert_called_once_with(mock_guild)

    async def test_rebuilds_on_accept_button_change(
        self, verification_cog: VerificationCog
    ) -> None:
        """Probar que reconstruye embeds al cambiar texto del botón."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        with patch.object(
            verification_cog,
            "_rebuild_pending_embeds_for_guild",
            new_callable=AsyncMock,
        ) as mock_rebuild:
            await verification_cog.on_config_changed(mock_guild, [ConfigKey.ACCEPT_BUTTON_TEXT])
            mock_rebuild.assert_called_once_with(mock_guild)

    async def test_no_rebuild_on_unrelated_key(self, verification_cog: VerificationCog) -> None:
        """Probar que no reconstruye con claves no relacionadas."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        with patch.object(
            verification_cog,
            "_rebuild_pending_embeds_for_guild",
            new_callable=AsyncMock,
        ) as mock_rebuild:
            await verification_cog.on_config_changed(mock_guild, ["some_unrelated_key"])
            mock_rebuild.assert_not_called()
