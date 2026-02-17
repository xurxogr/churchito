"""Logica de panel y health check para el cog de verificacion."""

import logging
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import delete_message
from discord_bot.verification.config import COG_NAME
from discord_bot.verification.enums import ConfigKey
from discord_bot.verification.formatters import create_panel_embed, format_message
from discord_bot.verification.views import VerificationPanelView

if TYPE_CHECKING:
    from discord_bot.verification.cog import VerificationCog

logger = logging.getLogger(__name__)


def get_mod_channel(
    guild: discord.Guild,
    config: dict[str, Any],
    bot_user: discord.User | discord.ClientUser | None,
) -> discord.TextChannel | None:
    """Obtener canal de moderacion si esta configurado y accesible.

    Args:
        guild (discord.Guild): Guild.
        config (dict[str, Any]): Configuracion del cog.
        bot_user (discord.User | discord.ClientUser | None): Usuario del bot.

    Returns:
        discord.TextChannel | None: Canal de moderacion o None si no disponible.
    """
    mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
    if not mod_channel_id:
        return None

    mod_channel = guild.get_channel(mod_channel_id)
    if not mod_channel or not isinstance(mod_channel, discord.TextChannel):
        return None

    # Verificar permisos del bot
    if bot_user is None:
        return None

    bot_member = guild.get_member(bot_user.id)
    if not bot_member:
        return None

    permissions = mod_channel.permissions_for(bot_member)
    if not permissions.send_messages:
        return None

    return mod_channel


async def check_verification_message(
    cog: "VerificationCog",
    guild: discord.Guild,
    recreate: bool = False,
) -> None:
    """Verificar y restaurar panel de verificacion de un guild.

    Args:
        cog (VerificationCog): Instancia del cog.
        guild (discord.Guild): Guild a verificar.
        recreate (bool): Si True, elimina el panel existente y lo recrea
            (usado cuando cambia la configuracion del panel).
    """
    async with cog.bot.database.session() as session:
        config_service = ConfigService(session=session)

        # Verificar si el cog esta habilitado
        if not await config_service.is_cog_enabled(guild_id=guild.id, cog_name=COG_NAME):
            return

        # Obtener toda la configuracion de una vez
        config = await config_service.get_all_config(guild_id=guild.id, cog_name=COG_NAME)

        # Obtener canal configurado
        channel_id = config.get(ConfigKey.VERIFICATION_CHANNEL)
        if not channel_id:
            return  # No hay canal configurado

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning(f"Canal de verificacion {channel_id} no encontrado en guild {guild.id}")
            return

        # Obtener panel actual
        panel_message_id = config.get(ConfigKey.PANEL_MESSAGE_ID)
        panel_channel_id = config.get(ConfigKey.PANEL_CHANNEL_ID)

        # Si recreate=True, eliminar panel viejo y crear nuevo
        if recreate:
            if panel_message_id and panel_channel_id:
                await delete_message(
                    guild=guild,
                    channel_id=panel_channel_id,
                    message_id=panel_message_id,
                )
            await cog._create_verification_message(
                guild=guild,
                channel=channel,
                config=config,
                config_service=config_service,
                session=session,
            )
            return

        # Caso 1: No hay panel, crear uno nuevo
        if not panel_message_id:
            logger.info(f"Creando panel de verificacion en guild {guild.id}, canal {channel.name}")
            await cog._create_verification_message(
                guild=guild,
                channel=channel,
                config=config,
                config_service=config_service,
                session=session,
            )
            return

        # Caso 2: El canal cambio, eliminar panel viejo y crear nuevo
        if panel_channel_id and panel_channel_id != channel_id:
            logger.info(
                f"Canal de verificacion cambio en guild {guild.id}, "
                f"moviendo panel de {panel_channel_id} a {channel_id}"
            )
            await delete_message(
                guild=guild,
                channel_id=panel_channel_id,
                message_id=panel_message_id,
            )
            await cog._create_verification_message(
                guild=guild,
                channel=channel,
                config=config,
                config_service=config_service,
                session=session,
            )
            return

        # Caso 3: Verificar que el panel existe y tiene botones
        try:
            message = await channel.fetch_message(panel_message_id)
            # Verificar que tiene botones (view activa)
            if not message.components:
                logger.info(f"Panel en guild {guild.id} sin botones, restaurando...")
                await cog._create_verification_message(
                    guild=guild,
                    channel=channel,
                    config=config,
                    config_service=config_service,
                    session=session,
                )
        except discord.NotFound:
            logger.info(f"Panel no encontrado en guild {guild.id}, restaurando...")
            await cog._create_verification_message(
                guild=guild,
                channel=channel,
                config=config,
                config_service=config_service,
                session=session,
            )
        except discord.Forbidden:
            logger.warning(f"Sin permisos para verificar panel en guild {guild.id}")


async def create_verification_message(
    cog: "VerificationCog",
    guild: discord.Guild,
    channel: discord.TextChannel,
    config: dict[str, Any],
    config_service: ConfigService,
    session: Any,
) -> None:
    """Crear panel de verificacion en un canal.

    Args:
        cog (VerificationCog): Instancia del cog.
        guild (discord.Guild): Guild del panel.
        channel (discord.TextChannel): Canal donde crear.
        config (dict[str, Any]): Configuracion del cog.
        config_service (ConfigService): Servicio de configuracion (para set_value).
        session (Any): Sesion de base de datos.
    """
    # Verificar si la verificacion esta habilitada
    verification_enabled = config.get(ConfigKey.VERIFICATION_ENABLED)
    if verification_enabled is False:
        logger.info(f"Verificacion deshabilitada manualmente en guild {guild.id}")

    # Verificar que el canal de moderacion esta configurado y accesible
    mod_channel = get_mod_channel(guild=guild, config=config, bot_user=cog.bot.user)
    if not mod_channel:
        logger.warning(
            f"Verificacion deshabilitada en guild {guild.id}: "
            f"canal de moderacion no configurado o sin permisos"
        )

    is_configured = verification_enabled is not False and mod_channel is not None

    if is_configured:
        # Verificacion habilitada - mostrar botones
        formatted_message = format_message(
            template=config.get(ConfigKey.VERIFICATION_PANEL_MESSAGE),
            server_name=guild.name,
        )
        view: discord.ui.View | None = VerificationPanelView(
            verify_label=config.get(ConfigKey.VERIFY_BUTTON_TEXT) or "Verificar",
            ally_label=config.get(ConfigKey.VERIFY_ALLY_BUTTON_TEXT) or "Verificar como Aliado",
        )
    else:
        # Verificacion deshabilitada - mostrar mensaje sin botones
        formatted_message = format_message(
            template=config.get(ConfigKey.VERIFICATION_DISABLED_MESSAGE),
            server_name=guild.name,
        )
        view = None

    # Crear embed si hay imagen en el mensaje
    embed, clean_text = create_panel_embed(formatted_message)

    try:
        if embed and view:
            new_message = await channel.send(embed=embed, view=view)
        elif embed:
            new_message = await channel.send(embed=embed)
        elif view:
            new_message = await channel.send(content=clean_text, view=view)
        else:
            new_message = await channel.send(content=clean_text)
        await config_service.set_value(
            guild_id=guild.id,
            cog_name=COG_NAME,
            key=ConfigKey.PANEL_MESSAGE_ID,
            value=new_message.id,
        )
        await config_service.set_value(
            guild_id=guild.id,
            cog_name=COG_NAME,
            key=ConfigKey.PANEL_CHANNEL_ID,
            value=channel.id,
        )
        await session.commit()
        logger.info(f"Panel de verificacion creado en guild {guild.id}, canal {channel.name}")
    except discord.Forbidden:
        logger.error(f"Sin permisos para enviar panel en guild {guild.id}, canal {channel.name}")
