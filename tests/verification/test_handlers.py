"""Tests para handlers de verificación."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_bot.verification.handlers import (
    _create_screenshot_embeds,
    _get_api_error_message,
    _is_valid_discord_url,
    _replace_status_in_content,
    _send_mod_ping_message,
    _update_mod_message_for_review,
    _update_status_ready_for_approval,
    update_mod_message_cancelled,
)
from discord_bot.verification.models import VerificationRequest


class TestIsValidDiscordUrl:
    """Tests para _is_valid_discord_url."""

    def test_valid_cdn_url(self) -> None:
        """Probar URL válida de cdn.discordapp.com."""
        url = "https://cdn.discordapp.com/attachments/123/456/image.png"
        assert _is_valid_discord_url(url) is True

    def test_valid_media_url(self) -> None:
        """Probar URL válida de media.discordapp.net."""
        url = "https://media.discordapp.net/attachments/123/456/image.png"
        assert _is_valid_discord_url(url) is True

    def test_empty_url(self) -> None:
        """Probar que URL vacía retorna False."""
        assert _is_valid_discord_url("") is False

    def test_http_url(self) -> None:
        """Probar que URL HTTP (no HTTPS) retorna False."""
        url = "http://cdn.discordapp.com/attachments/123/456/image.png"
        assert _is_valid_discord_url(url) is False

    def test_wrong_domain(self) -> None:
        """Probar que dominio incorrecto retorna False."""
        url = "https://example.com/image.png"
        assert _is_valid_discord_url(url) is False

    def test_malicious_url(self) -> None:
        """Probar que URL maliciosa retorna False."""
        url = "https://evil.com/cdn.discordapp.com/image.png"
        assert _is_valid_discord_url(url) is False

    def test_subdomain_attack(self) -> None:
        """Probar que subdominio malicioso retorna False."""
        url = "https://cdn.discordapp.com.evil.com/image.png"
        assert _is_valid_discord_url(url) is False

    def test_url_with_query_params(self) -> None:
        """Probar URL válida con query params."""
        url = "https://cdn.discordapp.com/attachments/123/456/image.png?size=128"
        assert _is_valid_discord_url(url) is True

    def test_url_too_short_for_parsing(self) -> None:
        """Probar URL demasiado corta que podría causar IndexError."""
        # URL que empieza con https:// pero no tiene dominio
        url = "https://"
        assert _is_valid_discord_url(url) is False

    def test_url_with_only_domain(self) -> None:
        """Probar URL con solo dominio sin path."""
        url = "https://cdn.discordapp.com"
        assert _is_valid_discord_url(url) is True


class TestCreateScreenshotEmbeds:
    """Tests para _create_screenshot_embeds."""

    def test_creates_two_embeds_for_two_urls(self) -> None:
        """Probar que crea dos embeds para dos URLs."""
        url1 = "https://cdn.discordapp.com/attachments/123/456/1.png"
        url2 = "https://cdn.discordapp.com/attachments/123/456/2.png"

        embeds = _create_screenshot_embeds(url1=url1, url2=url2)

        assert len(embeds) == 2
        assert embeds[0].image.url == url1
        assert embeds[1].image.url == url2

    def test_creates_one_embed_for_one_url(self) -> None:
        """Probar que crea un embed si solo hay una URL."""
        url1 = "https://cdn.discordapp.com/attachments/123/456/1.png"

        embeds = _create_screenshot_embeds(url1=url1, url2=None)

        assert len(embeds) == 1
        assert embeds[0].image.url == url1

    def test_creates_empty_list_for_no_urls(self) -> None:
        """Probar que retorna lista vacía si no hay URLs."""
        embeds = _create_screenshot_embeds(url1=None, url2=None)

        assert len(embeds) == 0

    def test_skips_none_url(self) -> None:
        """Probar que salta URL None."""
        url2 = "https://cdn.discordapp.com/attachments/123/456/2.png"

        embeds = _create_screenshot_embeds(url1=None, url2=url2)

        assert len(embeds) == 1
        assert embeds[0].image.url == url2


class TestGetApiErrorMessage:
    """Tests para _get_api_error_message."""

    def test_401_unauthorized(self) -> None:
        """Probar mensaje para 401."""
        result = _get_api_error_message(401)
        assert result == "API key required or invalid"

    def test_413_too_large(self) -> None:
        """Probar mensaje para 413."""
        result = _get_api_error_message(413)
        assert result == "Image exceeds maximum upload size"

    def test_422_not_in_error_messages(self) -> None:
        """Probar que 422 no está en API_ERROR_MESSAGES (se maneja por separado)."""
        # 422 is handled separately as "invalid images", not as an API error
        result = _get_api_error_message(422)
        assert result == "API Error (code: 422)"

    def test_429_rate_limit(self) -> None:
        """Probar mensaje para 429."""
        result = _get_api_error_message(429)
        assert result == "Rate limit exceeded"

    def test_500_internal_error(self) -> None:
        """Probar mensaje para 500."""
        result = _get_api_error_message(500)
        assert result == "Internal processing error"

    def test_unknown_status_code(self) -> None:
        """Probar mensaje para código desconocido."""
        result = _get_api_error_message(418)
        assert result == "API Error (code: 418)"


class TestUpdateStatusReadyForApproval:
    """Tests para _update_status_ready_for_approval."""

    def test_replaces_status_with_roles(self) -> None:
        """Probar que reemplaza el estado con los roles de moderador."""
        mock_role = MagicMock(spec=discord.Role)
        mock_role.mention = "<@&123>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        config = {
            "mod_roles": [123],
            "status_pending_review": "🔍 Pendiente",
            "status_ready_for_approval": "✅ Listo - {roles}",
        }

        formatted = "Mensaje\n\n🔍 Pendiente\n\nMás info"

        result = _update_status_ready_for_approval(
            formatted=formatted,
            config=config,
            guild=mock_guild,
        )

        assert "✅ Listo - <@&123>" in result
        assert "🔍 Pendiente" not in result

    def test_multiple_roles(self) -> None:
        """Probar con múltiples roles de moderador."""
        mock_role1 = MagicMock(spec=discord.Role)
        mock_role1.mention = "<@&111>"
        mock_role2 = MagicMock(spec=discord.Role)
        mock_role2.mention = "<@&222>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_role = MagicMock(side_effect=[mock_role1, mock_role2])

        config = {
            "mod_roles": [111, 222],
            "status_pending_review": "🔍 Pendiente",
            "status_ready_for_approval": "✅ Listo - {roles}",
        }

        formatted = "Mensaje\n\n🔍 Pendiente"

        result = _update_status_ready_for_approval(
            formatted=formatted,
            config=config,
            guild=mock_guild,
        )

        assert "<@&111>" in result
        assert "<@&222>" in result

    def test_no_mod_roles_uses_default(self) -> None:
        """Probar que usa 'moderadores' si no hay roles configurados."""
        mock_guild = MagicMock(spec=discord.Guild)

        config = {
            "mod_roles": [],
            "status_pending_review": "🔍 Pendiente",
            "status_ready_for_approval": "✅ Listo - {roles}",
        }

        formatted = "Mensaje\n\n🔍 Pendiente"

        result = _update_status_ready_for_approval(
            formatted=formatted,
            config=config,
            guild=mock_guild,
        )

        assert "✅ Listo - moderadores" in result

    def test_role_not_found_skipped(self) -> None:
        """Probar que roles no encontrados se saltan."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_role = MagicMock(return_value=None)

        config = {
            "mod_roles": [999],
            "status_pending_review": "🔍 Pendiente",
            "status_ready_for_approval": "✅ Listo - {roles}",
        }

        formatted = "Mensaje\n\n🔍 Pendiente"

        result = _update_status_ready_for_approval(
            formatted=formatted,
            config=config,
            guild=mock_guild,
        )

        # Sin roles válidos, usa "moderadores"
        assert "✅ Listo - moderadores" in result

    def test_returns_unchanged_when_no_pending_status(self) -> None:
        """Probar que retorna sin cambios si no hay estado pendiente configurado."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_role = MagicMock(return_value=None)

        config = {
            "mod_roles": [],
            "status_pending_review": "",  # Vacío
            "status_ready_for_approval": "✅ Listo - {roles}",
        }

        formatted = "Mensaje original"

        result = _update_status_ready_for_approval(
            formatted=formatted,
            config=config,
            guild=mock_guild,
        )

        # Retorna sin cambios
        assert result == formatted

    def test_returns_unchanged_when_no_ready_status(self) -> None:
        """Probar que retorna sin cambios si no hay estado listo configurado."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_role = MagicMock(return_value=None)

        config = {
            "mod_roles": [],
            "status_pending_review": "🔍 Pendiente",
            "status_ready_for_approval": "",  # Vacío
        }

        formatted = "Mensaje\n\n🔍 Pendiente"

        result = _update_status_ready_for_approval(
            formatted=formatted,
            config=config,
            guild=mock_guild,
        )

        # Retorna sin cambios
        assert result == formatted


class TestUpdateModMessageForReview:
    """Tests para _update_mod_message_for_review."""

    @pytest.mark.asyncio
    async def test_returns_early_when_no_mod_message_id(self) -> None:
        """Probar que retorna si no hay mod_message_id."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_request = MagicMock()
        mock_request.mod_message_id = None

        config: dict[str, Any] = {}

        # No debería fallar, solo retornar
        await _update_mod_message_for_review(mock_guild, mock_request, config, 123)

    @pytest.mark.asyncio
    async def test_returns_early_when_no_mod_channel_id(self) -> None:
        """Probar que retorna si no hay canal de moderación configurado."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_request = MagicMock()
        mock_request.mod_message_id = 999

        config: dict[str, Any] = {
            "mod_notification_channel": None,
        }

        await _update_mod_message_for_review(mock_guild, mock_request, config, 123)

    @pytest.mark.asyncio
    async def test_returns_early_when_channel_not_found(self) -> None:
        """Probar que retorna si el canal no existe."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=None)

        mock_request = MagicMock()
        mock_request.mod_message_id = 999

        config: dict[str, Any] = {
            "mod_notification_channel": 888,
        }

        await _update_mod_message_for_review(mock_guild, mock_request, config, 123)

    @pytest.mark.asyncio
    async def test_returns_early_when_channel_wrong_type(self) -> None:
        """Probar que retorna si el canal no es TextChannel."""
        mock_channel = MagicMock(spec=discord.VoiceChannel)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        mock_request = MagicMock()
        mock_request.mod_message_id = 999

        config: dict[str, Any] = {
            "mod_notification_channel": 888,
        }

        await _update_mod_message_for_review(mock_guild, mock_request, config, 123)

    @pytest.mark.asyncio
    async def test_handles_message_not_found(self) -> None:
        """Probar que maneja NotFound al buscar el mensaje."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        mock_request = MagicMock()
        mock_request.mod_message_id = 999

        config: dict[str, Any] = {
            "mod_notification_channel": 888,
        }

        # No debería fallar
        await _update_mod_message_for_review(mock_guild, mock_request, config, 123)


class TestReplaceStatusInContent:
    """Tests para _replace_status_in_content."""

    def test_replaces_pending_review_status(self) -> None:
        """Probar que reemplaza STATUS_PENDING_REVIEW."""
        config = {
            "status_pending_review": "🔍 Pendiente",
            "status_ready_for_approval": "✅ Listo - {roles}",
        }
        content = "Mensaje\n\n🔍 Pendiente\n\nMás info"
        new_status = "✅ Aprobado"

        result = _replace_status_in_content(content, new_status, config)

        assert "✅ Aprobado" in result
        assert "🔍 Pendiente" not in result

    def test_replaces_ready_for_approval_status_with_roles(self) -> None:
        """Probar que reemplaza STATUS_READY_FOR_APPROVAL con menciones de roles."""
        config = {
            "status_pending_review": "🔍 Pendiente",
            "status_ready_for_approval": "✅ Listo - {roles}",
        }
        # El contenido tiene el estado con roles ya formateados
        content = "Mensaje\n\n✅ Listo - <@&123>, <@&456>\n\nMás info"
        new_status = "✅ Aprobado por moderador"

        result = _replace_status_in_content(content, new_status, config)

        assert "✅ Aprobado por moderador" in result
        assert "✅ Listo - <@&123>" not in result

    def test_appends_when_no_status_found(self) -> None:
        """Probar que añade al final si no hay estado conocido."""
        config = {
            "status_pending_review": "🔍 Pendiente",
            "status_ready_for_approval": "✅ Listo - {roles}",
        }
        content = "Mensaje sin estado"
        new_status = "✅ Aprobado"

        result = _replace_status_in_content(content, new_status, config)

        assert result == "Mensaje sin estado\n\n✅ Aprobado"

    def test_handles_empty_config(self) -> None:
        """Probar con configuración vacía."""
        config: dict[str, Any] = {}
        content = "Mensaje"
        new_status = "✅ Aprobado"

        result = _replace_status_in_content(content, new_status, config)

        assert result == "Mensaje\n\n✅ Aprobado"

    def test_handles_template_without_roles_placeholder(self) -> None:
        """Probar con template sin {roles}."""
        config = {
            "status_pending_review": "🔍 Pendiente",
            "status_ready_for_approval": "✅ Listo para aprobar",  # Sin {roles}
        }
        content = "Mensaje\n\n🔍 Pendiente"
        new_status = "✅ Aprobado"

        result = _replace_status_in_content(content, new_status, config)

        assert "✅ Aprobado" in result

    def test_handles_template_starting_with_placeholder(self) -> None:
        """Probar con template que empieza con placeholder (sin prefijo)."""
        config = {
            "status_pending_review": "{placeholder} Pendiente",  # Empieza con {
            "status_ready_for_approval": "",
        }
        content = "Mensaje sin estado"
        new_status = "✅ Aprobado"

        result = _replace_status_in_content(content, new_status, config)

        # Debe añadir al final porque no puede extraer prefijo
        assert result == "Mensaje sin estado\n\n✅ Aprobado"

    def test_replaces_awaiting_screenshots_status(self) -> None:
        """Probar que reemplaza STATUS_AWAITING_SCREENSHOTS."""
        config = {
            "status_awaiting_screenshots": "⏳ Esperando capturas...",
            "status_pending_review": "🔍 Pendiente",
            "status_ready_for_approval": "✅ Listo - {roles}",
        }
        content = "Mensaje\n\n⏳ Esperando capturas...\n\nMás info"
        new_status = "🚫 Cancelado"

        result = _replace_status_in_content(content, new_status, config)

        assert "🚫 Cancelado" in result
        assert "⏳ Esperando capturas..." not in result


class TestUpdateModMessageCancelled:
    """Tests para update_mod_message_cancelled."""

    @pytest.mark.asyncio
    async def test_returns_early_if_no_mod_message_id(self) -> None:
        """Probar que retorna si no hay mod_message_id."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_request = MagicMock(spec=VerificationRequest)
        mock_request.mod_message_id = None

        # No debe hacer nada
        await update_mod_message_cancelled(mock_guild, mock_request, {})

        mock_guild.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_no_mod_channel_config(self) -> None:
        """Probar que retorna si no hay canal de moderación configurado."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_request = MagicMock(spec=VerificationRequest)
        mock_request.mod_message_id = 123

        await update_mod_message_cancelled(mock_guild, mock_request, {})

        mock_guild.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_early_if_channel_not_found(self) -> None:
        """Probar que retorna si el canal no existe."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=None)
        mock_request = MagicMock(spec=VerificationRequest)
        mock_request.mod_message_id = 123

        config = {"mod_notification_channel": 456}

        await update_mod_message_cancelled(mock_guild, mock_request, config)

        mock_guild.get_channel.assert_called_once_with(456)

    @pytest.mark.asyncio
    async def test_deletes_message_if_configured(self) -> None:
        """Probar que elimina el mensaje si DELETE_PROCESSED_MESSAGES está activo."""
        mock_message = MagicMock(spec=discord.Message)
        mock_message.delete = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        mock_request = MagicMock(spec=VerificationRequest)
        mock_request.mod_message_id = 123

        config = {
            "mod_notification_channel": 456,
            "delete_processed_messages": True,
        }

        await update_mod_message_cancelled(mock_guild, mock_request, config)

        mock_message.delete.assert_called_once()
        mock_message.edit.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_message_with_cancelled_status(self) -> None:
        """Probar que actualiza el mensaje con estado cancelado."""
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.description = "Usuario: Test\n\n⏳ Esperando capturas..."

        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [mock_embed]
        mock_message.edit = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        mock_request = MagicMock(spec=VerificationRequest)
        mock_request.mod_message_id = 123
        mock_request.username = "TestUser"
        mock_request.user_id = 789

        config = {
            "mod_notification_channel": 456,
            "delete_processed_messages": False,
            "status_awaiting_screenshots": "⏳ Esperando capturas...",
            "status_cancelled": "🚫 Cancelado",
        }

        await update_mod_message_cancelled(mock_guild, mock_request, config)

        mock_message.edit.assert_called_once()
        call_kwargs = mock_message.edit.call_args[1]
        assert call_kwargs["view"] is None
        assert len(call_kwargs["embeds"]) >= 1

    @pytest.mark.asyncio
    async def test_handles_message_not_found(self) -> None:
        """Probar que maneja cuando el mensaje no existe."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        mock_request = MagicMock(spec=VerificationRequest)
        mock_request.mod_message_id = 123

        config = {"mod_notification_channel": 456}

        # No debe lanzar excepción
        await update_mod_message_cancelled(mock_guild, mock_request, config)


class TestSendModPingMessage:
    """Tests para _send_mod_ping_message."""

    @pytest.mark.asyncio
    async def test_sends_ping_message_with_roles(self) -> None:
        """Probar que envía mensaje con menciones de roles."""
        mock_role = MagicMock(spec=discord.Role)
        mock_role.mention = "<@&123>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.guild = mock_guild
        mock_channel.send = AsyncMock()

        config = {
            "mod_ping_message": "{roles} - Nueva verificación",
            "mod_roles": [123],
        }

        await _send_mod_ping_message(mock_channel, config)

        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args
        assert "<@&123> - Nueva verificación" in call_args.kwargs["content"]

    @pytest.mark.asyncio
    async def test_does_not_send_when_no_template(self) -> None:
        """Probar que no envía si no hay template configurado."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()

        config: dict[str, Any] = {
            "mod_ping_message": "",
            "mod_roles": [123],
        }

        await _send_mod_ping_message(mock_channel, config)

        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_send_when_no_roles(self) -> None:
        """Probar que no envía si no hay roles configurados."""
        mock_guild = MagicMock(spec=discord.Guild)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.guild = mock_guild
        mock_channel.send = AsyncMock()

        config = {
            "mod_ping_message": "{roles} - Nueva verificación",
            "mod_roles": [],
        }

        await _send_mod_ping_message(mock_channel, config)

        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_send_when_roles_not_found(self) -> None:
        """Probar que no envía si los roles no existen en el guild."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_role = MagicMock(return_value=None)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.guild = mock_guild
        mock_channel.send = AsyncMock()

        config = {
            "mod_ping_message": "{roles} - Nueva verificación",
            "mod_roles": [999],
        }

        await _send_mod_ping_message(mock_channel, config)

        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_with_multiple_roles(self) -> None:
        """Probar que envía con múltiples roles."""
        mock_role1 = MagicMock(spec=discord.Role)
        mock_role1.mention = "<@&111>"
        mock_role2 = MagicMock(spec=discord.Role)
        mock_role2.mention = "<@&222>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.get_role = MagicMock(side_effect=[mock_role1, mock_role2])

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.guild = mock_guild
        mock_channel.send = AsyncMock()

        config = {
            "mod_ping_message": "{roles} - Pendiente",
            "mod_roles": [111, 222],
        }

        await _send_mod_ping_message(mock_channel, config)

        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args
        assert "<@&111>" in call_args.kwargs["content"]
        assert "<@&222>" in call_args.kwargs["content"]
