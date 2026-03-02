"""Cog de verificacion de usuarios."""

import logging
from datetime import UTC, datetime
from typing import Any

import discord
from discord.ext import commands, tasks

from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import delete_message
from discord_bot.verification.config import COG_NAME, VERIFICATION_CONFIG_SCHEMA
from discord_bot.verification.enums import ConfigKey, VerificationType
from discord_bot.verification.formatters import create_panel_embed, format_message
from discord_bot.verification.handlers import (
    handle_accept,
    handle_dm_screenshots,
    handle_reject,
    handle_review,
    handle_verification_start,
    show_rejection_select,
    update_mod_message_cancelled,
)
from discord_bot.verification.panel import check_verification_message, get_mod_channel
from discord_bot.verification.service import VerificationService
from discord_bot.verification.views import VerificationPanelView

logger = logging.getLogger(__name__)


class VerificationCog(commands.Cog):
    """Cog para el sistema de verificacion de usuarios."""

    def __init__(self, bot: DiscordBot) -> None:
        """Inicializar el cog de verificacion.

        Args:
            bot (DiscordBot): Instancia del bot
        """
        self.bot = bot
        self._pending_dm_verifications: dict[int, tuple[int, int]] = {}
        self._last_health_check: dict[int, datetime] = {}
        self._health_check_started = False

    def get_locked_options(self) -> dict[str, dict[str, Any]]:
        """Obtener opciones bloqueadas por configuración de despliegue.

        Returns:
            dict[str, dict[str, Any]]: Mapa de key -> {locked, reason}
        """
        return {}

    async def cog_load(self) -> None:
        """Registrar vistas persistentes y restaurar estado al cargar el cog."""
        self.bot.add_view(VerificationPanelView())

        # Restaurar verificaciones pendientes desde la base de datos
        await self._restore_pending_verifications()

        # El health check se inicia despues de que el bot este listo
        if not self._health_check_started:
            self.health_check_loop.start()
            self._health_check_started = True

    async def _restore_pending_verifications(self) -> None:
        """Restaurar verificaciones pendientes desde la base de datos."""
        async with self.bot.database.session() as session:
            service = VerificationService(session=session)
            pending_requests = await service.get_all_pending_screenshots()

            for request in pending_requests:
                self._pending_dm_verifications[request.user_id] = (
                    request.guild_id,
                    request.id,
                )

            if pending_requests:
                logger.info(f"Restauradas {len(pending_requests)} verificaciones pendientes")

    async def cog_unload(self) -> None:
        """Detener tareas al descargar el cog."""
        if self._health_check_started:
            self.health_check_loop.cancel()
            self._health_check_started = False

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

    # Claves de configuración que requieren actualizar el panel
    _PANEL_UPDATE_KEYS = frozenset(
        {
            ConfigKey.VERIFICATION_ENABLED,
            ConfigKey.VERIFICATION_CHANNEL,
            ConfigKey.MOD_NOTIFICATION_CHANNEL,
            ConfigKey.VERIFY_BUTTON_TEXT,
            ConfigKey.VERIFY_ALLY_BUTTON_TEXT,
            ConfigKey.VERIFICATION_PANEL_MESSAGE,
            ConfigKey.VERIFICATION_DISABLED_MESSAGE,
        }
    )

    async def on_config_changed(self, guild: discord.Guild, key: str) -> None:
        """Manejar cambios de configuración desde el dashboard web.

        Args:
            guild (discord.Guild): Guild donde cambió la configuración
            key (str): Clave de configuración que cambió
        """
        if key in self._PANEL_UPDATE_KEYS:
            logger.info(f"[{guild.name}] Configuración '{key}' cambió, actualizando panel")
            await self._check_verification_message(guild=guild, recreate=True)

    async def on_cog_toggled(self, guild: discord.Guild, enabled: bool) -> None:
        """Manejar cuando el cog es habilitado o deshabilitado.

        Args:
            guild (discord.Guild): Guild donde cambió el estado
            enabled (bool): True si fue habilitado, False si fue deshabilitado
        """
        if enabled:
            logger.info(f"[{guild.name}] Cog habilitado, creando panel")
            await self._check_verification_message(guild=guild, recreate=True)
            return

        logger.info(f"[{guild.name}] Cog deshabilitado, eliminando panel")

        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            config = await config_service.get_all_config(guild_id=guild.id, cog_name=COG_NAME)

            panel_message_id = config.get(ConfigKey.PANEL_MESSAGE_ID)
            panel_channel_id = config.get(ConfigKey.PANEL_CHANNEL_ID)

            if not panel_message_id or not panel_channel_id:
                return

            await delete_message(
                guild=guild,
                channel_id=panel_channel_id,
                message_id=panel_message_id,
            )

            await config_service.set_value(
                guild_id=guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.PANEL_MESSAGE_ID,
                value=None,
            )
            await config_service.set_value(
                guild_id=guild.id,
                cog_name=COG_NAME,
                key=ConfigKey.PANEL_CHANNEL_ID,
                value=None,
            )
            await session.commit()

    @tasks.loop(minutes=1)
    async def health_check_loop(self) -> None:
        """Verificar periodicamente que los paneles de verificacion existen.

        Cada guild tiene su propio intervalo configurado. Este loop corre
        cada minuto y verifica si cada guild esta listo para su health check.
        """
        await self._run_health_check()

    @health_check_loop.before_loop
    async def before_health_check(self) -> None:
        """Esperar a que el bot este listo antes de iniciar el health check."""
        await self.bot.wait_until_ready()
        # Limpiar verificaciones de usuarios que salieron mientras el bot estaba offline
        await self._cleanup_stale_verifications()
        # Ejecutar inmediatamente al iniciar para todos los guilds
        await self._run_health_check(force_all=True)

    async def _cleanup_stale_verifications(self) -> None:
        """Cancelar verificaciones de usuarios que salieron mientras el bot estaba offline."""
        async with self.bot.database.session() as session:
            service = VerificationService(session=session)
            pending = await service.get_all_pending()

            if not pending:
                return

            config_service = ConfigService(session=session)
            cancelled_count = 0

            for request in pending:
                guild = self.bot.get_guild(request.guild_id)
                if not guild:
                    continue

                member = guild.get_member(request.user_id)
                if member:
                    continue

                # Usuario no está en el servidor, cancelar verificación
                await service.cancel(request_id=request.id)

                # Limpiar de memoria si estaba pendiente
                if request.user_id in self._pending_dm_verifications:
                    del self._pending_dm_verifications[request.user_id]

                # Actualizar mensaje de moderación
                config = await config_service.get_all_config(
                    guild_id=request.guild_id, cog_name=COG_NAME
                )
                await update_mod_message_cancelled(
                    guild=guild,
                    request=request,
                    config=config,
                )

                cancelled_count += 1
                logger.info(
                    f"[{guild.name}] Verificacion {request.id} cancelada "
                    f"(usuario {request.username} ya no esta en el servidor)"
                )

            if cancelled_count > 0:
                await session.commit()
                logger.info(f"Limpiadas {cancelled_count} verificaciones obsoletas")

    async def _run_health_check(self, force_all: bool = False) -> None:
        """Ejecutar verificacion de salud de paneles en guilds que esten listos.

        Args:
            force_all (bool): Si True, ejecuta para todos los guilds ignorando intervalos
        """
        now = datetime.now(UTC)

        for guild in self.bot.guilds:
            try:
                # Obtener intervalo configurado para este guild
                interval = await self._get_health_check_interval(guild.id)

                # Si intervalo es 0, health check desactivado para este guild
                if interval == 0:
                    continue

                # Verificar si es momento de ejecutar (a menos que sea forzado)
                if not force_all:
                    last_check = self._last_health_check.get(guild.id)
                    if last_check:
                        seconds_since_last = (now - last_check).total_seconds()
                        if seconds_since_last < interval * 60:
                            continue  # Aun no es momento

                # Ejecutar health check y registrar timestamp
                await self._check_verification_message(guild=guild)
                self._last_health_check[guild.id] = now

            except Exception as e:
                logger.error(f"[{guild.name}] Error en health check: {e}")

    async def _get_health_check_interval(self, guild_id: int) -> int:
        """Obtener el intervalo de health check configurado para un guild.

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
                key=ConfigKey.HEALTH_CHECK_INTERVAL,
            )
            return interval if interval is not None else 30

    async def _get_all_config(
        self,
        guild_id: int,
        config_service: ConfigService | None = None,
    ) -> dict[str, Any]:
        """Obtener toda la configuracion del cog para un guild.

        Args:
            guild_id (int): ID del guild
            config_service (ConfigService | None): Servicio existente para reutilizar sesion

        Returns:
            dict[str, Any]: Diccionario con toda la configuracion
        """
        if config_service:
            return await config_service.get_all_config(guild_id=guild_id, cog_name=COG_NAME)
        async with self.bot.database.session() as session:
            svc = ConfigService(session=session)
            return await svc.get_all_config(guild_id=guild_id, cog_name=COG_NAME)

    def _format_message(self, template: str | None = None, **kwargs: str | None) -> str:
        """Reemplazar placeholders en un mensaje.

        Args:
            template (str | None): Plantilla del mensaje
            **kwargs: Placeholders a reemplazar (ej: username="Juan", status="Pendiente")

        Returns:
            str: Mensaje formateado
        """
        return format_message(template, **kwargs)

    def _create_panel_embed(self, text: str) -> discord.Embed:
        """Crear un embed para el panel de verificación.

        Args:
            text (str): Texto del mensaje que puede contener URLs de imagen

        Returns:
            discord.Embed: Embed con el mensaje formateado
        """
        return create_panel_embed(text)

    def _get_mod_channel(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
    ) -> discord.TextChannel | None:
        """Obtener canal de moderacion si esta configurado y accesible.

        Args:
            guild (discord.Guild): Guild
            config (dict[str, Any]): Configuracion del cog

        Returns:
            discord.TextChannel | None: Canal de moderacion o None si no disponible
        """
        return get_mod_channel(guild=guild, config=config, bot_user=self.bot.user)

    async def _check_verification_message(
        self,
        guild: discord.Guild,
        recreate: bool = False,
    ) -> None:
        """Verificar y restaurar panel de verificacion de un guild.

        Args:
            guild (discord.Guild): Guild a verificar
            recreate (bool): Si True, elimina el panel existente y lo recrea
        """
        await check_verification_message(cog=self, guild=guild, recreate=recreate)

    async def _create_verification_message(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        config: dict[str, Any],
        config_service: ConfigService,
        session: Any,
    ) -> None:
        """Crear panel de verificacion en un canal.

        Args:
            guild (discord.Guild): Guild del panel
            channel (discord.TextChannel): Canal donde crear
            config (dict[str, Any]): Configuracion del cog
            config_service (ConfigService): Servicio de configuracion
            session (Any): Sesion de base de datos
        """
        from discord_bot.verification.panel import create_verification_message

        await create_verification_message(
            cog=self,
            guild=guild,
            channel=channel,
            config=config,
            config_service=config_service,
            session=session,
        )

    async def _update_mod_message_for_review(
        self,
        channel: discord.TextChannel,
        request: Any,
        verification_service: VerificationService,
        config: dict[str, Any],
    ) -> None:
        """Actualizar mensaje de moderacion cuando se reciben las capturas.

        Args:
            channel (discord.TextChannel): Canal de moderacion
            request (VerificationRequest): Solicitud de verificacion
            verification_service (VerificationService): Servicio de verificacion
            config (dict[str, Any]): Configuracion del cog
        """
        from discord_bot.verification.handlers import update_mod_message_for_review

        await update_mod_message_for_review(
            cog=self,
            channel=channel,
            request=request,
            verification_service=verification_service,
            config=config,
        )

    async def _validate_mod_action(
        self,
        interaction: discord.Interaction,
        request_id: int,
        session: Any,
        permission_error_key: ConfigKey,
        permission_error_default: str,
    ) -> Any:
        """Validar y preparar contexto para acciones de moderacion.

        Args:
            interaction (discord.Interaction): Interaccion del moderador
            request_id (int): ID de la solicitud
            session (AsyncSession): Sesion de base de datos
            permission_error_key (ConfigKey): Clave del mensaje de error
            permission_error_default (str): Mensaje por defecto

        Returns:
            ModActionContext | None: Contexto validado o None si fallo
        """
        from discord_bot.verification.handlers import validate_mod_action

        return await validate_mod_action(
            cog=self,
            interaction=interaction,
            request_id=request_id,
            session=session,
            permission_error_key=permission_error_key,
            permission_error_default=permission_error_default,
        )

    async def handle_verification_start(
        self, interaction: discord.Interaction, verification_type: VerificationType
    ) -> None:
        """Manejar inicio de verificacion cuando el usuario hace clic en un boton.

        Args:
            interaction (discord.Interaction): Interaccion del usuario
            verification_type (VerificationType): Tipo de verificacion
        """
        await handle_verification_start(
            cog=self, interaction=interaction, verification_type=verification_type
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Manejar mensajes DM con capturas de pantalla.

        Args:
            message (discord.Message): Mensaje recibido
        """
        if message.guild is not None:
            return
        if message.author.bot:
            return

        # Buscar verificacion pendiente en memoria o en base de datos
        verification_info = await self._get_pending_verification(message.author.id)

        if verification_info is None:
            await self._respond_no_pending_verification(message)
            return

        guild_id, request_id = verification_info

        # Verificar si el cog esta habilitado
        if not await self._is_cog_enabled(guild_id):
            return

        await handle_dm_screenshots(
            cog=self, message=message, guild_id=guild_id, request_id=request_id
        )

    async def _get_pending_verification(self, user_id: int) -> tuple[int, int] | None:
        """Obtener verificacion pendiente de un usuario.

        Busca primero en memoria, luego en base de datos.
        Si encuentra en DB, restaura el estado en memoria.

        Args:
            user_id (int): ID del usuario

        Returns:
            tuple[int, int] | None: (guild_id, request_id) o None si no hay pendiente
        """
        # Primero buscar en memoria (mas rapido)
        if user_id in self._pending_dm_verifications:
            return self._pending_dm_verifications[user_id]

        # Buscar en base de datos (por si el bot reinicio)
        async with self.bot.database.session() as session:
            service = VerificationService(session=session)
            pending = await service.get_any_pending_by_user(user_id)

            if pending:
                # Restaurar en memoria para futuras consultas
                self._pending_dm_verifications[user_id] = (pending.guild_id, pending.id)
                return (pending.guild_id, pending.id)

        return None

    async def _respond_no_pending_verification(self, message: discord.Message) -> None:
        """Responder cuando el usuario envia un DM sin verificacion activa.

        Args:
            message (discord.Message): Mensaje recibido
        """
        # Buscar un servidor comun para obtener la configuracion
        guild_id = None
        for guild in self.bot.guilds:
            if guild.get_member(message.author.id):
                # Verificar si el cog esta habilitado en este servidor
                if await self._is_cog_enabled(guild.id):
                    guild_id = guild.id
                    break

        # Obtener mensaje de configuracion o usar default
        default_message = (
            "No tienes ninguna verificación en curso. "
            "Si deseas verificarte, usa el panel de verificación en el servidor."
        )

        if guild_id:
            config = await self._get_all_config(guild_id)
            response = config.get(ConfigKey.NO_PENDING_VERIFICATION_MESSAGE) or default_message
        else:
            response = default_message

        try:
            await message.reply(response)
        except discord.Forbidden:
            pass  # No se pudo responder

    async def handle_accept(self, interaction: discord.Interaction, request_id: int) -> None:
        """Manejar aprobacion de verificacion.

        Args:
            interaction (discord.Interaction): Interaccion del moderador
            request_id (int): ID de la solicitud
        """
        await handle_accept(cog=self, interaction=interaction, request_id=request_id)

    async def show_rejection_select(
        self, interaction: discord.Interaction, request_id: int
    ) -> None:
        """Mostrar selector de motivos de rechazo.

        Args:
            interaction (discord.Interaction): Interaccion del moderador
            request_id (int): ID de la solicitud
        """
        await show_rejection_select(cog=self, interaction=interaction, request_id=request_id)

    async def handle_reject(
        self, interaction: discord.Interaction, request_id: int, reason: str
    ) -> None:
        """Manejar rechazo de verificacion.

        Args:
            interaction (discord.Interaction): Interaccion del moderador
            request_id (int): ID de la solicitud
            reason (str): Motivo del rechazo
        """
        await handle_reject(cog=self, interaction=interaction, request_id=request_id, reason=reason)

    async def handle_review(self, interaction: discord.Interaction, request_id: int) -> None:
        """Manejar revisión de verificación auto-rechazada.

        Args:
            interaction (discord.Interaction): Interaccion del moderador
            request_id (int): ID de la solicitud
        """
        await handle_review(cog=self, interaction=interaction, request_id=request_id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Cancelar verificaciones pendientes cuando un usuario sale.

        Args:
            member (discord.Member): Miembro que salio
        """
        if member.id in self._pending_dm_verifications:
            del self._pending_dm_verifications[member.id]

        async with self.bot.database.session() as session:
            verification_service = VerificationService(session=session)
            pending = await verification_service.get_pending_by_user(
                guild_id=member.guild.id, user_id=member.id
            )
            if pending:
                await verification_service.cancel(request_id=pending.id)
                await session.commit()

                # Actualizar el mensaje de moderación
                config_service = ConfigService(session=session)
                config = await config_service.get_all_config(
                    guild_id=member.guild.id, cog_name=COG_NAME
                )
                await update_mod_message_cancelled(
                    guild=member.guild,
                    request=pending,
                    config=config,
                )

                logger.info(
                    f"Verificacion cancelada para {member.name} "
                    f"(salio del servidor {member.guild.name})"
                )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Manejar interacciones de botones de moderacion con IDs dinamicos.

        Los botones de aceptar/rechazar tienen custom_ids dinamicos como
        'verification:accept:123' que incluyen el request_id. Este listener
        es el unico manejador de estos botones (no tienen callbacks en la vista),
        lo que permite que funcionen incluso despues de reiniciar el bot.

        Args:
            interaction (discord.Interaction): Interaccion recibida
        """
        if interaction.type != discord.InteractionType.component:
            return

        custom_id: str = str(interaction.data.get("custom_id", "") if interaction.data else "")

        # Manejar boton de aceptar: verification:accept:{request_id}
        if custom_id.startswith("verification:accept:"):
            try:
                request_id = int(custom_id.split(":")[2])
                await self.handle_accept(interaction=interaction, request_id=request_id)
            except (ValueError, IndexError):
                logger.error(f"Custom ID invalido para accept: {custom_id}")
            return

        # Manejar boton de rechazar: verification:reject:{request_id}
        if custom_id.startswith("verification:reject:"):
            try:
                request_id = int(custom_id.split(":")[2])
                await self.show_rejection_select(interaction=interaction, request_id=request_id)
            except (ValueError, IndexError):
                logger.error(f"Custom ID invalido para reject: {custom_id}")
            return

        # Manejar boton de revisar auto-rechazo: verification:review:{request_id}
        if custom_id.startswith("verification:review:"):
            try:
                request_id = int(custom_id.split(":")[2])
                await self.handle_review(interaction=interaction, request_id=request_id)
            except (ValueError, IndexError):
                logger.error(f"Custom ID invalido para review: {custom_id}")
            return


async def setup(bot: DiscordBot) -> None:
    """Cargar el cog de verificacion.

    Args:
        bot (DiscordBot): Instancia del bot
    """
    get_config_schema_service().register_schema(VERIFICATION_CONFIG_SCHEMA)
    await bot.add_cog(VerificationCog(bot))


async def teardown(bot: DiscordBot) -> None:
    """Descargar el cog de verificacion.

    Args:
        bot (DiscordBot): Instancia del bot
    """
    get_config_schema_service().unregister_schema("verification")
