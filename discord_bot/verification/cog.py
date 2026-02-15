"""Cog de verificacion de usuarios."""

import logging
from typing import Any, NamedTuple

import discord
from discord.ext import commands, tasks
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.bot import DiscordBot
from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import delete_message, has_any_role
from discord_bot.verification.enums import ConfigKey, VerificationStatus, VerificationType
from discord_bot.verification.models import VerificationRequest
from discord_bot.verification.service import VerificationService
from discord_bot.verification.views import (
    ModReviewView,
    RejectionReasonView,
    VerificationPanelView,
)

logger = logging.getLogger(__name__)

COG_NAME = "verification"


class ModActionContext(NamedTuple):
    """Contexto validado para acciones de moderacion."""

    config: dict[str, Any]
    request: "VerificationRequest"
    service: "VerificationService"


VERIFICATION_CONFIG_SCHEMA = CogConfigSchema(
    cog_name=COG_NAME,
    display_name="Verificacion",
    description="Sistema de verificacion de usuarios con capturas de pantalla",
    icon="✅",
    options=[
        # ===== 1. OPCIONES GENERALES =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_ENABLED,
            name="Verificacion habilitada",
            description="Habilitar o deshabilitar el sistema de verificacion",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
            group="Opciones",
        ),
        ConfigOption(
            key=ConfigKey.BLOCK_ALREADY_VERIFIED,
            name="Bloquear usuarios verificados",
            description="Impedir que usuarios con roles de verificado inicien nueva verificacion",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
            group="Opciones",
        ),
        # ===== 2. PANEL DE VERIFICACIÓN =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_CHANNEL,
            name="Canal de verificacion",
            description=(
                "Canal donde se publica el panel de verificacion con botones. "
                "Solo se muestran canales donde el bot tiene permiso de escritura."
            ),
            option_type=ConfigOptionType.CHANNEL,
            group="Panel de verificación",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_PANEL_MESSAGE,
            name="Mensaje del panel",
            description=(
                "Mensaje que aparece en el panel de verificacion. "
                "Si incluyes una URL de imagen (terminada en .png, .jpg, .gif, etc.) "
                "se mostrara como imagen en el embed."
            ),
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Bienvenido a {server_name}!**\n\n"
                "Para acceder al servidor, necesitas verificarte. "
                "Haz clic en el boton correspondiente para comenzar."
            ),
            max_length=4000,
            placeholders=["server_name"],
            group="Panel de verificación",
        ),
        ConfigOption(
            key=ConfigKey.VERIFY_BUTTON_TEXT,
            name="Texto boton verificar",
            description="Texto del boton de verificacion normal",
            option_type=ConfigOptionType.STRING,
            default="Verificar",
            max_length=80,
            group="Panel de verificación",
        ),
        ConfigOption(
            key=ConfigKey.VERIFY_ALLY_BUTTON_TEXT,
            name="Texto boton aliado",
            description="Texto del boton de verificacion como aliado",
            option_type=ConfigOptionType.STRING,
            default="Verificar como Aliado",
            max_length=80,
            group="Panel de verificación",
        ),
        ConfigOption(
            key=ConfigKey.HEALTH_CHECK_INTERVAL,
            name="Intervalo de verificacion (minutos)",
            description="Frecuencia de verificacion del panel (0 para desactivar)",
            option_type=ConfigOptionType.INTEGER,
            default=30,
            min_value=0,
            max_value=1440,
            group="Panel de verificación",
        ),
        # ===== 2. VERIFICACIÓN NORMAL =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY,
            name="Nombre tipo normal",
            description="Nombre a mostrar para verificacion normal en mensajes",
            option_type=ConfigOptionType.STRING,
            default="Normal",
            max_length=50,
            group="Verificación (Normal)",
        ),
        ConfigOption(
            key=ConfigKey.DM_INSTRUCTIONS_MESSAGE,
            name="Instrucciones por DM",
            description="Mensaje enviado al usuario por DM con las instrucciones",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Instrucciones de Verificacion**\n\n"
                "Hola {username}! Para completar tu verificacion en **{server_name}**, "
                "envia **2 capturas de pantalla** en un solo mensaje."
            ),
            max_length=4000,
            placeholders=["username", "user_mention", "server_name", "verification_type"],
            group="Verificación (Normal)",
        ),
        ConfigOption(
            key=ConfigKey.REGULAR_ROLES_ADD,
            name="Roles a agregar",
            description="Roles que se agregan al aprobar verificacion normal",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Verificación (Normal)",
        ),
        ConfigOption(
            key=ConfigKey.REGULAR_ROLES_REMOVE,
            name="Roles a quitar",
            description="Roles que se quitan al aprobar verificacion normal",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Verificación (Normal)",
        ),
        ConfigOption(
            key=ConfigKey.APPROVAL_MESSAGE_REGULAR,
            name="Mensaje de aprobacion",
            description="Mensaje enviado al usuario cuando es aprobado",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Verificacion aprobada!**\n\n"
                "Tu verificacion en **{server_name}** ha sido aprobada. "
                "Ya tienes acceso completo al servidor."
            ),
            max_length=2000,
            placeholders=["username", "server_name"],
            group="Verificación (Normal)",
        ),
        # ===== 3. VERIFICACIÓN ALIADO =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY,
            name="Nombre tipo aliado",
            description="Nombre a mostrar para verificacion de aliado en mensajes",
            option_type=ConfigOptionType.STRING,
            default="Aliado",
            max_length=50,
            group="Verificación (Aliado)",
        ),
        ConfigOption(
            key=ConfigKey.DM_INSTRUCTIONS_ALLY_MESSAGE,
            name="Instrucciones por DM",
            description="Mensaje enviado al usuario por DM con las instrucciones",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Instrucciones de Verificacion (Aliado)**\n\n"
                "Hola {username}! Para completar tu verificacion como aliado en **{server_name}**, "
                "envia **2 capturas de pantalla** en un solo mensaje."
            ),
            max_length=4000,
            placeholders=["username", "user_mention", "server_name", "verification_type"],
            group="Verificación (Aliado)",
        ),
        ConfigOption(
            key=ConfigKey.ALLY_ROLES_ADD,
            name="Roles a agregar",
            description="Roles que se agregan al aprobar verificacion de aliado",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Verificación (Aliado)",
        ),
        ConfigOption(
            key=ConfigKey.ALLY_ROLES_REMOVE,
            name="Roles a quitar",
            description="Roles que se quitan al aprobar verificacion de aliado",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Verificación (Aliado)",
        ),
        ConfigOption(
            key=ConfigKey.APPROVAL_MESSAGE_ALLY,
            name="Mensaje de aprobacion",
            description="Mensaje enviado al usuario cuando es aprobado como aliado",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Verificacion de aliado aprobada!**\n\n"
                "Tu verificacion como aliado en **{server_name}** ha sido aprobada. "
                "Ya tienes acceso como aliado al servidor."
            ),
            max_length=2000,
            placeholders=["username", "server_name"],
            group="Verificación (Aliado)",
        ),
        # ===== 4. PANEL DE MODERACIÓN =====
        ConfigOption(
            key=ConfigKey.MOD_NOTIFICATION_CHANNEL,
            name="Canal de moderacion",
            description=(
                "Canal donde los moderadores reciben notificaciones de verificacion. "
                "Solo se muestran canales donde el bot tiene permiso de escritura."
            ),
            option_type=ConfigOptionType.CHANNEL,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.MOD_ROLES,
            name="Roles de moderador",
            description="Roles que pueden aprobar/rechazar verificaciones",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.MOD_MESSAGE_TEMPLATE,
            name="Mensaje de moderacion",
            description="Mensaje en el canal de moderacion (se actualiza con el progreso)",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Solicitud de verificacion**\n\n"
                "**Usuario:** {user_mention} ({username})\n"
                "**Tipo:** {verification_type}\n\n"
                "{status}"
            ),
            max_length=2000,
            placeholders=["username", "user_mention", "verification_type", "status"],
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.DELETE_PROCESSED_MESSAGES,
            name="Eliminar mensajes procesados",
            description="Eliminar mensajes del canal de moderacion tras aceptar/rechazar",
            option_type=ConfigOptionType.BOOLEAN,
            default=False,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.ACCEPT_BUTTON_TEXT,
            name="Texto boton aceptar",
            description="Texto del boton de aceptar para moderadores",
            option_type=ConfigOptionType.STRING,
            default="Aceptar",
            max_length=80,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_BUTTON_TEXT,
            name="Texto boton rechazar",
            description="Texto del boton de rechazar para moderadores",
            option_type=ConfigOptionType.STRING,
            default="Rechazar",
            max_length=80,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.HISTORY_LABEL,
            name="Etiqueta historial",
            description="Texto para la seccion de historial en el mensaje de revision",
            option_type=ConfigOptionType.STRING,
            default="Historial",
            max_length=50,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_AWAITING_SCREENSHOTS,
            name="Estado: Esperando capturas",
            description="Texto del estado cuando se espera que el usuario envie capturas",
            option_type=ConfigOptionType.STRING,
            default="⏳ **Estado:** Esperando capturas de pantalla...",
            max_length=200,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_PENDING_REVIEW,
            name="Estado: Pendiente de revision",
            description="Texto del estado cuando las capturas estan listas para revision",
            option_type=ConfigOptionType.STRING,
            default="🔍 **Estado:** Pendiente de revision",
            max_length=200,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_APPROVED,
            name="Estado: Aprobado",
            description="Texto del estado cuando la verificacion fue aprobada",
            option_type=ConfigOptionType.STRING,
            default="✅ **Estado:** Aprobado por {moderator}",
            max_length=200,
            placeholders=["moderator"],
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_REJECTED,
            name="Estado: Rechazado",
            description="Texto del estado cuando la verificacion fue rechazada",
            option_type=ConfigOptionType.STRING,
            default="❌ **Estado:** Rechazado por {moderator}\n**Motivo:** {reason}",
            max_length=200,
            placeholders=["moderator", "reason"],
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_REASON_1,
            name="Motivo de rechazo 1",
            description="Primer motivo predefinido para rechazar verificaciones",
            option_type=ConfigOptionType.STRING,
            default="Capturas incorrectas o ilegibles",
            max_length=100,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_REASON_2,
            name="Motivo de rechazo 2",
            description="Segundo motivo predefinido para rechazar verificaciones",
            option_type=ConfigOptionType.STRING,
            default="Nombre de usuario no coincide",
            max_length=100,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_REASON_3,
            name="Motivo de rechazo 3",
            description="Tercer motivo predefinido para rechazar verificaciones",
            option_type=ConfigOptionType.STRING,
            default="Informacion insuficiente",
            max_length=100,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_REASON_4,
            name="Motivo de rechazo 4",
            description="Cuarto motivo predefinido (dejar vacio para ocultar)",
            option_type=ConfigOptionType.STRING,
            default="",
            max_length=100,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_SELECT_PLACEHOLDER,
            name="Placeholder selector de rechazo",
            description="Texto del placeholder del selector de motivos",
            option_type=ConfigOptionType.STRING,
            default="Selecciona el motivo de rechazo...",
            max_length=100,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_SELECT_MESSAGE,
            name="Mensaje selector de rechazo",
            description="Mensaje mostrado al moderador antes del selector de motivos",
            option_type=ConfigOptionType.STRING,
            default="Selecciona el motivo de rechazo:",
            max_length=200,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_OTHER_LABEL,
            name="Etiqueta 'Otro motivo'",
            description="Texto de la opcion para escribir un motivo personalizado",
            option_type=ConfigOptionType.STRING,
            default="Otro motivo...",
            max_length=100,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_OTHER_DESCRIPTION,
            name="Descripcion 'Otro motivo'",
            description="Descripcion de la opcion para escribir un motivo personalizado",
            option_type=ConfigOptionType.STRING,
            default="Escribir un motivo personalizado",
            max_length=100,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_MODAL_TITLE,
            name="Titulo modal de rechazo",
            description="Titulo del modal para escribir un motivo personalizado",
            option_type=ConfigOptionType.STRING,
            default="Motivo de Rechazo",
            max_length=45,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_MODAL_LABEL,
            name="Etiqueta campo motivo",
            description="Etiqueta del campo de texto en el modal de rechazo",
            option_type=ConfigOptionType.STRING,
            default="Motivo",
            max_length=45,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_MODAL_PLACEHOLDER,
            name="Placeholder campo motivo",
            description="Texto de ayuda en el campo de texto del modal de rechazo",
            option_type=ConfigOptionType.STRING,
            default="Explica por que se rechaza la verificacion...",
            max_length=100,
            group="Panel de moderación",
        ),
        # ===== 5. MENSAJES AL USUARIO =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_STARTED_MESSAGE,
            name="Verificacion iniciada",
            description="Mensaje mostrado al usuario cuando inicia la verificacion",
            option_type=ConfigOptionType.STRING,
            default="Revisa tus mensajes directos para continuar con la verificacion.",
            max_length=500,
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.SCREENSHOTS_RECEIVED_MESSAGE,
            name="Capturas recibidas",
            description="Mensaje de confirmacion cuando el usuario envia las capturas",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "Tus capturas han sido recibidas correctamente. "
                "Un moderador revisara tu solicitud pronto."
            ),
            max_length=2000,
            placeholders=["username", "server_name"],
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_MESSAGE,
            name="Mensaje de rechazo",
            description="Mensaje enviado al usuario cuando es rechazado",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Verificacion rechazada**\n\n"
                "Tu verificacion en **{server_name}** ha sido rechazada.\n"
                "**Motivo:** {reason}\n\n"
                "Puedes intentarlo de nuevo si lo deseas."
            ),
            max_length=2000,
            placeholders=["username", "server_name", "verification_type", "reason"],
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.WRONG_IMAGES_MESSAGE,
            name="Error: imagenes incorrectas",
            description="Mensaje cuando no se envian exactamente 2 imagenes",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "Debes enviar exactamente **2 capturas de pantalla** "
                "en el mismo mensaje. Por favor, intentalo de nuevo."
            ),
            max_length=2000,
            placeholders=["username"],
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.DM_DISABLED_MESSAGE,
            name="Error: DMs deshabilitados",
            description="Mensaje cuando no se puede enviar DM al usuario",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "No pude enviarte un mensaje directo. "
                "Por favor, habilita los DMs de miembros del servidor e intentalo de nuevo."
            ),
            max_length=1000,
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.ALREADY_PENDING_MESSAGE,
            name="Error: verificacion pendiente",
            description="Mensaje cuando el usuario ya tiene una verificacion pendiente",
            option_type=ConfigOptionType.TEXTAREA,
            default="Ya tienes una solicitud de verificacion pendiente. Por favor, espera.",
            max_length=1000,
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.ALREADY_VERIFIED_MESSAGE,
            name="Error: ya verificado",
            description="Mensaje cuando el usuario ya tiene los roles de verificacion",
            option_type=ConfigOptionType.STRING,
            default="Ya tienes los roles de verificacion. No necesitas verificarte de nuevo.",
            max_length=500,
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_DISABLED_MESSAGE,
            name="Error: verificacion deshabilitada",
            description="Mensaje mostrado cuando la verificacion no esta configurada",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "⚠️ **Verificacion no disponible**\n\n"
                "La verificacion esta temporalmente deshabilitada. "
                "Por favor, contacta a un administrador."
            ),
            max_length=2000,
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.REQUEST_NOT_FOUND_MESSAGE,
            name="Error: solicitud no encontrada",
            description="Mensaje cuando no se encuentra la solicitud de verificacion",
            option_type=ConfigOptionType.STRING,
            default="Error: No se encontro tu solicitud de verificacion.",
            max_length=500,
            group="Mensajes al usuario",
        ),
        # ===== 6. MENSAJES DE MODERACIÓN =====
        ConfigOption(
            key=ConfigKey.MOD_APPROVED_CONFIRMATION,
            name="Confirmacion de aprobacion",
            description="Mensaje mostrado al moderador al aprobar",
            option_type=ConfigOptionType.STRING,
            default="Verificacion aprobada para {username}.",
            max_length=500,
            placeholders=["username"],
            group="Mensajes de moderación",
        ),
        ConfigOption(
            key=ConfigKey.MOD_REJECTED_CONFIRMATION,
            name="Confirmacion de rechazo",
            description="Mensaje mostrado al moderador al rechazar",
            option_type=ConfigOptionType.STRING,
            default="Verificacion rechazada para {username}.",
            max_length=500,
            placeholders=["username"],
            group="Mensajes de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REQUEST_ALREADY_PROCESSED_MESSAGE,
            name="Error: solicitud ya procesada",
            description="Mensaje cuando se intenta procesar una solicitud ya procesada",
            option_type=ConfigOptionType.STRING,
            default="Esta solicitud ya fue procesada.",
            max_length=500,
            group="Mensajes de moderación",
        ),
        ConfigOption(
            key=ConfigKey.NO_PERMISSION_APPROVE_MESSAGE,
            name="Error: sin permisos para aprobar",
            description="Mensaje cuando el moderador no tiene permisos para aprobar",
            option_type=ConfigOptionType.STRING,
            default="No tienes permisos para aprobar verificaciones.",
            max_length=500,
            group="Mensajes de moderación",
        ),
        ConfigOption(
            key=ConfigKey.NO_PERMISSION_REJECT_MESSAGE,
            name="Error: sin permisos para rechazar",
            description="Mensaje cuando el moderador no tiene permisos para rechazar",
            option_type=ConfigOptionType.STRING,
            default="No tienes permisos para rechazar verificaciones.",
            max_length=500,
            group="Mensajes de moderación",
        ),
    ],
)


class VerificationCog(commands.Cog):
    """Cog para el sistema de verificacion de usuarios."""

    def __init__(self, bot: DiscordBot) -> None:
        """Inicializar el cog de verificacion.

        Args:
            bot (DiscordBot): Instancia del bot
        """
        self.bot = bot
        self._pending_dm_verifications: dict[int, tuple[int, int]] = {}
        self._health_check_started = False

    async def cog_load(self) -> None:
        """Registrar vistas persistentes al cargar el cog."""
        self.bot.add_view(VerificationPanelView())
        # El health check se inicia despues de que el bot este listo
        if not self._health_check_started:
            self.health_check_loop.start()
            self._health_check_started = True

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
            logger.info(f"Configuración '{key}' cambió, actualizando panel en {guild.name}")
            await self._check_verification_message(guild=guild, force=True)

    async def on_cog_toggled(self, guild: discord.Guild, enabled: bool) -> None:
        """Manejar cuando el cog es habilitado o deshabilitado.

        Args:
            guild (discord.Guild): Guild donde cambió el estado
            enabled (bool): True si fue habilitado, False si fue deshabilitado
        """
        if enabled:
            logger.info(f"Cog habilitado en {guild.name}, creando panel")
            await self._check_verification_message(guild=guild, force=True)
            return

        logger.info(f"Cog deshabilitado en {guild.name}, eliminando panel")

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

    @tasks.loop(minutes=30)
    async def health_check_loop(self) -> None:
        """Verificar periodicamente que los paneles de verificacion existen."""
        await self._run_health_check()

    @health_check_loop.before_loop
    async def before_health_check(self) -> None:
        """Esperar a que el bot este listo antes de iniciar el health check."""
        await self.bot.wait_until_ready()
        # Ejecutar inmediatamente al iniciar, no esperar 30 minutos
        await self._run_health_check()

    async def _run_health_check(self) -> None:
        """Ejecutar verificacion de salud de paneles en todos los guilds."""
        for guild in self.bot.guilds:
            try:
                await self._check_verification_message(guild)
            except Exception as e:
                logger.error(f"Error en health check para guild {guild.id}: {e}")

    async def _check_verification_message(self, guild: discord.Guild, force: bool = False) -> None:
        """Verificar y restaurar panel de verificacion de un guild.

        Args:
            guild (discord.Guild): Guild a verificar
            force (bool): Si True, siempre recrea el panel (usado en cambios de config)
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)

            # Verificar si el cog esta habilitado
            if not await config_service.is_cog_enabled(guild.id, COG_NAME):
                return

            # Obtener toda la configuracion de una vez
            config = await config_service.get_all_config(guild_id=guild.id, cog_name=COG_NAME)

            # Verificar intervalo configurado (solo aplica si no es forzado)
            if not force:
                interval = config.get(ConfigKey.HEALTH_CHECK_INTERVAL)
                if interval == 0:
                    return  # Health check desactivado para este guild

            # Obtener canal configurado
            channel_id = config.get(ConfigKey.VERIFICATION_CHANNEL)
            if not channel_id:
                return  # No hay canal configurado

            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                logger.warning(
                    f"Canal de verificacion {channel_id} no encontrado en guild {guild.id}"
                )
                return

            # Obtener panel actual
            panel_message_id = config.get(ConfigKey.PANEL_MESSAGE_ID)
            panel_channel_id = config.get(ConfigKey.PANEL_CHANNEL_ID)

            # Si es forzado, eliminar panel viejo y crear nuevo
            if force:
                if panel_message_id and panel_channel_id:
                    await delete_message(
                        guild=guild,
                        channel_id=panel_channel_id,
                        message_id=panel_message_id,
                    )
                await self._create_verification_message(
                    guild=guild,
                    channel=channel,
                    config=config,
                    config_service=config_service,
                    session=session,
                )
                return

            # Caso 1: No hay panel, crear uno nuevo
            if not panel_message_id:
                logger.info(
                    f"Creando panel de verificacion en guild {guild.id}, canal {channel.name}"
                )
                await self._create_verification_message(
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
                await self._create_verification_message(
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
                    await self._create_verification_message(
                        guild=guild,
                        channel=channel,
                        config=config,
                        config_service=config_service,
                        session=session,
                    )
            except discord.NotFound:
                logger.info(f"Panel no encontrado en guild {guild.id}, restaurando...")
                await self._create_verification_message(
                    guild=guild,
                    channel=channel,
                    config=config,
                    config_service=config_service,
                    session=session,
                )
            except discord.Forbidden:
                logger.warning(f"Sin permisos para verificar panel en guild {guild.id}")

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
            config_service (ConfigService): Servicio de configuracion (para set_value)
            session (Any): Sesion de base de datos
        """
        # Verificar si la verificacion esta habilitada
        verification_enabled = config.get(ConfigKey.VERIFICATION_ENABLED)
        if verification_enabled is False:
            logger.info(f"Verificacion deshabilitada manualmente en guild {guild.id}")

        # Verificar que el canal de moderacion esta configurado y accesible
        mod_channel = self._get_mod_channel(guild=guild, config=config)
        if not mod_channel:
            logger.warning(
                f"Verificacion deshabilitada en guild {guild.id}: "
                f"canal de moderacion no configurado o sin permisos"
            )

        is_configured = verification_enabled is not False and mod_channel is not None

        if is_configured:
            # Verificacion habilitada - mostrar botones
            formatted_message = self._format_message(
                template=config.get(ConfigKey.VERIFICATION_PANEL_MESSAGE),
                server_name=guild.name,
            )
            view: discord.ui.View | None = VerificationPanelView(
                verify_label=config.get(ConfigKey.VERIFY_BUTTON_TEXT) or "Verificar",
                ally_label=config.get(ConfigKey.VERIFY_ALLY_BUTTON_TEXT) or "Verificar como Aliado",
            )
        else:
            # Verificacion deshabilitada - mostrar mensaje sin botones
            formatted_message = self._format_message(
                template=config.get(ConfigKey.VERIFICATION_DISABLED_MESSAGE),
                server_name=guild.name,
            )
            view = None

        # Crear embed si hay imagen en el mensaje
        embed, clean_text = self._create_panel_embed(formatted_message)

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
            logger.error(
                f"Sin permisos para enviar panel en guild {guild.id}, canal {channel.name}"
            )

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
        result = template or ""
        for key, value in kwargs.items():
            result = result.replace(f"{{{key}}}", value or "")
        return result

    def _create_panel_embed(self, text: str) -> tuple[discord.Embed | None, str]:
        """Crear un embed para el panel de verificacion si hay una imagen.

        Busca URLs de imagen en el texto y las usa para crear un embed.
        La URL de imagen se elimina del texto mostrado.

        Args:
            text (str): Texto del mensaje que puede contener URLs de imagen

        Returns:
            tuple[discord.Embed | None, str]: Embed (o None) y texto limpio
        """
        import re

        # Buscar URLs de imagen
        image_pattern = r"(https?://[^\s]+\.(?:png|jpg|jpeg|gif|webp)(?:\?[^\s]*)?)"
        match = re.search(image_pattern, text, re.IGNORECASE)

        if not match:
            return None, text

        image_url = match.group(1)
        # Eliminar la URL del texto (y lineas vacias extra)
        clean_text = re.sub(image_pattern, "", text, count=1, flags=re.IGNORECASE)
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()

        embed = discord.Embed(
            description=clean_text,
            color=discord.Color.blurple(),
        )
        embed.set_image(url=image_url)
        return embed, clean_text

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
        mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
        if not mod_channel_id:
            return None

        mod_channel = guild.get_channel(mod_channel_id)
        if not mod_channel or not isinstance(mod_channel, discord.TextChannel):
            return None

        # Verificar permisos del bot
        if self.bot.user is None:
            return None

        bot_member = guild.get_member(self.bot.user.id)
        if not bot_member:
            return None

        permissions = mod_channel.permissions_for(bot_member)
        if not permissions.send_messages:
            return None

        return mod_channel

    async def _validate_mod_action(
        self,
        interaction: discord.Interaction,
        request_id: int,
        session: AsyncSession,
        permission_error_key: ConfigKey,
        permission_error_default: str,
    ) -> ModActionContext | None:
        """Validar y preparar contexto para acciones de moderacion.

        Realiza todas las validaciones comunes para aprobar/rechazar:
        - Verificar permisos de moderador
        - Defer la interaccion
        - Obtener la solicitud
        - Verificar que existe y esta pendiente de revision

        Args:
            interaction (discord.Interaction): Interaccion del moderador
            request_id (int): ID de la solicitud
            session (AsyncSession): Sesion de base de datos
            permission_error_key (ConfigKey): Clave del mensaje de error de permisos
            permission_error_default (str): Mensaje por defecto si no esta configurado

        Returns:
            ModActionContext | None: Contexto validado o None si fallo alguna validacion
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return None

        config_service = ConfigService(session=session)
        config = await self._get_all_config(
            guild_id=interaction.guild.id, config_service=config_service
        )

        # Verificar permisos de moderador
        if not has_any_role(
            member=interaction.user, role_ids=config.get(ConfigKey.MOD_ROLES) or []
        ):
            await interaction.response.send_message(
                content=config.get(permission_error_key) or permission_error_default,
                ephemeral=True,
            )
            return None

        await interaction.response.defer()

        verification_service = VerificationService(session=session)
        request = await verification_service.get_request(request_id=request_id)

        if not request:
            await interaction.followup.send(
                content=config.get(ConfigKey.REQUEST_NOT_FOUND_MESSAGE)
                or "Solicitud no encontrada.",
                ephemeral=True,
            )
            return None

        if request.status != VerificationStatus.PENDING_REVIEW:
            await interaction.followup.send(
                content=config.get(ConfigKey.REQUEST_ALREADY_PROCESSED_MESSAGE)
                or "Esta solicitud ya fue procesada.",
                ephemeral=True,
            )
            return None

        return ModActionContext(config=config, request=request, service=verification_service)

    async def handle_verification_start(
        self, interaction: discord.Interaction, verification_type: VerificationType
    ) -> None:
        """Manejar inicio de verificacion cuando el usuario hace clic en un boton.

        Args:
            interaction (discord.Interaction): Interaccion del usuario
            verification_type (VerificationType): Tipo de verificacion
        """
        if not interaction.guild or not interaction.user:
            return

        guild = interaction.guild
        user = interaction.user

        # Verificar si el cog esta habilitado
        if not await self._is_cog_enabled(guild.id):
            return

        await interaction.response.defer(ephemeral=True)

        # Obtener toda la configuracion de una vez
        config = await self._get_all_config(guild.id)

        # Verificar si la verificacion esta habilitada
        if config.get(ConfigKey.VERIFICATION_ENABLED) is False:
            await interaction.followup.send(
                config.get(ConfigKey.VERIFICATION_DISABLED_MESSAGE) or "", ephemeral=True
            )
            return

        # Verificar que el canal de moderacion esta configurado y accesible
        mod_channel = self._get_mod_channel(guild=guild, config=config)
        if not mod_channel:
            await interaction.followup.send(
                config.get(ConfigKey.VERIFICATION_DISABLED_MESSAGE) or "", ephemeral=True
            )
            return

        # Obtener nombre del tipo de verificacion para mensajes
        type_display = (
            config.get(ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY) or "Normal"
            if verification_type == VerificationType.REGULAR
            else config.get(ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY) or "Aliado"
        )

        # Verificar si el usuario ya tiene los roles de verificacion
        if config.get(ConfigKey.BLOCK_ALREADY_VERIFIED) and isinstance(user, discord.Member):
            roles_to_add = (
                config.get(ConfigKey.REGULAR_ROLES_ADD)
                if verification_type == VerificationType.REGULAR
                else config.get(ConfigKey.ALLY_ROLES_ADD)
            )

            if roles_to_add:
                user_role_ids = {role.id for role in user.roles}
                has_all_roles = all(role_id in user_role_ids for role_id in roles_to_add)
                if has_all_roles:
                    await interaction.followup.send(
                        config.get(ConfigKey.ALREADY_VERIFIED_MESSAGE) or "", ephemeral=True
                    )
                    return

        async with self.bot.database.session() as session:
            verification_service = VerificationService(session=session)

            pending = await verification_service.get_pending_by_user(
                guild_id=guild.id, user_id=user.id
            )
            if pending:
                await interaction.followup.send(
                    config.get(ConfigKey.ALREADY_PENDING_MESSAGE) or "", ephemeral=True
                )
                return

            request = await verification_service.create_request(
                guild_id=guild.id,
                user_id=user.id,
                username=user.name,
                verification_type=verification_type,
            )

            dm_template = (
                config.get(ConfigKey.DM_INSTRUCTIONS_MESSAGE)
                if verification_type == VerificationType.REGULAR
                else config.get(ConfigKey.DM_INSTRUCTIONS_ALLY_MESSAGE)
            )
            formatted_dm = self._format_message(
                template=dm_template,
                username=user.name,
                user_mention=user.mention,
                server_name=guild.name,
                verification_type=type_display,
            )

            try:
                await user.send(content=formatted_dm)
            except discord.Forbidden:
                await verification_service.cancel(request.id)
                await session.commit()
                await interaction.followup.send(
                    config.get(ConfigKey.DM_DISABLED_MESSAGE) or "", ephemeral=True
                )
                return

            self._pending_dm_verifications[user.id] = (guild.id, request.id)

            # Enviar notificacion al canal de moderacion
            status_text = config.get(ConfigKey.STATUS_AWAITING_SCREENSHOTS) or ""
            formatted_mod = self._format_message(
                template=config.get(ConfigKey.MOD_MESSAGE_TEMPLATE),
                username=user.name,
                user_mention=user.mention,
                verification_type=type_display,
                status=status_text,
            )

            mod_message = await mod_channel.send(content=formatted_mod)
            await verification_service.set_mod_message_id(
                request_id=request.id, message_id=mod_message.id
            )

            await session.commit()

        started_message = config.get(ConfigKey.VERIFICATION_STARTED_MESSAGE) or ""
        await interaction.followup.send(started_message, ephemeral=True)

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
        if message.author.id not in self._pending_dm_verifications:
            return

        guild_id, request_id = self._pending_dm_verifications[message.author.id]

        # Verificar si el cog esta habilitado
        if not await self._is_cog_enabled(guild_id):
            return

        image_attachments = [
            a for a in message.attachments if a.content_type and a.content_type.startswith("image/")
        ]

        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            config = await self._get_all_config(guild_id=guild_id, config_service=config_service)

            if len(image_attachments) != 2:
                formatted = self._format_message(
                    template=config.get(ConfigKey.WRONG_IMAGES_MESSAGE),
                    username=message.author.name,
                )
                await message.channel.send(content=formatted)
                return

            del self._pending_dm_verifications[message.author.id]

            verification_service = VerificationService(session=session)

            request = await verification_service.update_screenshots(
                request_id=request_id,
                url1=image_attachments[0].url,
                url2=image_attachments[1].url,
            )

            if not request:
                await message.channel.send(content=config.get(ConfigKey.REQUEST_NOT_FOUND_MESSAGE))
                return

            guild = self.bot.get_guild(guild_id)
            server_name = guild.name if guild else "el servidor"
            formatted_received = self._format_message(
                template=config.get(ConfigKey.SCREENSHOTS_RECEIVED_MESSAGE),
                username=message.author.name,
                server_name=server_name,
            )
            await message.channel.send(content=formatted_received)

            if guild and request.mod_message_id:
                mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
                if mod_channel_id:
                    mod_channel = guild.get_channel(mod_channel_id)
                    if mod_channel and isinstance(mod_channel, discord.TextChannel):
                        await self._update_mod_message_for_review(
                            channel=mod_channel,
                            request=request,
                            verification_service=verification_service,
                            config=config,
                        )

            await session.commit()

    async def _update_mod_message_for_review(
        self,
        channel: discord.TextChannel,
        request: VerificationRequest,
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
        if not request.mod_message_id:
            return

        try:
            mod_message = await channel.fetch_message(request.mod_message_id)
        except discord.NotFound:
            logger.warning(f"Mensaje de mod no encontrado: {request.mod_message_id}")
            return

        type_display = (
            config.get(ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY) or "Normal"
            if request.verification_type == VerificationType.REGULAR
            else config.get(ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY) or "Aliado"
        )
        status_text = config.get(ConfigKey.STATUS_PENDING_REVIEW) or ""
        formatted = self._format_message(
            template=config.get(ConfigKey.MOD_MESSAGE_TEMPLATE),
            username=request.username,
            user_mention=f"<@{request.user_id}>",
            verification_type=type_display,
            status=status_text,
        )

        # Agregar capturas
        formatted += f"\n{request.screenshot_1_url} {request.screenshot_2_url}"

        # Agregar historial
        history = await verification_service.get_user_history(
            guild_id=request.guild_id, user_id=request.user_id
        )
        past_requests = [r for r in history if r.id != request.id]

        if past_requests:
            history_label = config.get(ConfigKey.HISTORY_LABEL) or "Historial"
            formatted += f"\n**{history_label}:**"
            for past in past_requests[:5]:
                status_emoji = {
                    VerificationStatus.APPROVED: "✅",
                    VerificationStatus.REJECTED: "❌",
                    VerificationStatus.CANCELLED: "🚫",
                }.get(VerificationStatus(past.status), "❓")
                timestamp = past.reviewed_at or past.created_at
                date_str = timestamp.strftime("%Y-%m-%d %H:%M")
                moderator = past.reviewed_by_username or ""
                past_type_display = (
                    config.get(ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY) or "Normal"
                    if past.verification_type == VerificationType.REGULAR
                    else config.get(ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY) or "Aliado"
                )
                formatted += f"\n{status_emoji} {past_type_display} - {moderator} ({date_str})"
                if past.rejection_reason:
                    formatted += f" - {past.rejection_reason}"

        accept_label = config.get(ConfigKey.ACCEPT_BUTTON_TEXT) or "Aceptar"
        reject_label = config.get(ConfigKey.REJECT_BUTTON_TEXT) or "Rechazar"
        view = ModReviewView(
            request_id=request.id, accept_label=accept_label, reject_label=reject_label
        )

        await mod_message.edit(content=formatted, view=view)

    async def handle_accept(self, interaction: discord.Interaction, request_id: int) -> None:
        """Manejar aprobacion de verificacion.

        Args:
            interaction (discord.Interaction): Interaccion del moderador
            request_id (int): ID de la solicitud
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if not await self._is_cog_enabled(interaction.guild.id):
            return

        async with self.bot.database.session() as session:
            ctx = await self._validate_mod_action(
                interaction=interaction,
                request_id=request_id,
                session=session,
                permission_error_key=ConfigKey.NO_PERMISSION_APPROVE_MESSAGE,
                permission_error_default="No tienes permisos para aprobar verificaciones.",
            )
            if not ctx:
                return

            config, request, verification_service = ctx

            await verification_service.approve(
                request_id=request_id,
                reviewer_id=interaction.user.id,
                reviewer_username=interaction.user.name,
            )

            failed_roles: list[str] = []
            member = interaction.guild.get_member(request.user_id)
            if member:
                if request.verification_type == VerificationType.REGULAR:
                    roles_add = config.get(ConfigKey.REGULAR_ROLES_ADD)
                    roles_remove = config.get(ConfigKey.REGULAR_ROLES_REMOVE)
                    approval_msg_key = ConfigKey.APPROVAL_MESSAGE_REGULAR
                else:
                    roles_add = config.get(ConfigKey.ALLY_ROLES_ADD)
                    roles_remove = config.get(ConfigKey.ALLY_ROLES_REMOVE)
                    approval_msg_key = ConfigKey.APPROVAL_MESSAGE_ALLY

                for role_id in roles_add or []:
                    role = interaction.guild.get_role(role_id)
                    if not role:
                        logger.warning(f"Rol no encontrado: {role_id}")
                        continue
                    try:
                        await member.add_roles(role)
                    except discord.Forbidden as e:
                        failed_roles.append(f"@{role.name} (agregar)")
                        logger.warning(
                            f"No se pudo agregar rol {role.name} ({role_id}): {e}. "
                            f"Verifica que el bot tenga permiso 'Gestionar roles' y que "
                            f"su rol este por encima de @{role.name} en la jerarquia."
                        )

                for role_id in roles_remove or []:
                    role = interaction.guild.get_role(role_id)
                    if not role:
                        logger.warning(f"Rol no encontrado: {role_id}")
                        continue
                    try:
                        await member.remove_roles(role)
                    except discord.Forbidden as e:
                        failed_roles.append(f"@{role.name} (quitar)")
                        logger.warning(
                            f"No se pudo quitar rol {role.name} ({role_id}): {e}. "
                            f"Verifica que el bot tenga permiso 'Gestionar roles' y que "
                            f"su rol este por encima de @{role.name} en la jerarquia."
                        )

                formatted = self._format_message(
                    template=config.get(approval_msg_key),
                    username=request.username,
                    server_name=interaction.guild.name,
                )
                try:
                    await member.send(content=formatted)
                except discord.Forbidden:
                    pass

            # Actualizar o eliminar mensaje de moderacion
            if request.mod_message_id:
                mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
                delete_messages = config.get(ConfigKey.DELETE_PROCESSED_MESSAGES)
                if mod_channel_id:
                    mod_channel = interaction.guild.get_channel(mod_channel_id)
                    if mod_channel and isinstance(mod_channel, discord.TextChannel):
                        try:
                            mod_message = await mod_channel.fetch_message(request.mod_message_id)
                            if delete_messages:
                                await mod_message.delete()
                            else:
                                current_content = mod_message.content
                                pending_status = config.get(ConfigKey.STATUS_PENDING_REVIEW) or ""
                                approved_status = self._format_message(
                                    template=config.get(ConfigKey.STATUS_APPROVED),
                                    moderator=interaction.user.name,
                                )
                                if pending_status and pending_status in current_content:
                                    new_content = current_content.replace(
                                        pending_status, approved_status
                                    )
                                else:
                                    new_content = current_content + f"\n\n{approved_status}"
                                await mod_message.edit(content=new_content, view=None)
                        except discord.NotFound:
                            logger.warning(
                                f"Mensaje de mod no encontrado: {request.mod_message_id}"
                            )

            await session.commit()

            confirmation = self._format_message(
                template=config.get(ConfigKey.MOD_APPROVED_CONFIRMATION)
                or "Verificacion aprobada para {username}.",
                username=request.username,
            )
            if failed_roles:
                roles_warning = ", ".join(failed_roles)
                await interaction.followup.send(
                    f"{confirmation}\n\n"
                    f"⚠️ **Advertencia:** No se pudieron modificar algunos roles: {roles_warning}\n"
                    f"Verifica que:\n"
                    f"• El bot tenga el permiso **Gestionar roles**\n"
                    f"• El rol del bot este **por encima** de estos roles en la jerarquia",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(confirmation, ephemeral=True)

    async def show_rejection_select(
        self, interaction: discord.Interaction, request_id: int
    ) -> None:
        """Mostrar selector de motivos de rechazo.

        Args:
            interaction (discord.Interaction): Interaccion del moderador
            request_id (int): ID de la solicitud
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild_id = interaction.guild.id

        # Verificar si el cog esta habilitado
        if not await self._is_cog_enabled(guild_id):
            return

        # Obtener toda la configuracion de una vez
        config = await self._get_all_config(guild_id)

        # Verificar permisos antes de mostrar el selector
        if not has_any_role(
            member=interaction.user, role_ids=config.get(ConfigKey.MOD_ROLES) or []
        ):
            await interaction.response.send_message(
                content="No tienes permisos para rechazar verificaciones.",
                ephemeral=True,
            )
            return

        # Obtener motivos predefinidos configurados
        reasons: list[str] = []
        rejection_reason_keys = [
            ConfigKey.REJECTION_REASON_1,
            ConfigKey.REJECTION_REASON_2,
            ConfigKey.REJECTION_REASON_3,
            ConfigKey.REJECTION_REASON_4,
        ]
        for key in rejection_reason_keys:
            reason = config.get(key) or ""
            if reason and reason.strip():
                reasons.append(reason)

        # Si no hay motivos configurados, usar por defecto
        if not reasons:
            reasons = [
                "Capturas incorrectas o ilegibles",
                "Nombre de usuario no coincide",
                "Informacion insuficiente",
            ]

        # Obtener textos configurables
        select_message = (
            config.get(ConfigKey.REJECTION_SELECT_MESSAGE) or "Selecciona el motivo de rechazo:"
        )
        placeholder = (
            config.get(ConfigKey.REJECTION_SELECT_PLACEHOLDER)
            or "Selecciona el motivo de rechazo..."
        )
        other_label = config.get(ConfigKey.REJECTION_OTHER_LABEL) or "Otro motivo..."
        other_description = (
            config.get(ConfigKey.REJECTION_OTHER_DESCRIPTION) or "Escribir un motivo personalizado"
        )
        modal_title = config.get(ConfigKey.REJECTION_MODAL_TITLE) or "Motivo de Rechazo"
        modal_label = config.get(ConfigKey.REJECTION_MODAL_LABEL) or "Motivo"
        modal_placeholder = (
            config.get(ConfigKey.REJECTION_MODAL_PLACEHOLDER)
            or "Explica por que se rechaza la verificacion..."
        )

        view = RejectionReasonView(
            request_id=request_id,
            reasons=reasons,
            other_label=other_label,
            other_description=other_description,
            placeholder=placeholder,
            modal_title=modal_title,
            modal_label=modal_label,
            modal_placeholder=modal_placeholder,
        )
        await interaction.response.send_message(
            content=select_message,
            view=view,
            ephemeral=True,
        )

    async def handle_reject(
        self, interaction: discord.Interaction, request_id: int, reason: str
    ) -> None:
        """Manejar rechazo de verificacion.

        Args:
            interaction (discord.Interaction): Interaccion del moderador
            request_id (int): ID de la solicitud
            reason (str): Motivo del rechazo
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if not await self._is_cog_enabled(interaction.guild.id):
            return

        async with self.bot.database.session() as session:
            ctx = await self._validate_mod_action(
                interaction=interaction,
                request_id=request_id,
                session=session,
                permission_error_key=ConfigKey.NO_PERMISSION_REJECT_MESSAGE,
                permission_error_default="No tienes permisos para rechazar verificaciones.",
            )
            if not ctx:
                return

            config, request, verification_service = ctx

            await verification_service.reject(
                request_id=request_id,
                reviewer_id=interaction.user.id,
                reviewer_username=interaction.user.name,
                reason=reason,
            )

            member = interaction.guild.get_member(request.user_id)
            if member:
                type_display = (
                    config.get(ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY) or "Normal"
                    if request.verification_type == VerificationType.REGULAR
                    else config.get(ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY) or "Aliado"
                )
                formatted = self._format_message(
                    template=config.get(ConfigKey.REJECTION_MESSAGE),
                    username=request.username,
                    server_name=interaction.guild.name,
                    verification_type=type_display,
                    reason=reason,
                )
                try:
                    await member.send(content=formatted)
                except discord.Forbidden:
                    pass

            # Actualizar o eliminar mensaje de moderacion
            if request.mod_message_id:
                mod_channel_id = config.get(ConfigKey.MOD_NOTIFICATION_CHANNEL)
                delete_messages = config.get(ConfigKey.DELETE_PROCESSED_MESSAGES)
                if mod_channel_id:
                    mod_channel = interaction.guild.get_channel(mod_channel_id)
                    if mod_channel and isinstance(mod_channel, discord.TextChannel):
                        try:
                            mod_message = await mod_channel.fetch_message(request.mod_message_id)
                            if delete_messages:
                                await mod_message.delete()
                            else:
                                current_content = mod_message.content
                                pending_status = config.get(ConfigKey.STATUS_PENDING_REVIEW) or ""
                                rejected_status = self._format_message(
                                    template=config.get(ConfigKey.STATUS_REJECTED),
                                    moderator=interaction.user.name,
                                    reason=reason,
                                )
                                if pending_status and pending_status in current_content:
                                    new_content = current_content.replace(
                                        pending_status, rejected_status
                                    )
                                else:
                                    new_content = current_content + f"\n\n{rejected_status}"
                                await mod_message.edit(content=new_content, view=None)
                        except discord.NotFound:
                            logger.warning(
                                f"Mensaje de mod no encontrado: {request.mod_message_id}"
                            )

            await session.commit()

            confirmation = self._format_message(
                template=config.get(ConfigKey.MOD_REJECTED_CONFIRMATION)
                or "Verificacion rechazada para {username}.",
                username=request.username,
            )
            await interaction.followup.send(content=confirmation, ephemeral=True)

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
