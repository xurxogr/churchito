"""Utilidades para operaciones de Discord."""

import logging

import discord

logger = logging.getLogger(__name__)


async def delete_message(
    guild: discord.Guild,
    channel_id: int,
    message_id: int,
) -> bool:
    """Eliminar un mensaje de un canal.

    Args:
        guild (discord.Guild): Guild donde esta el mensaje
        channel_id (int): ID del canal
        message_id (int): ID del mensaje

    Returns:
        bool: True si se elimino, False si no se pudo
    """
    channel = guild.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.TextChannel):
        return False

    try:
        message = await channel.fetch_message(message_id)
        await message.delete()
        logger.info(f"Mensaje {message_id} eliminado de canal {channel.name} en guild {guild.id}")
        return True
    except discord.NotFound:
        return False
    except discord.Forbidden:
        logger.warning(f"Sin permisos para eliminar mensaje {message_id} en guild {guild.id}")
        return False


def has_any_role(member: discord.Member, role_ids: list[int]) -> bool:
    """Verificar si un miembro tiene alguno de los roles especificados.

    Si la lista de roles esta vacia, verifica el permiso manage_guild.

    Args:
        member (discord.Member): Miembro a verificar
        role_ids (list[int]): IDs de roles a verificar

    Returns:
        bool: True si tiene alguno de los roles o manage_guild si lista vacia
    """
    if not role_ids:
        return member.guild_permissions.manage_guild
    return any(role.id in role_ids for role in member.roles)
