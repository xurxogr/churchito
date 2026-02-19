"""Cog de autoname para formateo automatico de nicknames."""

import logging
from datetime import UTC, datetime
from typing import Any

import discord
from discord.ext import commands, tasks

from discord_bot.autoname.config import AUTONAME_CONFIG_SCHEMA, COG_NAME, ConfigKey
from discord_bot.autoname.service import compute_nickname
from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService

logger = logging.getLogger(__name__)


class AutonameCog(commands.Cog):
    """Cog para formateo automatico de nicknames basado en roles."""

    def __init__(self, bot: DiscordBot) -> None:
        """Inicializar el cog de autoname.

        Args:
            bot (DiscordBot): Instancia del bot
        """
        self.bot = bot
        self._last_sync: dict[int, datetime] = {}
        self._sync_started = False

    async def cog_load(self) -> None:
        """Iniciar tareas al cargar el cog."""
        if not self._sync_started:
            self.sync_loop.start()
            self._sync_started = True

    async def cog_unload(self) -> None:
        """Detener tareas al descargar el cog."""
        if self._sync_started:
            self.sync_loop.cancel()
            self._sync_started = False

    async def _is_cog_enabled(self, guild_id: int) -> bool:
        """Verificar si el cog esta habilitado para un guild.

        Args:
            guild_id (int): ID del guild

        Returns:
            bool: True si el cog esta habilitado
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.is_cog_enabled(guild_id=guild_id, cog_name=COG_NAME)

    async def _get_config(self, guild_id: int) -> dict[str, Any]:
        """Obtener toda la configuracion del cog para un guild.

        Args:
            guild_id (int): ID del guild

        Returns:
            dict[str, Any]: Configuracion del cog
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.get_all_config(guild_id=guild_id, cog_name=COG_NAME)

    async def _get_sync_interval(self, guild_id: int) -> int:
        """Obtener el intervalo de sincronizacion configurado para un guild.

        Args:
            guild_id (int): ID del guild

        Returns:
            int: Intervalo en minutos (0 si desactivado, 30 por defecto)
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)

            if not await config_service.is_cog_enabled(guild_id=guild_id, cog_name=COG_NAME):
                return 0

            interval = await config_service.get_value(
                guild_id=guild_id,
                cog_name=COG_NAME,
                key=ConfigKey.SYNC_INTERVAL,
            )
            return interval if interval is not None else 30

    async def _send_log(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
        message_key: str,
        **placeholders: str,
    ) -> None:
        """Enviar mensaje al canal de logs si esta configurado.

        Args:
            guild: Guild donde enviar el log
            config: Configuracion del cog
            message_key: Clave del mensaje en la config
            **placeholders: Valores para reemplazar en el mensaje
        """
        channel_id = config.get(ConfigKey.LOG_CHANNEL)
        if not channel_id:
            return

        message_template = config.get(message_key, "")
        if not message_template:
            return

        try:
            channel_id_int = int(channel_id)
            channel = guild.get_channel(channel_id_int)
            if channel and isinstance(channel, discord.TextChannel):
                message = message_template.format(**placeholders)
                await channel.send(message)
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"[{guild.name}] Error formateando mensaje de log: {e}")
        except discord.HTTPException as e:
            logger.warning(f"[{guild.name}] Error enviando log al canal: {e}")

    async def apply_nickname(self, member: discord.Member) -> bool:
        """Aplicar nickname formateado a un miembro.

        Args:
            member (discord.Member): Miembro a actualizar

        Returns:
            bool: True si se actualizo el nickname
        """
        if member.bot:
            return False

        config = await self._get_config(member.guild.id)

        tags_config = config.get(ConfigKey.ROLE_TAGS) or []
        prefixes_config = config.get(ConfigKey.ROLE_PREFIXES) or []
        tag_format = config.get(ConfigKey.TAG_FORMAT) or "[ABC | {tag}]"

        if not tags_config and not prefixes_config:
            return False

        member_role_ids = [r.id for r in member.roles]

        new_nickname = compute_nickname(
            display_name=member.display_name,
            current_nick=member.nick,
            member_role_ids=member_role_ids,
            tags_config=tags_config,
            prefixes_config=prefixes_config,
            tag_format=tag_format,
        )

        if new_nickname is None:
            return False

        # Safety check - don't update if nickname is already correct
        # (handles edge cases with unicode normalization, whitespace, etc.)
        if new_nickname == member.nick or new_nickname == member.display_name:
            return False

        # Save original name before edit for logging
        original_name = member.display_name

        try:
            await member.edit(nick=new_nickname)
            logger.info(f"[{member.guild.name}] '{original_name}' -> '{new_nickname}'")
            await self._send_log(
                guild=member.guild,
                config=config,
                message_key=ConfigKey.LOG_MESSAGE_SUCCESS,
                old_name=original_name,
                new_name=new_nickname,
            )
            return True
        except discord.Forbidden:
            logger.warning(f"[{member.guild.name}] Sin permisos para '{original_name}'")
            await self._send_log(
                guild=member.guild,
                config=config,
                message_key=ConfigKey.LOG_MESSAGE_NO_PERMS,
                name=original_name,
            )
            return False
        except discord.HTTPException as e:
            logger.error(f"[{member.guild.name}] Error con '{original_name}': {e}")
            return False

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Manejar actualizaciones de miembros para detectar cambios de rol.

        Args:
            before (discord.Member): Estado anterior del miembro
            after (discord.Member): Estado actual del miembro
        """
        # Solo procesar si cambiaron los roles
        if before.roles == after.roles:
            return

        # Verificar si el cog esta habilitado
        if not await self._is_cog_enabled(after.guild.id):
            return

        await self.apply_nickname(after)

    @tasks.loop(minutes=1)
    async def sync_loop(self) -> None:
        """Loop de sincronizacion periodica de nicknames.

        Cada guild tiene su propio intervalo configurado. Este loop corre
        cada minuto y verifica si cada guild esta listo para sincronizar.
        """
        await self._run_sync()

    @sync_loop.before_loop
    async def before_sync(self) -> None:
        """Esperar a que el bot este listo antes de iniciar el sync."""
        await self.bot.wait_until_ready()
        # Ejecutar inmediatamente al iniciar
        await self._run_sync(force_all=True)

    async def _run_sync(self, force_all: bool = False) -> None:
        """Ejecutar sincronizacion de nicknames en guilds que esten listos.

        Args:
            force_all (bool): Si True, ejecuta para todos los guilds ignorando intervalos
        """
        now = datetime.now(UTC)

        for guild in self.bot.guilds:
            try:
                interval = await self._get_sync_interval(guild.id)

                if interval == 0:
                    continue

                if not force_all:
                    last_sync = self._last_sync.get(guild.id)
                    if last_sync:
                        seconds_since_last = (now - last_sync).total_seconds()
                        if seconds_since_last < interval * 60:
                            continue

                await self._sync_guild(guild)
                self._last_sync[guild.id] = now

            except Exception as e:
                logger.error(f"[{guild.name}] Error en sync: {e}")

    async def _sync_guild(self, guild: discord.Guild) -> None:
        """Sincronizar nicknames de todos los miembros de un guild.

        Args:
            guild (discord.Guild): Guild a sincronizar
        """
        if not await self._is_cog_enabled(guild.id):
            return

        config = await self._get_config(guild.id)
        tags_config = config.get(ConfigKey.ROLE_TAGS) or []
        prefixes_config = config.get(ConfigKey.ROLE_PREFIXES) or []

        if not tags_config and not prefixes_config:
            return

        updated = 0
        for member in guild.members:
            if member.bot:
                continue

            try:
                if await self.apply_nickname(member):
                    updated += 1
            except Exception as e:
                logger.error(
                    "Error aplicando nickname a '%s' en '%s': %s",
                    member.display_name,
                    guild.name,
                    e,
                )

        if updated > 0:
            logger.info(f"[{guild.name}] Autoname sync: {updated} nicknames actualizados")

    async def on_config_changed(self, guild: discord.Guild, key: str) -> None:
        """Callback cuando cambia la configuracion del cog.

        Args:
            guild (discord.Guild): Guild donde cambio la config
            key (str): Clave de configuracion que cambio
        """
        # Re-sincronizar si cambia la configuracion de roles, prefijos o formato
        resync_keys = (ConfigKey.ROLE_TAGS, ConfigKey.ROLE_PREFIXES, ConfigKey.TAG_FORMAT)
        if key in resync_keys:
            logger.info(f"[{guild.name}] Configuración '{key}' cambió, re-sincronizando")
            await self._sync_guild(guild)


async def setup(bot: DiscordBot) -> None:
    """Cargar el cog de autoname.

    Args:
        bot (DiscordBot): Instancia del bot
    """
    get_config_schema_service().register_schema(AUTONAME_CONFIG_SCHEMA)
    await bot.add_cog(AutonameCog(bot))


async def teardown(bot: DiscordBot) -> None:
    """Descargar el cog de autoname.

    Args:
        bot (DiscordBot): Instancia del bot
    """
    get_config_schema_service().unregister_schema(COG_NAME)
