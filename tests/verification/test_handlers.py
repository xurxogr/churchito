"""Tests para handlers de verificación."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_bot.common.utils import is_valid_discord_cdn_url
from discord_bot.verification.enums import ConfigKey, VerificationStatus, VerificationType
from discord_bot.verification.handlers import (
    update_mod_message_cancelled,
    update_mod_message_for_manual_review,
    update_tracker_message,
)
from discord_bot.verification.handlers.auto_processing import send_mod_ping_message
from discord_bot.verification.handlers.utils import (
    calculate_expires_timestamp,
    create_screenshot_embeds,
    get_api_error_message,
)
from discord_bot.verification.models import VerificationRequest


class TestCalculateExpiresTimestamp:
    """Tests para calculate_expires_timestamp."""

    def test_returns_empty_string_when_timeout_is_zero(self) -> None:
        """Probar que retorna cadena vacía cuando timeout es 0."""
        created_at = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
        result = calculate_expires_timestamp(created_at, 0)
        assert result == ""

    def test_returns_empty_string_when_timeout_is_negative(self) -> None:
        """Probar que retorna cadena vacía cuando timeout es negativo."""
        created_at = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
        result = calculate_expires_timestamp(created_at, -5)
        assert result == ""

    def test_returns_relative_timestamp_format(self) -> None:
        """Probar que retorna formato de timestamp relativo de Discord."""
        created_at = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
        result = calculate_expires_timestamp(created_at, 60)

        # Verificar que tiene el formato correcto <t:TIMESTAMP:R>
        assert result.startswith("<t:")
        assert result.endswith(":R>")

    def test_calculates_correct_expiration_time(self) -> None:
        """Probar que calcula el tiempo de expiración correcto."""
        created_at = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
        timeout_minutes = 60

        result = calculate_expires_timestamp(created_at, timeout_minutes)

        # Extraer el timestamp del resultado
        timestamp_str = result[3:-3]  # Quitar "<t:" y ":R>"
        timestamp = int(timestamp_str)

        # Calcular el timestamp esperado (created_at + 60 minutos)
        expected_timestamp = int(created_at.timestamp()) + (60 * 60)

        assert timestamp == expected_timestamp

    def test_works_with_different_timeout_values(self) -> None:
        """Probar con diferentes valores de timeout."""
        created_at = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
        base_timestamp = int(created_at.timestamp())

        # 5 minutos
        result_5 = calculate_expires_timestamp(created_at, 5)
        timestamp_5 = int(result_5[3:-3])
        assert timestamp_5 == base_timestamp + (5 * 60)

        # 30 minutos
        result_30 = calculate_expires_timestamp(created_at, 30)
        timestamp_30 = int(result_30[3:-3])
        assert timestamp_30 == base_timestamp + (30 * 60)

        # 1440 minutos (24 horas)
        result_1440 = calculate_expires_timestamp(created_at, 1440)
        timestamp_1440 = int(result_1440[3:-3])
        assert timestamp_1440 == base_timestamp + (1440 * 60)


class TestIsValidDiscordUrl:
    """Tests para is_valid_discord_cdn_url."""

    def test_valid_cdn_url(self) -> None:
        """Probar URL válida de cdn.discordapp.com."""
        url = "https://cdn.discordapp.com/attachments/123/456/image.png"
        assert is_valid_discord_cdn_url(url) is True

    def test_valid_media_url(self) -> None:
        """Probar URL válida de media.discordapp.net."""
        url = "https://media.discordapp.net/attachments/123/456/image.png"
        assert is_valid_discord_cdn_url(url) is True

    def test_empty_url(self) -> None:
        """Probar que URL vacía retorna False."""
        assert is_valid_discord_cdn_url("") is False

    def test_http_url(self) -> None:
        """Probar que URL HTTP (no HTTPS) retorna False."""
        url = "http://cdn.discordapp.com/attachments/123/456/image.png"
        assert is_valid_discord_cdn_url(url) is False

    def test_wrong_domain(self) -> None:
        """Probar que dominio incorrecto retorna False."""
        url = "https://example.com/image.png"
        assert is_valid_discord_cdn_url(url) is False

    def test_malicious_url(self) -> None:
        """Probar que URL maliciosa retorna False."""
        url = "https://evil.com/cdn.discordapp.com/image.png"
        assert is_valid_discord_cdn_url(url) is False

    def test_subdomain_attack(self) -> None:
        """Probar que subdominio malicioso retorna False."""
        url = "https://cdn.discordapp.com.evil.com/image.png"
        assert is_valid_discord_cdn_url(url) is False

    def test_url_with_query_params(self) -> None:
        """Probar URL válida con query params."""
        url = "https://cdn.discordapp.com/attachments/123/456/image.png?size=128"
        assert is_valid_discord_cdn_url(url) is True

    def test_url_too_short_for_parsing(self) -> None:
        """Probar URL demasiado corta que podría causar IndexError."""
        # URL que empieza con https:// pero no tiene dominio
        url = "https://"
        assert is_valid_discord_cdn_url(url) is False

    def test_url_with_only_domain(self) -> None:
        """Probar URL con solo dominio sin path."""
        url = "https://cdn.discordapp.com"
        assert is_valid_discord_cdn_url(url) is True


class TestCreateScreenshotEmbeds:
    """Tests para create_screenshot_embeds."""

    def test_creates_two_embeds_for_two_urls(self) -> None:
        """Probar que crea dos embeds para dos URLs."""
        url1 = "https://cdn.discordapp.com/attachments/123/456/1.png"
        url2 = "https://cdn.discordapp.com/attachments/123/456/2.png"

        embeds = create_screenshot_embeds(url1=url1, url2=url2)

        assert len(embeds) == 2
        assert embeds[0].image.url == url1
        assert embeds[1].image.url == url2

    def test_creates_one_embed_for_one_url(self) -> None:
        """Probar que crea un embed si solo hay una URL."""
        url1 = "https://cdn.discordapp.com/attachments/123/456/1.png"

        embeds = create_screenshot_embeds(url1=url1, url2=None)

        assert len(embeds) == 1
        assert embeds[0].image.url == url1

    def test_creates_empty_list_for_no_urls(self) -> None:
        """Probar que retorna lista vacía si no hay URLs."""
        embeds = create_screenshot_embeds(url1=None, url2=None)

        assert len(embeds) == 0

    def test_skips_none_url(self) -> None:
        """Probar que salta URL None."""
        url2 = "https://cdn.discordapp.com/attachments/123/456/2.png"

        embeds = create_screenshot_embeds(url1=None, url2=url2)

        assert len(embeds) == 1
        assert embeds[0].image.url == url2


class TestGetApiErrorMessage:
    """Tests para get_api_error_message."""

    def test_401_unauthorized(self) -> None:
        """Probar mensaje para 401."""
        result = get_api_error_message(401)
        assert result == "API key required or invalid"

    def test_413_too_large(self) -> None:
        """Probar mensaje para 413."""
        result = get_api_error_message(413)
        assert result == "Image exceeds maximum upload size"

    def test_422_not_in_error_messages(self) -> None:
        """Probar que 422 no está en API_ERROR_MESSAGES (se maneja por separado)."""
        # 422 is handled separately as "invalid images", not as an API error
        result = get_api_error_message(422)
        assert result == "API Error (code: 422)"

    def test_429_rate_limit(self) -> None:
        """Probar mensaje para 429."""
        result = get_api_error_message(429)
        assert result == "Rate limit exceeded"

    def test_500_internal_error(self) -> None:
        """Probar mensaje para 500."""
        result = get_api_error_message(500)
        assert result == "Internal processing error"

    def test_unknown_status_code(self) -> None:
        """Probar mensaje para código desconocido."""
        result = get_api_error_message(418)
        assert result == "API Error (code: 418)"


class TestUpdateModMessageForReview:
    """Tests para update_mod_message_for_manual_review."""

    @pytest.mark.asyncio
    async def test_returns_early_when_no_mod_message_id(self) -> None:
        """Probar que retorna si no hay mod_message_id."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_request = MagicMock()
        mock_request.mod_message_id = None

        config: dict[str, Any] = {}

        # No debería fallar, solo retornar
        await update_mod_message_for_manual_review(mock_guild, mock_request, config, 123)

    @pytest.mark.asyncio
    async def test_returns_early_when_no_mod_channel_id(self) -> None:
        """Probar que retorna si no hay canal de moderación configurado."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_request = MagicMock()
        mock_request.mod_message_id = 999

        config: dict[str, Any] = {
            "mod_notification_channel": None,
        }

        await update_mod_message_for_manual_review(mock_guild, mock_request, config, 123)

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

        await update_mod_message_for_manual_review(mock_guild, mock_request, config, 123)

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

        await update_mod_message_for_manual_review(mock_guild, mock_request, config, 123)

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
        await update_mod_message_for_manual_review(mock_guild, mock_request, config, 123)


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
        mock_request.verification_type = VerificationType.REGULAR

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
    """Tests para send_mod_ping_message."""

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

        await send_mod_ping_message(mock_channel, config)

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

        await send_mod_ping_message(mock_channel, config)

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

        await send_mod_ping_message(mock_channel, config)

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

        await send_mod_ping_message(mock_channel, config)

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

        await send_mod_ping_message(mock_channel, config)

        mock_channel.send.assert_called_once()
        call_args = mock_channel.send.call_args
        assert "<@&111>" in call_args.kwargs["content"]
        assert "<@&222>" in call_args.kwargs["content"]


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


class TestUpdateTrackerMessage:
    """Tests para update_tracker_message."""

    async def test_returns_early_when_channel_not_text_channel(self) -> None:
        """Probar que retorna temprano si canal no es TextChannel."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        # Return a VoiceChannel instead of TextChannel
        mock_voice_channel = MagicMock(spec=discord.VoiceChannel)
        mock_guild.get_channel = MagicMock(return_value=mock_voice_channel)

        mock_verification_service = MagicMock()
        mock_config_service = MagicMock()

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Verificaciones Pendientes",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
        }

        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

        # Should not call any service methods
        mock_verification_service.get_pending_for_guild.assert_not_called()

    async def test_fetches_existing_tracker_and_handles_not_found(self) -> None:
        """Probar que maneja NotFound al buscar mensaje de tracker existente."""
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([]))
        mock_tracker_msg = MagicMock()
        mock_tracker_msg.id = 9999
        mock_mod_channel.send = AsyncMock(return_value=mock_tracker_msg)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_request = MagicMock()
        mock_request.username = "TestUser"
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.mod_message_id = 12345
        mock_request.created_at = MagicMock()
        mock_request.created_at.timestamp = MagicMock(return_value=1234567890)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[mock_request])

        mock_config_service = MagicMock()
        mock_config_service.set_value = AsyncMock(return_value=(True, None))

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Verificaciones Pendientes",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,  # Existing tracker ID
        }

        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

        # Should have called set_value to clear the old tracker ID
        assert mock_config_service.set_value.call_count >= 1

    async def test_deletes_tracker_when_no_pending_requests(self) -> None:
        """Probar que elimina tracker cuando no hay solicitudes pendientes."""
        mock_tracker_message = MagicMock()
        mock_tracker_message.delete = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_tracker_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[])

        mock_config_service = MagicMock()
        mock_config_service.set_value = AsyncMock(return_value=(True, None))

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Verificaciones Pendientes",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,
        }

        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

        mock_tracker_message.delete.assert_called_once()

    async def test_handles_not_found_when_deleting_tracker(self) -> None:
        """Probar que maneja NotFound al eliminar tracker."""
        mock_tracker_message = MagicMock()
        mock_tracker_message.delete = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_tracker_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[])

        mock_config_service = MagicMock()
        mock_config_service.set_value = AsyncMock(return_value=(True, None))

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Verificaciones Pendientes",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,
        }

        # Should not raise
        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

    async def test_repositions_tracker_when_not_last_message(self) -> None:
        """Probar que reposiciona tracker cuando no es el último mensaje."""
        mock_tracker_message = MagicMock()
        mock_tracker_message.id = 888
        mock_tracker_message.delete = AsyncMock()

        # Last message is different from tracker
        mock_last_message = MagicMock()
        mock_last_message.id = 999

        mock_new_tracker = MagicMock()
        mock_new_tracker.id = 1000

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_tracker_message)
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([mock_last_message]))
        mock_mod_channel.send = AsyncMock(return_value=mock_new_tracker)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_request = MagicMock()
        mock_request.username = "TestUser"
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.mod_message_id = 12345
        mock_request.created_at = MagicMock()
        mock_request.created_at.timestamp = MagicMock(return_value=1234567890)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[mock_request])

        mock_config_service = MagicMock()
        mock_config_service.set_value = AsyncMock(return_value=(True, None))

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Verificaciones Pendientes",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,
        }

        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

        # Should delete old tracker and send new one
        mock_tracker_message.delete.assert_called_once()
        mock_mod_channel.send.assert_called_once()

    async def test_edits_existing_tracker_when_last_message(self) -> None:
        """Probar que edita tracker existente cuando es el último mensaje."""
        mock_tracker_message = MagicMock()
        mock_tracker_message.id = 888
        mock_tracker_message.edit = AsyncMock()

        # Tracker is the last message
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_tracker_message)
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([mock_tracker_message]))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_request = MagicMock()
        mock_request.username = "TestUser"
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.mod_message_id = 12345
        mock_request.created_at = MagicMock()
        mock_request.created_at.timestamp = MagicMock(return_value=1234567890)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[mock_request])

        mock_config_service = MagicMock()

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Verificaciones Pendientes",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,
        }

        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

        mock_tracker_message.edit.assert_called_once()

    async def test_handles_not_found_when_editing_tracker(self) -> None:
        """Probar que maneja NotFound al editar tracker y crea uno nuevo."""
        mock_tracker_message = MagicMock()
        mock_tracker_message.id = 888
        mock_tracker_message.edit = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        mock_new_tracker = MagicMock()
        mock_new_tracker.id = 1000

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_tracker_message)
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([mock_tracker_message]))
        mock_mod_channel.send = AsyncMock(return_value=mock_new_tracker)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_request = MagicMock()
        mock_request.username = "TestUser"
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.mod_message_id = 12345
        mock_request.created_at = MagicMock()
        mock_request.created_at.timestamp = MagicMock(return_value=1234567890)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[mock_request])

        mock_config_service = MagicMock()
        mock_config_service.set_value = AsyncMock(return_value=(True, None))

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Verificaciones Pendientes",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,
        }

        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )

        # Should send new message after edit fails
        mock_mod_channel.send.assert_called_once()

    async def test_handles_forbidden_when_sending_tracker(self) -> None:
        """Probar que maneja Forbidden al enviar nuevo tracker."""
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.name = "mod-channel"
        mock_mod_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([]))
        mock_mod_channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        mock_request = MagicMock()
        mock_request.username = "TestUser"
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.mod_message_id = 12345
        mock_request.created_at = MagicMock()
        mock_request.created_at.timestamp = MagicMock(return_value=1234567890)

        mock_verification_service = MagicMock()
        mock_verification_service.get_pending_for_guild = AsyncMock(return_value=[mock_request])

        mock_config_service = MagicMock()
        mock_config_service.set_value = AsyncMock(return_value=(True, None))

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Verificaciones Pendientes",
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 456,
            ConfigKey.TRACKER_MESSAGE_ID: 888,
        }

        # Should not raise
        await update_tracker_message(
            guild=mock_guild,
            config=config,
            verification_service=mock_verification_service,
            config_service=mock_config_service,
        )
