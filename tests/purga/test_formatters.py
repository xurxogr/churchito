"""Tests para discord_bot/purga/formatters.py."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import discord
import pytest

from discord_bot.purga.enums import ConfigKey, PurgaStatus, PurgaType
from discord_bot.purga.formatters import (
    format_authorized_by,
    format_message,
    format_roles,
    get_button_style,
    get_mod_message_content,
)


@pytest.fixture
def mock_guild() -> MagicMock:
    """Crear mock de un guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 123456789
    guild.name = "Test Guild"
    guild.get_member = MagicMock(return_value=None)
    guild.get_role = MagicMock(return_value=None)
    return guild


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
    return record


class TestFormatMessage:
    """Tests para format_message."""

    def test_format_all_placeholders(self) -> None:
        """Probar reemplazo de todos los placeholders."""
        template = "Estado: {status}, Dia: {dia}"

        result = format_message(
            template,
            status="Pendiente",
            dia="2024-01-01",
        )

        assert result == "Estado: Pendiente, Dia: 2024-01-01"

    def test_format_empty_placeholders(self) -> None:
        """Probar con placeholder pasado como None."""
        template = "Usuario: {username}"
        result = format_message(template, username=None)
        assert result == "Usuario: "

    def test_format_unmatched_placeholder(self) -> None:
        """Probar que placeholders no pasados se mantienen."""
        template = "Usuario: {username}"
        result = format_message(template)
        assert result == "Usuario: {username}"

    def test_format_no_placeholders(self) -> None:
        """Probar mensaje sin placeholders."""
        template = "Mensaje simple sin placeholders"
        result = format_message(template)
        assert result == template

    def test_format_none_template(self) -> None:
        """Probar con template None."""
        result = format_message(None, status="Test")
        assert result == ""


class TestGetButtonStyle:
    """Tests para get_button_style."""

    def test_blurple(self) -> None:
        """Probar estilo blurple."""
        result = get_button_style("blurple")
        assert result == discord.ButtonStyle.primary

    def test_grey(self) -> None:
        """Probar estilo grey."""
        result = get_button_style("grey")
        assert result == discord.ButtonStyle.secondary

    def test_green(self) -> None:
        """Probar estilo green."""
        result = get_button_style("green")
        assert result == discord.ButtonStyle.success

    def test_red(self) -> None:
        """Probar estilo red."""
        result = get_button_style("red")
        assert result == discord.ButtonStyle.danger

    def test_unknown_defaults_to_success(self) -> None:
        """Probar que color desconocido devuelve success."""
        result = get_button_style("unknown")
        assert result == discord.ButtonStyle.success


class TestFormatAuthorizedBy:
    """Tests para format_authorized_by."""

    def test_empty_list(self, mock_guild: MagicMock) -> None:
        """Probar con lista vacia."""
        result = format_authorized_by(mock_guild, [])
        assert result == "Ninguno"

    def test_with_found_members(self, mock_guild: MagicMock) -> None:
        """Probar con miembros encontrados."""
        member1 = MagicMock(spec=discord.Member)
        member1.display_name = "User1"
        member2 = MagicMock(spec=discord.Member)
        member2.display_name = "User2"

        mock_guild.get_member = MagicMock(
            side_effect=lambda uid: member1 if uid == 111 else member2 if uid == 222 else None
        )

        result = format_authorized_by(mock_guild, [111, 222])
        assert result == "User1, User2"

    def test_with_not_found_members(self, mock_guild: MagicMock) -> None:
        """Probar con miembros no encontrados."""
        mock_guild.get_member = MagicMock(return_value=None)

        result = format_authorized_by(mock_guild, [111, 222])
        assert result == "<@111>, <@222>"

    def test_mixed_members(self, mock_guild: MagicMock) -> None:
        """Probar con mezcla de miembros encontrados y no encontrados."""
        member1 = MagicMock(spec=discord.Member)
        member1.display_name = "User1"

        mock_guild.get_member = MagicMock(side_effect=lambda uid: member1 if uid == 111 else None)

        result = format_authorized_by(mock_guild, [111, 222])
        assert result == "User1, <@222>"


class TestFormatRoles:
    """Tests para format_roles."""

    def test_empty_list(self, mock_guild: MagicMock) -> None:
        """Probar con lista vacia."""
        result = format_roles(mock_guild, [])
        assert result == "Ninguno"

    def test_with_found_roles(self, mock_guild: MagicMock) -> None:
        """Probar con roles encontrados."""
        role1 = MagicMock(spec=discord.Role)
        role1.mention = "@Role1"
        role2 = MagicMock(spec=discord.Role)
        role2.mention = "@Role2"

        mock_guild.get_role = MagicMock(
            side_effect=lambda rid: role1 if rid == 100 else role2 if rid == 200 else None
        )

        result = format_roles(mock_guild, [100, 200])
        assert result == "@Role1, @Role2"

    def test_with_not_found_roles(self, mock_guild: MagicMock) -> None:
        """Probar con roles no encontrados."""
        mock_guild.get_role = MagicMock(return_value=None)

        result = format_roles(mock_guild, [100, 200])
        assert result == "<@&100>, <@&200>"


class TestGetModMessageContent:
    """Tests para get_mod_message_content."""

    def test_pending_status(
        self,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar contenido con estado pendiente."""
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Estado: {status}",
            ConfigKey.MOD_STATUS_PENDING: "Pendiente",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purga_record, config=config)

        assert "Pendiente" in result

    def test_authorized_status(
        self,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar contenido con estado autorizado."""
        mock_purga_record.status = PurgaStatus.AUTHORIZED
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Estado: {status}",
            ConfigKey.MOD_STATUS_AUTHORIZED: "Autorizado",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purga_record, config=config)

        assert "Autorizado" in result

    def test_with_execution_logs(
        self,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar contenido con logs de ejecucion."""
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Base message",
            ConfigKey.MOD_STATUS_PENDING: "Pendiente",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }
        logs = ["Log line 1", "Log line 2"]

        result = get_mod_message_content(
            guild=mock_guild,
            record=mock_purga_record,
            config=config,
            execution_logs=logs,
        )

        assert "**Logs:**" in result
        assert "Log line 1" in result
        assert "Log line 2" in result

    def test_without_execution_logs(
        self,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar contenido sin logs de ejecucion."""
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Base message",
            ConfigKey.MOD_STATUS_PENDING: "Pendiente",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purga_record, config=config)

        assert "**Logs:**" not in result

    def test_war_purge_type(
        self,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar que muestra tipo de purga de guerra."""
        mock_purga_record.purga_type = PurgaType.WAR_END
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "{purge_type}",
            ConfigKey.MOD_STATUS_PENDING: "Pendiente",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purga_record, config=config)

        assert "fin de guerra" in result.lower()

    def test_maintenance_purge_type(
        self,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar que muestra tipo de purga de mantenimiento."""
        mock_purga_record.purga_type = PurgaType.MAINTENANCE
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "{purge_type}",
            ConfigKey.MOD_STATUS_PENDING: "Pendiente",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purga_record, config=config)

        assert "mantenimiento" in result.lower()

    def test_all_status_messages(
        self,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar todos los estados posibles."""
        statuses = [
            (PurgaStatus.PENDING, ConfigKey.MOD_STATUS_PENDING, "Pendiente"),
            (PurgaStatus.AUTHORIZED, ConfigKey.MOD_STATUS_AUTHORIZED, "Autorizado"),
            (PurgaStatus.EXPIRED, ConfigKey.MOD_STATUS_EXPIRED, "Expirado"),
            (
                PurgaStatus.CANCEL_PENDING,
                ConfigKey.MOD_STATUS_CANCEL_PENDING,
                "Cancelación pendiente",
            ),
            (PurgaStatus.CANCELLED, ConfigKey.MOD_STATUS_CANCELLED, "Cancelado"),
            (PurgaStatus.EXECUTED, ConfigKey.MOD_STATUS_EXECUTED, "Ejecutado"),
        ]

        for status, config_key, expected_text in statuses:
            mock_purga_record.status = status
            config: dict[str, Any] = {
                ConfigKey.MOD_MESSAGE_TEMPLATE: "Estado: {status}",
                config_key: expected_text,
                ConfigKey.MOD_REQUIRED_REACTIONS: 2,
            }

            result = get_mod_message_content(
                guild=mock_guild, record=mock_purga_record, config=config
            )

            assert expected_text in result, f"Failed for status {status}"

    def test_failed_status(
        self,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar estado FAILED tiene texto por defecto."""
        mock_purga_record.status = PurgaStatus.FAILED
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Estado: {status}",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purga_record, config=config)

        assert "Fallido" in result

    def test_scheduled_for_date_formatting(
        self,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar formato de fecha de ejecución."""
        mock_purga_record.scheduled_for = datetime(2024, 6, 15, 18, 0, 0, tzinfo=UTC)
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Fecha: {dia}",
            ConfigKey.MOD_STATUS_PENDING: "Pendiente",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purga_record, config=config)

        assert "2024-06-15 18:00 UTC" in result

    def test_no_scheduled_for(
        self,
        mock_guild: MagicMock,
        mock_purga_record: MagicMock,
    ) -> None:
        """Probar cuando no hay fecha programada."""
        mock_purga_record.scheduled_for = None
        config: dict[str, Any] = {
            ConfigKey.MOD_MESSAGE_TEMPLATE: "Fecha: {dia}",
            ConfigKey.MOD_STATUS_PENDING: "Pendiente",
            ConfigKey.MOD_REQUIRED_REACTIONS: 2,
        }

        result = get_mod_message_content(guild=mock_guild, record=mock_purga_record, config=config)

        assert "No programada" in result
