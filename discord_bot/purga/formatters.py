"""Funciones de formateo para el cog de purga."""

from typing import Any

import discord

from discord_bot.purga.config import BUTTON_STYLES
from discord_bot.purga.enums import ConfigKey, PurgaStatus, PurgaType
from discord_bot.purga.models import PurgaRecord


def format_message(template: str | None = None, **kwargs: str | None) -> str:
    """Reemplazar placeholders en un mensaje.

    Args:
        template (str | None): Plantilla del mensaje.
        **kwargs: Placeholders a reemplazar.

    Returns:
        str: Mensaje formateado.
    """
    result = template or ""
    for key, value in kwargs.items():
        result = result.replace(f"{{{key}}}", value or "")
    return result


def get_button_style(color: str) -> discord.ButtonStyle:
    """Obtener el estilo de botón a partir del nombre de color.

    Args:
        color (str): Nombre del color (blurple, grey, green, red).

    Returns:
        discord.ButtonStyle: Estilo de botón.
    """
    return BUTTON_STYLES.get(color, discord.ButtonStyle.success)


def format_authorized_by(guild: discord.Guild, user_ids: list[int]) -> str:
    """Formatear la lista de usuarios que autorizaron.

    Args:
        guild (discord.Guild): Guild para resolver nombres.
        user_ids (list[int]): Lista de IDs de usuarios.

    Returns:
        str: Lista formateada de nombres.
    """
    if not user_ids:
        return "Ninguno"

    names: list[str] = []
    for user_id in user_ids:
        member = guild.get_member(user_id)
        if member:
            names.append(member.display_name)
        else:
            names.append(f"<@{user_id}>")

    return ", ".join(names)


def format_roles(guild: discord.Guild, role_ids: list[int]) -> str:
    """Formatear la lista de roles.

    Args:
        guild (discord.Guild): Guild para resolver roles.
        role_ids (list[int]): Lista de IDs de roles.

    Returns:
        str: Lista formateada de roles.
    """
    if not role_ids:
        return "Ninguno"

    roles: list[str] = []
    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role:
            roles.append(role.mention)
        else:
            roles.append(f"<@&{role_id}>")

    return ", ".join(roles)


def get_mod_message_content(
    guild: discord.Guild,
    record: PurgaRecord,
    config: dict[str, Any],
    execution_logs: list[str] | None = None,
) -> str:
    """Generar el contenido del mensaje de moderación.

    Args:
        guild (discord.Guild): Guild.
        record (PurgaRecord): Registro de purga.
        config (dict[str, Any]): Configuración.
        execution_logs (list[str] | None): Logs de ejecución para añadir.

    Returns:
        str: Contenido del mensaje.
    """
    status_map = {
        PurgaStatus.PENDING: config.get(ConfigKey.MOD_STATUS_PENDING, ""),
        PurgaStatus.AUTHORIZED: config.get(ConfigKey.MOD_STATUS_AUTHORIZED, ""),
        PurgaStatus.EXPIRED: config.get(ConfigKey.MOD_STATUS_EXPIRED, ""),
        PurgaStatus.CANCEL_PENDING: config.get(ConfigKey.MOD_STATUS_CANCEL_PENDING, ""),
        PurgaStatus.CANCELLED: config.get(ConfigKey.MOD_STATUS_CANCELLED, ""),
        PurgaStatus.EXECUTED: config.get(ConfigKey.MOD_STATUS_EXECUTED, ""),
        PurgaStatus.FAILED: "❌ Fallido",
    }

    status_text = status_map.get(PurgaStatus(record.status), "Desconocido")
    required = config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2)
    authorized_by = format_authorized_by(guild=guild, user_ids=record.authorized_by)
    cancellations = format_authorized_by(guild=guild, user_ids=record.cancelled_by)

    purge_type = "Purga de fin de guerra"
    if record.purga_type == PurgaType.MAINTENANCE:
        purge_type = "Purga de mantenimiento"

    execution_date = "No programada"
    if record.scheduled_for:
        execution_date = record.scheduled_for.strftime("%Y-%m-%d %H:%M UTC")

    content = format_message(
        template=config.get(ConfigKey.MOD_MESSAGE_TEMPLATE),
        purge_type=purge_type,
        status=status_text,
        required_reactions=str(required),
        authorized_by=authorized_by,
        cancellations=cancellations,
        dia=execution_date,
    )

    # Append execution logs if provided
    if execution_logs:
        logs_text = "\n".join(execution_logs)
        content = f"{content}\n\n**Logs:**\n{logs_text}"

    return content
