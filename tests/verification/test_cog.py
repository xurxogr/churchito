"""Tests para VerificationCog."""

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


@pytest.fixture
def mock_discord_bot(test_database: DatabaseService) -> MagicMock:
    """Crear mock del bot con database."""
    bot = MagicMock(spec=DiscordBot)
    bot.database = test_database
    bot.guilds = []
    bot.add_view = MagicMock()
    bot.get_guild = MagicMock(return_value=None)
    bot.wait_until_ready = AsyncMock()
    return bot


@pytest.fixture
def verification_cog(mock_discord_bot: MagicMock) -> VerificationCog:
    """Crear instancia del cog para tests."""
    return VerificationCog(mock_discord_bot)


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

        await verification_cog.handle_verification_start(interaction, VerificationType.REGULAR)

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

        await verification_cog.handle_accept(interaction, 1)

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

        await verification_cog.handle_reject(interaction, 1, "motivo")

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

        await verification_cog.show_rejection_select(interaction, 1)

        interaction.response.send_message.assert_not_called()

    async def test_with_configured_reasons(self, verification_cog: VerificationCog) -> None:
        """Probar con motivos configurados."""
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

            await verification_cog.show_rejection_select(interaction, 1)

            interaction.response.send_message.assert_called_once()
            call_kwargs = interaction.response.send_message.call_args[1]
            assert call_kwargs["ephemeral"] is True
            assert call_kwargs["view"] is not None

    async def test_with_no_configured_reasons(self, verification_cog: VerificationCog) -> None:
        """Probar sin motivos configurados - usa defaults."""
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

            await verification_cog.show_rejection_select(interaction, 1)

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

            await verification_cog.show_rejection_select(interaction, 1)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "No tienes permisos" in call_args[1]["content"]
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

    async def test_ignores_user_without_pending(self, verification_cog: VerificationCog) -> None:
        """Probar que ignora usuarios sin verificacion pendiente."""
        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 999

        await verification_cog.on_message(message)

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
        attachment1.url = "http://example.com/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "http://example.com/2.jpg"
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
            assert updated.screenshot_1_url == "http://example.com/1.png"
            assert updated.screenshot_2_url == "http://example.com/2.jpg"


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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request.id, "http://example.com/1.png", "http://example.com/2.png"
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

            await verification_cog.handle_accept(interaction, request_id)

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
            await service.approve(request.id, 111, "OtherMod")
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

            await verification_cog.handle_accept(interaction, request_id)

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
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
        """Probar health check sin canal configurado."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        # No deberia fallar
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

        with patch.object(
            verification_cog, "_check_verification_message", new_callable=AsyncMock
        ) as mock_check:
            await verification_cog._run_health_check()

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

        with patch.object(
            verification_cog, "_check_verification_message", new_callable=AsyncMock
        ) as mock_check:
            # Primer guild falla, segundo deberia continuar
            mock_check.side_effect = [Exception("Error"), None]

            await verification_cog._run_health_check()

            # Ambos fueron llamados
            assert mock_check.call_count == 2

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
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await session.commit()

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
        """Probar health check con permisos denegados."""
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
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        # No deberia fallar
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
            assert "deshabilitada" in call_kwargs["content"]

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

            await verification_cog.handle_verification_start(interaction, VerificationType.REGULAR)

            # DM enviado
            mock_user.send.assert_called_once()
            # Mensaje a mods enviado
            mock_mod_channel.send.assert_called_once()
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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
            await service.set_mod_message_id(request.id, 777)
            await session.commit()
            request_id = request.id

        pending_status = "🔍 **Estado:** Pendiente de revision"

        mock_mod_message = MagicMock()
        mock_mod_message.content = f"Solicitud\n\n{pending_status}"
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
            assert "Aprobado" in edit_kwargs["content"]
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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
            await service.set_mod_message_id(request.id, 777)
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
            await verification_cog.handle_accept(interaction, request_id)

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
            await service.set_mod_message_id(request.id, 777)
            await session.commit()
            request_id = request.id

        pending_status = "🔍 **Estado:** Pendiente de revision"

        mock_mod_message = MagicMock()
        mock_mod_message.content = f"Solicitud\n\n{pending_status}"
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
            assert "Rechazado" in edit_kwargs["content"]
            assert "Capturas invalidas" in edit_kwargs["content"]


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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(old_request.id, "old1", "old2")
            await service.approve(old_request.id, 111, "OldMod")

            # Solicitud actual
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                verification_type=VerificationType.ALLY,
            )
            await service.update_screenshots(request.id, "url1", "url2")
            await service.set_mod_message_id(request.id, 777)
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
            # Debe incluir historial
            assert "Historial" in edit_kwargs["content"]

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
            await service.set_mod_message_id(request.id, 777)
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
        attachment1.url = "http://example.com/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "http://example.com/2.jpg"
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
                verification_type=VerificationType.ALLY,
            )
            await service.update_screenshots(request.id, "url1", "url2")
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

            await verification_cog.handle_accept(interaction, request_id)

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
            await service.set_mod_message_id(request.id, 777)
            await session.commit()
            request_id = request.id

        # Mensaje sin "Pendiente de revision"
        mock_mod_message = MagicMock()
        mock_mod_message.content = "Solicitud de verificacion"
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
            # Debe añadir al final
            assert "Solicitud de verificacion" in edit_kwargs["content"]
            assert "Aprobado" in edit_kwargs["content"]

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
            await service.set_mod_message_id(request.id, 777)
            await session.commit()
            request_id = request.id

        # Mensaje sin "Pendiente de revision"
        mock_mod_message = MagicMock()
        mock_mod_message.content = "Solicitud de verificacion"
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
            # Debe añadir al final
            assert "Solicitud de verificacion" in edit_kwargs["content"]
            assert "Rechazado" in edit_kwargs["content"]
            assert "Motivo test" in edit_kwargs["content"]


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

            await verification_cog.handle_reject(interaction, 99999, "motivo")

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
            await service.reject(request.id, 111, "OtherMod", "Ya rechazada")
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

            await verification_cog.handle_reject(interaction, request_id, "motivo")

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
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
            await verification_cog.handle_reject(interaction, request_id, "Capturas invalidas")

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
            await service.set_mod_message_id(request.id, 777)
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
            await verification_cog.handle_reject(interaction, request_id, "Capturas invalidas")

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
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request.id, 777)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.edit = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

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
        attachment1.url = "http://example.com/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "http://example.com/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, object] = {
            "screenshots_received_message": "Capturas recibidas",
            "mod_notification_channel": 888,
            "mod_message_template": "Verificacion de {username}",
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Aliado",
            "accept_button_text": "Aceptar",
            "reject_button_text": "Rechazar",
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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
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
            await verification_cog.on_config_changed(mock_guild, "verification_channel")

            mock_check.assert_called_once_with(guild=mock_guild, force=True)

    async def test_ignores_irrelevant_key(self, verification_cog: VerificationCog) -> None:
        """Probar que ignora claves no relacionadas con el panel."""
        mock_guild = MagicMock(spec=discord.Guild)

        with patch.object(
            verification_cog, "_check_verification_message", new_callable=AsyncMock
        ) as mock_check:
            await verification_cog.on_config_changed(mock_guild, "some_other_key")

            mock_check.assert_not_called()


class TestCheckVerificationMessageForce:
    """Tests para _check_verification_message con force=True."""

    async def test_no_channel_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Probar cuando no hay canal configurado."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        with patch(
            "discord_bot.verification.cog.delete_message", new_callable=AsyncMock
        ) as mock_delete:
            await verification_cog._check_verification_message(guild=mock_guild, force=True)

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
            await verification_cog._check_verification_message(guild=mock_guild, force=True)

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
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "_panel_message_id", 777)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        with (
            patch(
                "discord_bot.verification.cog.delete_message", new_callable=AsyncMock
            ) as mock_delete,
            patch.object(
                verification_cog, "_create_verification_message", new_callable=AsyncMock
            ) as mock_create,
        ):
            await verification_cog._check_verification_message(guild=mock_guild, force=True)

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
            assert "Deshabilitado" in call_kwargs["content"]

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

            await verification_cog.handle_verification_start(interaction, VerificationType.REGULAR)

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args
            assert "deshabilitada" in args[0][0]

    async def test_already_verified_regular(self, verification_cog: VerificationCog) -> None:
        """Probar inicio cuando usuario ya esta verificado (regular)."""
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
        """Probar inicio cuando usuario ya esta verificado (aliado)."""
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

            mock_check.assert_called_once_with(guild=guild, force=True)

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
            await verification_cog._check_verification_message(guild, force=False)

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

            await verification_cog.handle_verification_start(interaction, VerificationType.REGULAR)

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

            await verification_cog.handle_verification_start(interaction, VerificationType.REGULAR)

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(old_request.id, "url1", "url2")
            await service.reject(old_request.id, 789, "ModUser", "Capturas incorrectas")
            await session.commit()

        # Crear nueva verificacion con mod_message_id
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url3", "url4")
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
            content = call_args.kwargs["content"]
            assert "Capturas incorrectas" in content


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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
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

            await verification_cog.handle_accept(interaction, request_id)

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
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

            await verification_cog.handle_accept(interaction, request_id)

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
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

            await verification_cog.handle_accept(interaction, request_id)

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

            await verification_cog.handle_reject(interaction, request_id=1, reason="Test")

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
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(request.id, "url1", "url2")
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
