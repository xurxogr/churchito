"""Cog de purga para gestión de actividad de miembros."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from discord_bot.bot import DiscordBot
from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import delete_message, has_any_role
from discord_bot.purga.enums import ConfigKey, PurgaStatus, PurgaType
from discord_bot.purga.models import PurgaRecord
from discord_bot.purga.service import PurgaService
from discord_bot.purga.views import ModAuthorizationView, UserConfirmationView

logger = logging.getLogger(__name__)

COG_NAME = "purga"

# Mapeo de nombres de color a estilos de botón
BUTTON_STYLES = {
    "blurple": discord.ButtonStyle.primary,
    "grey": discord.ButtonStyle.secondary,
    "green": discord.ButtonStyle.success,
    "red": discord.ButtonStyle.danger,
}

# Plantilla por defecto para el mensaje de moderación
DEFAULT_MOD_MESSAGE = """**{purge_type}**

Estado: {status}
Autorizaciones necesarias: {required_reactions}
Fecha de ejecución: {dia}

Autorizado por: {authorized_by}
Cancelaciones: {cancellations}

Reacciona al botón para autorizar la purga."""

# Plantilla por defecto para el mensaje de usuarios
DEFAULT_USER_MESSAGE = """**PURGA ACTIVA**

Se ha iniciado una purga. Los siguientes roles están afectados:
{roles}

Fecha de ejecución: {dia}

Reacciona al botón para confirmar tu permanencia y obtener el rol {reaction_rol}."""


PURGA_CONFIG_SCHEMA = CogConfigSchema(
    cog_name="purga",
    display_name="Purga",
    description="Sistema de purga para gestión de actividad de miembros",
    icon="🗡️",
    toggleable=True,
    options=[
        # ====================================================================
        # COMMON - Moderación
        # ====================================================================
        ConfigOption(
            key=ConfigKey.MOD_CHANNEL,
            name="Canal de moderación",
            description="Canal donde los moderadores activan y gestionan las purgas",
            option_type=ConfigOptionType.CHANNEL,
            section="Común",
            group="Moderación",
        ),
        ConfigOption(
            key=ConfigKey.MOD_MESSAGE_TEMPLATE,
            name="Plantilla del mensaje de autorización",
            description="Mensaje que se muestra cuando se inicia una purga. "
            "Se actualiza dinámicamente con el estado y la lista de autorizadores.",
            option_type=ConfigOptionType.TEXTAREA,
            section="Común",
            group="Moderación",
            default=DEFAULT_MOD_MESSAGE,
            max_length=2000,
            placeholders=[
                "purge_type",
                "status",
                "authorized_by",
                "cancellations",
                "required_reactions",
                "dia",
            ],
        ),
        ConfigOption(
            key=ConfigKey.MOD_BUTTON_COLOR,
            name="Color del botón de autorización",
            description="Color del botón que los moderadores usan para autorizar",
            option_type=ConfigOptionType.TEXT_CHOICE,
            section="Común",
            group="Moderación",
            default="green",
            choices=[
                ("Azul", "blurple"),
                ("Gris", "grey"),
                ("Verde", "green"),
                ("Rojo", "red"),
            ],
        ),
        ConfigOption(
            key=ConfigKey.MOD_BUTTON_TEXT,
            name="Texto del botón de autorización",
            description="Texto que aparece en el botón (puede incluir emojis)",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Moderación",
            default="🔑 Autorizar purga",
            max_length=80,
        ),
        ConfigOption(
            key=ConfigKey.MOD_REQUIRED_REACTIONS,
            name="Reacciones necesarias",
            description="Número de moderadores que deben autorizar para activar la purga",
            option_type=ConfigOptionType.INTEGER,
            section="Común",
            group="Moderación",
            default=2,
            min_value=1,
            max_value=10,
        ),
        ConfigOption(
            key=ConfigKey.MOD_REACTION_TIMEOUT,
            name="Tiempo límite (minutos)",
            description="Minutos para conseguir las autorizaciones necesarias. 0 = sin límite.",
            option_type=ConfigOptionType.INTEGER,
            section="Común",
            group="Moderación",
            default=1,
            min_value=0,
            max_value=1440,
        ),
        ConfigOption(
            key=ConfigKey.MOD_MESSAGE_RETENTION,
            name="Retención del mensaje (minutos)",
            description="Minutos que el mensaje permanece tras finalizar. 0 = permanente.",
            option_type=ConfigOptionType.INTEGER,
            section="Común",
            group="Moderación",
            default=0,
            min_value=0,
            max_value=1440,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STATUS_PENDING,
            name="Estado: Pendiente",
            description="Texto cuando se esperan más autorizaciones",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Moderación",
            default="⏳ Pendiente de aprobación",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STATUS_AUTHORIZED,
            name="Estado: Autorizado",
            description="Texto cuando se consiguen las autorizaciones necesarias",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Moderación",
            default="✅ Autorizado",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STATUS_EXPIRED,
            name="Estado: Expirado",
            description="Texto cuando no se consiguen las autorizaciones a tiempo",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Moderación",
            default="⌛ Expirado",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STATUS_CANCEL_PENDING,
            name="Estado: Cancelación pendiente",
            description="Texto cuando se inicia la cancelación pero faltan votos",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Moderación",
            default="🟡 Cancelación pendiente",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STATUS_CANCELLED,
            name="Estado: Cancelado",
            description="Texto cuando la purga es cancelada",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Moderación",
            default="❌ Cancelado",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STATUS_EXECUTED,
            name="Estado: Ejecutado",
            description="Texto cuando la purga se ejecuta correctamente",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Moderación",
            default="✅ Ejecutado",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STOP_BUTTON_TEXT,
            name="Texto del botón de detener",
            description="Texto del botón para detener una purga activa",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Moderación",
            default="🛑 Detener purga",
            max_length=80,
        ),
        ConfigOption(
            key=ConfigKey.MOD_ACTIVE_PURGE_TEXT,
            name="Mensaje: Purga activa",
            description="Mensaje cuando se intenta iniciar otra purga habiendo una activa",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Moderación",
            default="Ya hay una purga activa. Espera a que termine o cancélala.",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.MOD_NO_PERMISSION_TEXT,
            name="Mensaje: Sin permisos",
            description="Mensaje cuando el usuario no tiene rol para usar el comando",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Moderación",
            default="No tienes permisos para ejecutar este comando.",
            max_length=200,
        ),
        # ====================================================================
        # COMMON - Usuarios
        # ====================================================================
        ConfigOption(
            key=ConfigKey.USER_CHANNEL,
            name="Canal de usuarios",
            description="Canal donde los usuarios ven el mensaje de purga y reaccionan",
            option_type=ConfigOptionType.CHANNEL,
            section="Común",
            group="Usuarios",
        ),
        ConfigOption(
            key=ConfigKey.USER_BUTTON_COLOR,
            name="Color del botón de confirmación",
            description="Color del botón que los usuarios usan para confirmar",
            option_type=ConfigOptionType.TEXT_CHOICE,
            section="Común",
            group="Usuarios",
            default="green",
            choices=[
                ("Azul", "blurple"),
                ("Gris", "grey"),
                ("Verde", "green"),
                ("Rojo", "red"),
            ],
        ),
        ConfigOption(
            key=ConfigKey.USER_BUTTON_TEXT,
            name="Texto del botón de confirmación",
            description="Texto del botón que los usuarios presionan (puede incluir emojis)",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Usuarios",
            default="🛡️ Confirmar permanencia",
            max_length=80,
        ),
        ConfigOption(
            key=ConfigKey.USER_REACTION_ROLE,
            name="Rol al reaccionar",
            description="Rol que se asigna a los usuarios cuando reaccionan al botón",
            option_type=ConfigOptionType.ROLE,
            section="Común",
            group="Usuarios",
        ),
        ConfigOption(
            key=ConfigKey.USER_FIRST_REACTION_TEXT,
            name="Mensaje: Primera reacción",
            description="Mensaje (efímero) cuando el usuario confirma por primera vez",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Usuarios",
            default="Has confirmado tu permanencia. ¡Gracias!",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.USER_ALREADY_REACTED_TEXT,
            name="Mensaje: Ya confirmado",
            description="Mensaje (efímero) cuando el usuario ya había confirmado",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Usuarios",
            default="Ya habías confirmado tu permanencia anteriormente.",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.USER_REMOVED_REACTION_TEXT,
            name="Mensaje: Confirmación retirada",
            description="Mensaje (efímero) cuando el usuario retira su confirmación",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Usuarios",
            default="Has retirado tu confirmación.",
            max_length=200,
        ),
        # ====================================================================
        # COMMON - General
        # ====================================================================
        ConfigOption(
            key=ConfigKey.PURGE_HOUR,
            name="Hora de ejecución",
            description="Hora del día (UTC) a la que se ejecutará la purga. "
            "El comando añade días, pero la hora será esta.",
            option_type=ConfigOptionType.INTEGER,
            section="Común",
            group="General",
            default=18,
            min_value=0,
            max_value=23,
        ),
        ConfigOption(
            key=ConfigKey.TEST_MODE,
            name="Modo prueba",
            description="Permite saltarse las restricciones mínimas: "
            "solo requiere 1 autorización y ejecuta en 2 minutos.",
            option_type=ConfigOptionType.BOOLEAN,
            section="Común",
            group="General",
            default=False,
        ),
        ConfigOption(
            key=ConfigKey.AUDIT_LEVEL,
            name="Nivel de auditoría",
            description="0 = Sin mensajes, 1 = Solo títulos, 2 = Todas las acciones",
            option_type=ConfigOptionType.INTEGER,
            section="Común",
            group="General",
            default=1,
            min_value=0,
            max_value=2,
        ),
        # ====================================================================
        # COMMON - Mensajes de ejecución
        # ====================================================================
        ConfigOption(
            key=ConfigKey.EXEC_MSG_SIMULATION,
            name="Mensaje: Modo prueba",
            description="Indicador al inicio de logs cuando se ejecuta en modo prueba",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="🧪 **[MODO PRUEBA]**",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_INIT,
            name="Mensaje: Inicio de purga",
            description="Mensaje al iniciar la ejecución (nivel 1+)",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="🔥 **Iniciando purga...**",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_CLEANING_ROLE,
            name="Mensaje: Limpiando rol",
            description="Mensaje por cada rol afectado (nivel 2). Placeholder: {role}",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="🧹 Aplicando purga al rol {role}...",
            max_length=200,
            placeholders=["role"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_USER_CLEANED,
            name="Mensaje: Usuario purgado",
            description="Mensaje por cada usuario purgado (nivel 2). Placeholder: {user}",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="  ↳ 🧹 Purgado: {user}",
            max_length=200,
            placeholders=["user"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_PROMOTIONS_START,
            name="Mensaje: Inicio promociones",
            description="Mensaje al iniciar promociones (nivel 1+)",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="⬆️ **Aplicando promociones...**",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_PROMOTION_ROLE,
            name="Mensaje: Promoción por rol",
            description="Mensaje por cada promoción de rol (nivel 2). "
            "Placeholders: {from_role}, {to_role}",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="📈 Promocionando {from_role} → {to_role}...",
            max_length=200,
            placeholders=["from_role", "to_role"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_USER_PROMOTED,
            name="Mensaje: Usuario promocionado",
            description="Mensaje por cada usuario promocionado (nivel 2). "
            "Placeholders: {user}, {from_role}, {to_role}",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="  ↳ ⬆️ Promocionado: {user} ({from_role} → {to_role})",
            max_length=200,
            placeholders=["user", "from_role", "to_role"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_PROMOTION_DEFAULT,
            name="Mensaje: Rol para no afectados",
            description="Mensaje al aplicar rol a usuarios que confirmaron sin estar "
            "en roles afectados (nivel 2). Placeholder: {role}",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="🏷️ Marcando usuarios no afectados ({role})...",
            max_length=200,
            placeholders=["role"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_USER_PROMOTED_DEFAULT,
            name="Mensaje: Usuario no afectado",
            description="Mensaje por cada usuario no afectado que recibe el rol (nivel 2). "
            "Placeholders: {user}, {role}",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="  ↳ 🏷️ Marcado: {user} (→ {role})",
            max_length=200,
            placeholders=["user", "role"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_FINISH,
            name="Mensaje: Fin de purga",
            description="Mensaje al finalizar (nivel 1+). "
            "Placeholders: {cleaned}, {promoted_in_group}, {promoted_not_in_group}",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="✅ **Purga finalizada.** "
            "Purgados: {cleaned} | Promocionados (grupo): {promoted_in_group} | "
            "Promocionados (otros): {promoted_not_in_group}",
            max_length=500,
            placeholders=["cleaned", "promoted_in_group", "promoted_not_in_group"],
        ),
        # ====================================================================
        # PURGA FIN DE GUERRA
        # ====================================================================
        ConfigOption(
            key=ConfigKey.WAR_COMMAND_NAME,
            name="Nombre del comando",
            description="Nombre del comando slash para iniciar la purga de fin de guerra",
            option_type=ConfigOptionType.STRING,
            section="Purga: Final de guerra",
            default="purga_guerra",
            max_length=32,
        ),
        ConfigOption(
            key=ConfigKey.WAR_MESSAGE_TEMPLATE,
            name="Plantilla del mensaje de usuarios",
            description="Mensaje que ven los usuarios cuando la purga está activa",
            option_type=ConfigOptionType.TEXTAREA,
            section="Purga: Final de guerra",
            default=DEFAULT_USER_MESSAGE,
            max_length=2000,
            placeholders=["roles", "dia", "reaction_rol"],
        ),
        ConfigOption(
            key=ConfigKey.WAR_ADMIN_ROLES,
            name="Roles administradores",
            description="Roles que pueden iniciar y autorizar la purga",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purga: Final de guerra",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.WAR_AFFECTED_ROLES,
            name="Roles afectados",
            description="Roles cuyos miembros deben confirmar permanencia o serán purgados",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purga: Final de guerra",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.WAR_ROLES_TO_REMOVE,
            name="Roles a eliminar (purgados)",
            description="Roles que se eliminan a los miembros purgados. "
            "Dejar vacío para eliminar todos los roles.",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purga: Final de guerra",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.WAR_ROLES_TO_ADD,
            name="Roles a asignar (purgados)",
            description="Roles que se asignan a los miembros purgados después de eliminar roles",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purga: Final de guerra",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.WAR_PROMOTIONS,
            name="Promociones",
            description="Sustitución de roles para miembros que confirman. "
            "Si el rol origen está en 'Roles afectados', se sustituye. "
            "Si no está, se añade el rol destino sin quitar el origen.",
            option_type=ConfigOptionType.TABLE,
            section="Purga: Final de guerra",
            default=[],
            columns=[
                {
                    "key": "from_role",
                    "name": "Rol origen",
                    "type": "role",
                    "required": True,
                },
                {
                    "key": "to_role",
                    "name": "Rol destino",
                    "type": "role",
                    "required": True,
                },
            ],
        ),
        ConfigOption(
            key=ConfigKey.WAR_DEFAULT_PROMOTION,
            name="Rol para no afectados",
            description="Rol a asignar a usuarios que confirmaron pero NO tenían "
            "ningún rol afectado. Útil para identificar quién reaccionó sin estar "
            "en el grupo objetivo. Dejar vacío para ignorarlos.",
            option_type=ConfigOptionType.ROLE,
            section="Purga: Final de guerra",
            default=None,
        ),
    ],
)


class PurgaCog(commands.Cog):
    """Cog para gestión de purgas de miembros."""

    def __init__(self, bot: DiscordBot) -> None:
        """Inicializar el cog.

        Args:
            bot (DiscordBot): Instancia del bot de Discord.
        """
        self.bot = bot
        # Track registered commands per guild: {guild_id: command_name}
        self._registered_commands: dict[int, str] = {}
        # Debounce pending syncs: {guild_id: asyncio.Task}
        self._pending_syncs: dict[int, asyncio.Task[None]] = {}
        # Debounce delay in seconds
        self._sync_debounce_delay = 2.0
        # Track active purgas in memory: {guild_id: (purga_id, expires_at)}
        self._active_purgas: dict[int, tuple[int, datetime | None]] = {}
        # Track authorized purgas for execution: {guild_id: (purga_id, scheduled_for)}
        self._authorized_purgas: dict[int, tuple[int, datetime]] = {}
        # Track messages scheduled for deletion: {(channel_id, message_id): delete_at}
        self._pending_deletions: dict[tuple[int, int], datetime] = {}
        logger.info("PurgaCog inicializado")

    @staticmethod
    def get_config_schema() -> CogConfigSchema:
        """Obtener el esquema de configuración del cog.

        Returns:
            CogConfigSchema: Esquema de configuración.
        """
        return PURGA_CONFIG_SCHEMA

    # =========================================================================
    # Config helpers
    # =========================================================================

    async def _is_cog_enabled(self, guild_id: int) -> bool:
        """Verificar si el cog está habilitado en un guild.

        Args:
            guild_id (int): ID del guild.

        Returns:
            bool: True si está habilitado.
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.is_cog_enabled(guild_id=guild_id, cog_name=COG_NAME)

    async def _get_config(self, guild_id: int) -> dict[str, Any]:
        """Obtener toda la configuración del cog para un guild.

        Args:
            guild_id (int): ID del guild.

        Returns:
            dict[str, Any]: Configuración del cog.
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.get_all_config(guild_id=guild_id, cog_name=COG_NAME)

    async def _get_config_value(self, guild_id: int, key: str) -> Any:
        """Obtener un valor de configuración específico.

        Args:
            guild_id (int): ID del guild.
            key (str): Clave de configuración.

        Returns:
            Any: Valor de configuración.
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.get_value(guild_id=guild_id, cog_name=COG_NAME, key=key)

    def _is_config_complete(self, config: dict[str, Any]) -> tuple[bool, list[str]]:
        """Verificar si la configuración esencial está completa.

        Args:
            config (dict[str, Any]): Diccionario de configuración.

        Returns:
            tuple[bool, list[str]]: (está_completa, lista_de_opciones_faltantes)
        """
        missing: list[str] = []

        # Canales requeridos
        if not config.get(ConfigKey.MOD_CHANNEL):
            missing.append("Canal de moderación")
        if not config.get(ConfigKey.USER_CHANNEL):
            missing.append("Canal de usuarios")

        # Roles requeridos para purga de guerra
        if not config.get(ConfigKey.WAR_ADMIN_ROLES):
            missing.append("Roles administradores")
        if not config.get(ConfigKey.WAR_AFFECTED_ROLES):
            missing.append("Roles afectados")

        return len(missing) == 0, missing

    # =========================================================================
    # Message formatting helpers
    # =========================================================================

    def _format_message(self, template: str | None = None, **kwargs: str | None) -> str:
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

    def _get_button_style(self, color: str) -> discord.ButtonStyle:
        """Obtener el estilo de botón a partir del nombre de color.

        Args:
            color (str): Nombre del color (blurple, grey, green, red).

        Returns:
            discord.ButtonStyle: Estilo de botón.
        """
        return BUTTON_STYLES.get(color, discord.ButtonStyle.success)

    def _format_authorized_by(self, guild: discord.Guild, user_ids: list[int]) -> str:
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

    def _format_roles(self, guild: discord.Guild, role_ids: list[int]) -> str:
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

    def _get_mod_message_content(
        self,
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
        authorized_by = self._format_authorized_by(guild=guild, user_ids=record.authorized_by)
        cancellations = self._format_authorized_by(guild=guild, user_ids=record.cancelled_by)

        purge_type = "Purga de fin de guerra"
        if record.purga_type == PurgaType.MAINTENANCE:
            purge_type = "Purga de mantenimiento"

        execution_date = "No programada"
        if record.scheduled_for:
            execution_date = record.scheduled_for.strftime("%Y-%m-%d %H:%M UTC")

        content = self._format_message(
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

    # =========================================================================
    # Dynamic command registration
    # =========================================================================

    async def _register_guild_commands(self, guild: discord.Guild) -> None:
        """Registrar comandos para un guild basándose en su configuración.

        Solo registra comandos si el cog está habilitado Y la configuración
        esencial está completa.

        Args:
            guild (discord.Guild): Guild de Discord.
        """
        # Check if cog is enabled
        if not await self._is_cog_enabled(guild.id):
            logger.debug(f"Purga cog deshabilitado en {guild.name}, no se registran comandos")
            # Unregister if there were commands registered
            if guild.id in self._registered_commands:
                await self._unregister_guild_commands(guild)
            return

        config = await self._get_config(guild.id)

        # Check if essential config is complete
        is_complete, missing = self._is_config_complete(config)
        if not is_complete:
            logger.debug(
                f"Configuración incompleta en {guild.name}, "
                f"faltan: {', '.join(missing)}. No se registran comandos."
            )
            # Unregister if there were commands registered
            if guild.id in self._registered_commands:
                await self._unregister_guild_commands(guild)
            return

        war_command_name = config.get(ConfigKey.WAR_COMMAND_NAME, "purga_guerra")

        # Remove old command if name changed
        old_command_name = self._registered_commands.get(guild.id)
        if old_command_name and old_command_name != war_command_name:
            self.bot.tree.remove_command(old_command_name, guild=guild)
            logger.info(f"Comando '{old_command_name}' eliminado de {guild.name}")

        # Check if command already registered with same name
        if old_command_name == war_command_name:
            logger.debug(f"Comando '{war_command_name}' ya registrado en {guild.name}")
            return

        # Create and register the war purge command
        @app_commands.command(
            name=war_command_name,
            description="Inicia una purga de fin de guerra",
        )
        @app_commands.describe(dias="Número de días hasta la ejecución de la purga")
        async def war_purge_command(
            interaction: discord.Interaction,
            dias: app_commands.Range[int, 1, 30],
        ) -> None:
            await self._handle_war_purge(interaction=interaction, dias=dias)

        # Add command to guild
        self.bot.tree.add_command(war_purge_command, guild=guild)
        self._registered_commands[guild.id] = war_command_name
        logger.info(f"Comando '{war_command_name}' registrado en {guild.name}")

    async def _unregister_guild_commands(self, guild: discord.Guild) -> None:
        """Eliminar comandos registrados de un guild.

        Args:
            guild (discord.Guild): Guild de Discord.
        """
        old_command_name = self._registered_commands.get(guild.id)
        if old_command_name:
            self.bot.tree.remove_command(old_command_name, guild=guild)
            del self._registered_commands[guild.id]
            logger.info(f"Comando '{old_command_name}' eliminado de {guild.name}")

    async def _sync_guild_commands(self, guild: discord.Guild) -> None:
        """Sincronizar comandos de un guild con Discord.

        Args:
            guild (discord.Guild): Guild de Discord.
        """
        try:
            await self.bot.tree.sync(guild=guild)
            logger.info(f"Comandos sincronizados en {guild.name}")
        except Exception as e:
            logger.error(f"Error sincronizando comandos en {guild.name}: {e}")

    async def _debounced_register_and_sync(self, guild: discord.Guild) -> None:
        """Registrar y sincronizar comandos con debounce.

        Espera un breve periodo antes de ejecutar para agrupar múltiples
        cambios de configuración en una sola sincronización.

        Args:
            guild (discord.Guild): Guild de Discord.
        """
        # Cancel any pending sync for this guild
        if guild.id in self._pending_syncs:
            self._pending_syncs[guild.id].cancel()

        async def _delayed_sync() -> None:
            try:
                await asyncio.sleep(self._sync_debounce_delay)
                await self._register_guild_commands(guild)
                await self._sync_guild_commands(guild)
            except asyncio.CancelledError:
                pass  # Task was cancelled, a new one will run
            finally:
                self._pending_syncs.pop(guild.id, None)

        self._pending_syncs[guild.id] = asyncio.create_task(_delayed_sync())

    # =========================================================================
    # Command handlers
    # =========================================================================

    async def _handle_war_purge(self, interaction: discord.Interaction, dias: int) -> None:
        """Manejar el comando de purga de fin de guerra.

        Args:
            interaction (discord.Interaction): Interacción de Discord.
            dias (int): Número de días hasta la ejecución.
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        await interaction.response.defer(ephemeral=True)

        config = await self._get_config(guild.id)

        # Verificar permisos
        admin_roles = config.get(ConfigKey.WAR_ADMIN_ROLES, [])
        if not has_any_role(member=user, role_ids=admin_roles):
            await interaction.followup.send(
                config.get(ConfigKey.MOD_NO_PERMISSION_TEXT, "Sin permisos."),
                ephemeral=True,
            )
            return

        async with self.bot.database.session() as session:
            purga_service = PurgaService(session)

            # Verificar si hay una purga activa
            active = await purga_service.get_active_purga(guild.id)
            if active:
                await interaction.followup.send(
                    config.get(
                        ConfigKey.MOD_ACTIVE_PURGE_TEXT,
                        "Ya hay una purga activa.",
                    ),
                    ephemeral=True,
                )
                return

            # Calcular fecha de ejecución
            purge_hour = config.get(ConfigKey.PURGE_HOUR, 18)
            now = datetime.now(UTC)
            scheduled_for = (now + timedelta(days=dias)).replace(
                hour=purge_hour, minute=0, second=0, microsecond=0
            )

            # Calcular fecha de expiración para autorizaciones
            timeout_minutes = config.get(ConfigKey.MOD_REACTION_TIMEOUT, 1)
            expires_at = None
            if timeout_minutes > 0:
                expires_at = now + timedelta(minutes=timeout_minutes)

            # Crear snapshot de config relevante
            config_snapshot = {
                "affected_roles": config.get(ConfigKey.WAR_AFFECTED_ROLES, []),
                "roles_to_remove": config.get(ConfigKey.WAR_ROLES_TO_REMOVE, []),
                "roles_to_add": config.get(ConfigKey.WAR_ROLES_TO_ADD, []),
                "promotions": config.get(ConfigKey.WAR_PROMOTIONS, []),
                "default_promotion": config.get(ConfigKey.WAR_DEFAULT_PROMOTION),
                "reaction_role": config.get(ConfigKey.USER_REACTION_ROLE),
                "required_reactions": config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2),
                "test_mode": config.get(ConfigKey.TEST_MODE, False),
            }

            # Crear registro de purga
            record = await purga_service.create_purga(
                guild_id=guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=user.id,
                config_snapshot=config_snapshot,
                scheduled_for=scheduled_for,
                expires_at=expires_at,
            )

            logger.info(f"[{guild.name}] Purga {record.id} creada por {user.display_name}")

            # Obtener canal de moderación
            mod_channel_id = config.get(ConfigKey.MOD_CHANNEL)
            if not mod_channel_id:
                await interaction.followup.send(
                    "Error: Canal de moderación no configurado.",
                    ephemeral=True,
                )
                return
            mod_channel = guild.get_channel(mod_channel_id)
            if not mod_channel or not isinstance(mod_channel, discord.TextChannel):
                await interaction.followup.send(
                    "Error: Canal de moderación no encontrado.",
                    ephemeral=True,
                )
                return

            # Calcular autorizaciones requeridas (mínimo 2 si no es modo prueba)
            test_mode = config.get(ConfigKey.TEST_MODE, False)
            required = config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2)
            if not test_mode and required < 2:
                required = 2

            # Verificar si ya tenemos suficientes autorizaciones (el iniciador cuenta)
            authorized_count = len(record.authorized_by)
            if authorized_count >= required:
                # Auto-autorizar
                if test_mode:
                    exec_scheduled_for = datetime.now(UTC) + timedelta(minutes=2)
                else:
                    exec_scheduled_for = scheduled_for

                updated_record = await purga_service.update_status(
                    purga_id=record.id,
                    status=PurgaStatus.AUTHORIZED,
                    scheduled_for=exec_scheduled_for,
                )
                if updated_record:
                    record = updated_record
                    if exec_scheduled_for:
                        self._authorized_purgas[guild.id] = (record.id, exec_scheduled_for)
                    logger.info(
                        f"[{guild.name}] Purga {record.id} auto-autorizada, "
                        f"ejecución programada para {exec_scheduled_for}"
                    )

            # Crear mensaje de moderación
            content = self._get_mod_message_content(guild=guild, record=record, config=config)

            # Crear vista con botones según estado
            button_color = config.get(ConfigKey.MOD_BUTTON_COLOR, "green")
            authorize_label = config.get(ConfigKey.MOD_BUTTON_TEXT, "🔑 Autorizar purga")
            cancel_label = config.get(ConfigKey.MOD_STOP_BUTTON_TEXT, "🛑 Detener purga")

            view = ModAuthorizationView(
                purga_id=record.id,
                status=PurgaStatus(record.status),
                authorize_label=authorize_label,
                cancel_label=cancel_label,
                button_style=self._get_button_style(button_color),
            )

            mod_message = await mod_channel.send(content=content, view=view)

            # Actualizar registro con ID del mensaje
            await purga_service.update_mod_message(
                purga_id=record.id,
                channel_id=mod_channel.id,
                message_id=mod_message.id,
            )

            # Enviar mensaje a usuarios si ya está autorizada
            if record.status == PurgaStatus.AUTHORIZED:
                await self._send_user_message(
                    guild=guild, record=record, config=config, session=session
                )
            else:
                # Registrar en memoria para control de expiración
                self._active_purgas[guild.id] = (record.id, expires_at)

            await session.commit()

            await interaction.followup.send(
                f"Purga iniciada. Mensaje enviado a {mod_channel.mention}.",
                ephemeral=True,
            )

    # =========================================================================
    # Authorization handlers
    # =========================================================================

    async def _handle_authorize(self, interaction: discord.Interaction, purga_id: int) -> None:
        """Manejar autorización de una purga.

        Args:
            interaction (discord.Interaction): Interacción del botón.
            purga_id (int): ID del registro de purga.
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        config = await self._get_config(guild.id)

        # Verificar permisos
        admin_roles = config.get(ConfigKey.WAR_ADMIN_ROLES, [])
        if not has_any_role(member=user, role_ids=admin_roles):
            await interaction.response.send_message(
                config.get(ConfigKey.MOD_NO_PERMISSION_TEXT, "Sin permisos."),
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        async with self.bot.database.session() as session:
            purga_service = PurgaService(session)

            record = await purga_service.get_purga(purga_id)
            if not record:
                await interaction.followup.send(
                    "Purga no encontrada.",
                    ephemeral=True,
                )
                return

            if record.status not in (PurgaStatus.PENDING, PurgaStatus.AUTHORIZED):
                await interaction.followup.send(
                    "Esta purga ya no está activa.",
                    ephemeral=True,
                )
                return

            # Añadir autorización (no toggle)
            if user.id in record.authorized_by:
                await interaction.followup.send(
                    "Ya has autorizado esta purga.",
                    ephemeral=True,
                )
                return

            record = await purga_service.add_authorization(purga_id=purga_id, user_id=user.id)
            if not record:
                return

            logger.info(
                f"[{guild.name}] Autorización añadida a purga {purga_id} por {user.display_name}"
            )

            # Calcular autorizaciones requeridas (mínimo 2 si no es modo prueba)
            test_mode = config.get(ConfigKey.TEST_MODE, False)
            required = config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2)
            if not test_mode and required < 2:
                required = 2
            authorized_count = len(record.authorized_by)

            if authorized_count >= required and record.status == PurgaStatus.PENDING:
                # Calcular tiempo de ejecución
                exec_scheduled_for: datetime | None
                if test_mode:
                    # En modo prueba, ejecutar en 2 minutos
                    exec_scheduled_for = datetime.now(UTC) + timedelta(minutes=2)
                else:
                    # Mantener el scheduled_for original
                    exec_scheduled_for = record.scheduled_for

                # Autorizar purga
                updated_record = await purga_service.update_status(
                    purga_id=purga_id,
                    status=PurgaStatus.AUTHORIZED,
                    scheduled_for=exec_scheduled_for,
                )
                if updated_record:
                    record = updated_record
                    logger.info(
                        f"[{guild.name}] Purga {purga_id} autorizada, "
                        f"ejecución programada para {exec_scheduled_for}"
                    )
                    # Quitar de tracking de expiración
                    self._active_purgas.pop(guild.id, None)
                    # Añadir a tracking de ejecución
                    if exec_scheduled_for:
                        self._authorized_purgas[guild.id] = (record.id, exec_scheduled_for)
                    # Enviar mensaje a canal de usuarios
                    await self._send_user_message(
                        guild=guild, record=record, config=config, session=session
                    )

            # Actualizar mensaje de moderación
            await self._update_mod_message(guild=guild, record=record, config=config)

            await session.commit()

            await interaction.followup.send(
                f"Autorización añadida. ({authorized_count}/{required})",
                ephemeral=True,
            )

    async def _handle_cancel(self, interaction: discord.Interaction, purga_id: int) -> None:
        """Manejar voto de cancelación de una purga.

        La cancelación requiere el mismo número de votos que la autorización.

        Args:
            interaction (discord.Interaction): Interacción del botón.
            purga_id (int): ID del registro de purga.
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        config = await self._get_config(guild.id)

        # Verificar permisos
        admin_roles = config.get(ConfigKey.WAR_ADMIN_ROLES, [])
        if not has_any_role(member=user, role_ids=admin_roles):
            await interaction.response.send_message(
                config.get(ConfigKey.MOD_NO_PERMISSION_TEXT, "Sin permisos."),
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        async with self.bot.database.session() as session:
            purga_service = PurgaService(session)

            record = await purga_service.get_purga(purga_id)
            if not record:
                await interaction.followup.send(
                    "Purga no encontrada.",
                    ephemeral=True,
                )
                return

            if record.status not in (PurgaStatus.PENDING, PurgaStatus.AUTHORIZED):
                await interaction.followup.send(
                    "Esta purga no puede ser cancelada.",
                    ephemeral=True,
                )
                return

            # Verificar si ya votó por cancelar
            if user.id in record.cancelled_by:
                await interaction.followup.send(
                    "Ya has votado por cancelar esta purga.",
                    ephemeral=True,
                )
                return

            # Añadir voto de cancelación
            record = await purga_service.add_cancellation(purga_id=purga_id, user_id=user.id)
            if not record:
                return

            logger.info(
                f"[{guild.name}] Voto de cancelación añadido a purga {purga_id} "
                f"por {user.display_name}"
            )

            # Calcular autorizaciones requeridas (mínimo 2 si no es modo prueba)
            test_mode = config.get(ConfigKey.TEST_MODE, False)
            required = config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2)
            if not test_mode and required < 2:
                required = 2
            cancel_count = len(record.cancelled_by)

            if cancel_count >= required:
                # Cancelar la purga
                record = await purga_service.update_status(
                    purga_id=purga_id, status=PurgaStatus.CANCELLED
                )

                if not record:
                    return

                logger.info(f"[{guild.name}] Purga {purga_id} cancelada")

                # Quitar de tracking
                self._active_purgas.pop(guild.id, None)
                self._authorized_purgas.pop(guild.id, None)

                # Quitar rol de reacción a todos los que confirmaron
                reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
                if reaction_role_id and record.confirmed_by:
                    role = guild.get_role(reaction_role_id)
                    if role:
                        for confirmed_user_id in record.confirmed_by:
                            member = guild.get_member(confirmed_user_id)
                            if member and role in member.roles:
                                try:
                                    await member.remove_roles(role)
                                except discord.Forbidden:
                                    logger.warning(
                                        f"No se pudo quitar rol {role.name} a {member.name}"
                                    )

                # Eliminar mensaje de usuarios si existe
                if record.user_message_id and record.user_channel_id:
                    await delete_message(
                        guild=guild,
                        channel_id=record.user_channel_id,
                        message_id=record.user_message_id,
                    )

                # Actualizar mensaje de moderación (quitar botones, mostrar cancelado)
                await self._update_mod_message(
                    guild=guild, record=record, config=config, remove_view=True
                )

                # Programar eliminación del mensaje si hay retención configurada
                retention = config.get(ConfigKey.MOD_MESSAGE_RETENTION, 0)
                if retention > 0 and record.mod_channel_id and record.mod_message_id:
                    self._schedule_message_deletion(
                        channel_id=record.mod_channel_id,
                        message_id=record.mod_message_id,
                        retention_minutes=retention,
                    )

                await session.commit()

                await interaction.followup.send(
                    "Purga cancelada.",
                    ephemeral=True,
                )
            else:
                # Aún no hay suficientes votos
                # Actualizar mensaje de moderación con votos actuales
                await self._update_mod_message(guild=guild, record=record, config=config)

                await session.commit()

                await interaction.followup.send(
                    f"Voto de cancelación añadido. ({cancel_count}/{required})",
                    ephemeral=True,
                )

    # =========================================================================
    # User confirmation handlers
    # =========================================================================

    async def _handle_confirm(self, interaction: discord.Interaction, purga_id: int) -> None:
        """Manejar confirmación de permanencia de un usuario.

        Args:
            interaction (discord.Interaction): Interacción del botón.
            purga_id (int): ID del registro de purga.
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        config = await self._get_config(guild.id)

        async with self.bot.database.session() as session:
            purga_service = PurgaService(session)

            record = await purga_service.get_purga(purga_id)
            if not record:
                await interaction.response.send_message(
                    "Purga no encontrada.",
                    ephemeral=True,
                )
                return

            if record.status != PurgaStatus.AUTHORIZED:
                await interaction.response.send_message(
                    "Esta purga ya no está activa.",
                    ephemeral=True,
                )
                return

            # Toggle confirmación
            was_confirmed = user.id in record.confirmed_by
            if was_confirmed:
                record = await purga_service.remove_confirmation(purga_id=purga_id, user_id=user.id)
                message = config.get(
                    ConfigKey.USER_REMOVED_REACTION_TEXT,
                    "Has retirado tu confirmación.",
                )
                # Quitar rol si está configurado
                reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
                if reaction_role_id:
                    role = guild.get_role(reaction_role_id)
                    if role:
                        try:
                            await user.remove_roles(role)
                        except discord.Forbidden:
                            logger.warning(f"No se pudo quitar rol {role.name} a {user.name}")
            else:
                record = await purga_service.add_confirmation(purga_id=purga_id, user_id=user.id)
                message = config.get(
                    ConfigKey.USER_FIRST_REACTION_TEXT,
                    "Has confirmado tu permanencia.",
                )
                # Asignar rol si está configurado
                reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
                if reaction_role_id:
                    role = guild.get_role(reaction_role_id)
                    if role:
                        try:
                            await user.add_roles(role)
                        except discord.Forbidden:
                            logger.warning(f"No se pudo asignar rol {role.name} a {user.name}")

            await session.commit()

            await interaction.response.send_message(message, ephemeral=True)

    # =========================================================================
    # Message update helpers
    # =========================================================================

    async def _update_mod_message(
        self,
        guild: discord.Guild,
        record: PurgaRecord,
        config: dict[str, Any],
        remove_view: bool = False,
        execution_logs: list[str] | None = None,
    ) -> None:
        """Actualizar el mensaje de moderación.

        Args:
            guild (discord.Guild): Guild.
            record (PurgaRecord): Registro de purga.
            config (dict[str, Any]): Configuración.
            remove_view (bool): Si True, elimina los botones.
            execution_logs (list[str] | None): Logs de ejecución para añadir.
        """
        if not record.mod_message_id or not record.mod_channel_id:
            return

        channel = guild.get_channel(record.mod_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(record.mod_message_id)
        except discord.NotFound:
            logger.warning(f"Mensaje de mod no encontrado: {record.mod_message_id}")
            return

        content = self._get_mod_message_content(
            guild=guild, record=record, config=config, execution_logs=execution_logs
        )

        if remove_view or record.status in (
            PurgaStatus.CANCELLED,
            PurgaStatus.EXPIRED,
            PurgaStatus.EXECUTED,
            PurgaStatus.FAILED,
        ):
            await message.edit(content=content, view=None)
        elif record.status in (PurgaStatus.PENDING, PurgaStatus.AUTHORIZED):
            # Crear vista con el botón apropiado según el estado
            button_color = config.get(ConfigKey.MOD_BUTTON_COLOR, "green")
            authorize_label = config.get(ConfigKey.MOD_BUTTON_TEXT, "🔑 Autorizar purga")
            cancel_label = config.get(ConfigKey.MOD_STOP_BUTTON_TEXT, "🛑 Detener purga")

            view = ModAuthorizationView(
                purga_id=record.id,
                status=PurgaStatus(record.status),
                authorize_label=authorize_label,
                cancel_label=cancel_label,
                button_style=self._get_button_style(button_color),
            )
            await message.edit(content=content, view=view)
        else:
            await message.edit(content=content)

    async def _send_user_message(
        self,
        guild: discord.Guild,
        record: PurgaRecord,
        config: dict[str, Any],
        session: Any,
    ) -> None:
        """Enviar mensaje al canal de usuarios.

        Args:
            guild (discord.Guild): Guild.
            record (PurgaRecord): Registro de purga.
            config (dict[str, Any]): Configuración.
            session: Sesión de base de datos.
        """
        user_channel_id = config.get(ConfigKey.USER_CHANNEL)
        if not user_channel_id:
            return

        channel = guild.get_channel(user_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        # Formatear mensaje
        affected_roles = config.get(ConfigKey.WAR_AFFECTED_ROLES, [])
        roles_text = self._format_roles(guild=guild, role_ids=affected_roles)

        reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
        reaction_role = guild.get_role(reaction_role_id) if reaction_role_id else None
        reaction_role_text = reaction_role.mention if reaction_role else ""

        execution_date = "No programada"
        if record.scheduled_for:
            execution_date = record.scheduled_for.strftime("%Y-%m-%d %H:%M UTC")

        content = self._format_message(
            template=config.get(ConfigKey.WAR_MESSAGE_TEMPLATE),
            roles=roles_text,
            dia=execution_date,
            reaction_rol=reaction_role_text,
        )

        # Crear vista con botón
        button_color = config.get(ConfigKey.USER_BUTTON_COLOR, "green")
        confirm_label = config.get(ConfigKey.USER_BUTTON_TEXT, "🛡️ Confirmar permanencia")

        view = UserConfirmationView(
            purga_id=record.id,
            confirm_label=confirm_label,
            button_style=self._get_button_style(button_color),
        )

        user_message = await channel.send(content=content, view=view)

        # Actualizar registro
        purga_service = PurgaService(session)
        await purga_service.update_user_message(
            purga_id=record.id,
            channel_id=channel.id,
            message_id=user_message.id,
        )

    # =========================================================================
    # Event listeners
    # =========================================================================

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Registrar comandos cuando el bot está listo."""
        logger.info("PurgaCog: Registrando comandos en todos los guilds...")
        for guild in self.bot.guilds:
            try:
                await self._register_guild_commands(guild)
            except Exception as e:
                logger.error(f"Error registrando comandos en {guild.name}: {e}")

        # Sync commands for all guilds
        for guild in self.bot.guilds:
            if guild.id in self._registered_commands:
                await self._sync_guild_commands(guild)

        logger.info("PurgaCog: Registro de comandos completado")

        # Restaurar purgas activas desde la base de datos
        await self._restore_active_purgas()

        # Verificar expiración inmediatamente
        await self._check_expired_purgas()

        # Iniciar tarea de verificación de expiración
        if not self.expiration_check_loop.is_running():
            self.expiration_check_loop.start()

    async def _restore_active_purgas(self) -> None:
        """Restaurar purgas pendientes y autorizadas desde la base de datos al iniciar.

        Esto permite que las purgas activas sigan siendo monitoreadas
        después de un reinicio del bot.
        """
        try:
            async with self.bot.database.session() as session:
                purga_service = PurgaService(session)

                # Restaurar purgas pendientes de autorización
                pending_purgas = await purga_service.get_pending_purgas()
                for record in pending_purgas:
                    self._active_purgas[record.guild_id] = (record.id, record.expires_at)
                    logger.info(
                        f"Purga pendiente {record.id} restaurada para guild {record.guild_id}"
                    )

                # Restaurar purgas autorizadas pendientes de ejecución
                authorized_purgas = await purga_service.get_authorized_purgas()
                for record in authorized_purgas:
                    if record.scheduled_for:
                        self._authorized_purgas[record.guild_id] = (record.id, record.scheduled_for)
                        logger.info(
                            f"Purga autorizada {record.id} restaurada para guild {record.guild_id}"
                        )

                total = len(pending_purgas) + len(authorized_purgas)
                if total:
                    logger.info(f"PurgaCog: {total} purgas restauradas")
        except Exception as e:
            logger.error(f"Error restaurando purgas activas: {e}")

    async def cog_unload(self) -> None:
        """Limpiar recursos al descargar el cog."""
        self.expiration_check_loop.cancel()

    def _schedule_message_deletion(
        self, channel_id: int, message_id: int, retention_minutes: int
    ) -> None:
        """Programar eliminación de un mensaje.

        Args:
            channel_id (int): ID del canal.
            message_id (int): ID del mensaje.
            retention_minutes (int): Minutos hasta eliminar. 0 = no eliminar.
        """
        if retention_minutes > 0:
            delete_at = datetime.now(UTC) + timedelta(minutes=retention_minutes)
            self._pending_deletions[(channel_id, message_id)] = delete_at
            logger.debug(f"Mensaje {message_id} programado para eliminar a las {delete_at}")

    async def _check_pending_deletions(self) -> None:
        """Verificar y eliminar mensajes que han pasado su tiempo de retención."""
        now = datetime.now(UTC)
        to_delete: list[tuple[int, int]] = []

        for (channel_id, message_id), delete_at in self._pending_deletions.items():
            if delete_at <= now:
                to_delete.append((channel_id, message_id))

        for channel_id, message_id in to_delete:
            self._pending_deletions.pop((channel_id, message_id), None)
            try:
                channel = self.bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.delete()
                        logger.info(f"Mensaje {message_id} eliminado por retención")
                    except discord.NotFound:
                        pass  # Ya fue eliminado
            except Exception as e:
                logger.error(f"Error eliminando mensaje {message_id}: {e}")

    async def _check_expired_purgas(self) -> None:
        """Verificar y expirar purgas pendientes que han pasado su tiempo límite."""
        now = datetime.now(UTC)
        expired_guilds: list[int] = []

        # Identificar purgas expiradas
        for guild_id, (_purga_id, expires_at) in self._active_purgas.items():
            if expires_at and expires_at <= now:
                expired_guilds.append(guild_id)

        # Procesar purgas expiradas
        for guild_id in expired_guilds:
            purga_id, _ = self._active_purgas.pop(guild_id)
            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else str(guild_id)
            logger.info(f"[{guild_name}] Purga {purga_id} ha expirado")

            try:
                async with self.bot.database.session() as session:
                    purga_service = PurgaService(session)

                    # Actualizar estado a expirado
                    record = await purga_service.update_status(
                        purga_id=purga_id, status=PurgaStatus.EXPIRED
                    )

                    if record and guild:
                        config = await self._get_config(guild_id)
                        await self._update_mod_message(
                            guild=guild,
                            record=record,
                            config=config,
                            remove_view=True,
                        )
                        # Programar eliminación si hay retención configurada
                        retention = config.get(ConfigKey.MOD_MESSAGE_RETENTION, 0)
                        if retention > 0 and record.mod_channel_id and record.mod_message_id:
                            self._schedule_message_deletion(
                                record.mod_channel_id, record.mod_message_id, retention
                            )

                    await session.commit()
            except Exception as e:
                logger.error(f"Error expirando purga {purga_id}: {e}")

    async def _check_ready_purgas(self) -> None:
        """Verificar y ejecutar purgas autorizadas que han alcanzado su tiempo de ejecución."""
        now = datetime.now(UTC)
        ready_guilds: list[int] = []

        # Identificar purgas listas para ejecutar
        for guild_id, (_purga_id, scheduled_for) in self._authorized_purgas.items():
            if scheduled_for <= now:
                ready_guilds.append(guild_id)

        # Procesar purgas listas
        for guild_id in ready_guilds:
            purga_id, _ = self._authorized_purgas.pop(guild_id)
            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else str(guild_id)
            logger.info(f"[{guild_name}] Purga {purga_id} lista para ejecutar")

            try:
                await self._execute_purga(guild_id=guild_id, purga_id=purga_id)
            except Exception as e:
                logger.error(f"Error ejecutando purga {purga_id}: {e}")

    async def _execute_purga(self, guild_id: int, purga_id: int) -> None:
        """Ejecutar una purga.

        Args:
            guild_id (int): ID del guild.
            purga_id (int): ID de la purga.
        """
        guild = self.bot.get_guild(guild_id)
        if not guild:
            logger.error(f"Guild {guild_id} no encontrado para ejecutar purga {purga_id}")
            return

        async with self.bot.database.session() as session:
            purga_service = PurgaService(session)
            record = await purga_service.get_purga(purga_id)

            if not record or record.status != PurgaStatus.AUTHORIZED:
                logger.warning(f"Purga {purga_id} no está en estado autorizado")
                return

            config = await self._get_config(guild_id)
            test_mode = record.config_snapshot.get("test_mode", False)
            audit_level = config.get(ConfigKey.AUDIT_LEVEL, 1)

            logger.info(
                f"[{guild.name}] {'[MODO PRUEBA] ' if test_mode else ''}Ejecutando purga {purga_id}"
            )

            # Config from snapshot
            affected_roles = record.config_snapshot.get("affected_roles", [])
            roles_to_remove = record.config_snapshot.get("roles_to_remove", [])
            roles_to_add = record.config_snapshot.get("roles_to_add", [])
            promotions = record.config_snapshot.get("promotions", [])
            default_promotion = record.config_snapshot.get("default_promotion")
            confirmed_users = set(record.confirmed_by)

            # Stats
            cleaned_count = 0
            promoted_in_group = 0
            promoted_not_in_group = 0
            processed_users: set[int] = set()

            # Execution logs (will be added to mod message)
            execution_logs: list[str] = []

            # Add simulation indicator once at the start
            if test_mode:
                simulation_msg = config.get(ConfigKey.EXEC_MSG_SIMULATION, "🧪 **[MODO PRUEBA]**")
                execution_logs.append(simulation_msg)

            # === LOG INIT MESSAGE (level 1) ===
            if audit_level >= 1:
                msg = config.get(ConfigKey.EXEC_MSG_INIT, "🔥 **Iniciando purga...**")
                execution_logs.append(msg)

            # === PHASE 1: CLEAN NON-CONFIRMED USERS ===
            for role_id in affected_roles:
                role = guild.get_role(role_id)
                if not role:
                    continue

                # Log level 2 message
                if audit_level >= 2:
                    msg_template = config.get(
                        ConfigKey.EXEC_MSG_CLEANING_ROLE,
                        "🧹 Aplicando purga al rol {role}...",
                    )
                    msg = self._format_message(msg_template, role=role.name)
                    execution_logs.append(msg)

                # Find members with this role who did NOT confirm
                for member in role.members:
                    if member.id in confirmed_users:
                        continue
                    if member.id in processed_users:
                        continue

                    roles_before = [r.id for r in member.roles if r != guild.default_role]

                    # Remove roles
                    if roles_to_remove:
                        roles_to_rm: list[discord.Role] = [
                            rm_role
                            for rid in roles_to_remove
                            if (rm_role := guild.get_role(rid)) and rm_role in member.roles
                        ]
                        if roles_to_rm:
                            try:
                                await member.remove_roles(*roles_to_rm)
                            except discord.Forbidden:
                                logger.warning(f"No se pudo quitar roles a {member.name}")
                    else:
                        # Remove all roles except default
                        try:
                            await member.edit(roles=[])
                        except discord.Forbidden:
                            logger.warning(f"No se pudo quitar roles a {member.name}")

                    # Add purge roles
                    if roles_to_add:
                        roles_to_give: list[discord.Role] = [
                            add_role for rid in roles_to_add if (add_role := guild.get_role(rid))
                        ]
                        if roles_to_give:
                            try:
                                await member.add_roles(*roles_to_give)
                            except discord.Forbidden:
                                logger.warning(f"No se pudo añadir roles a {member.name}")

                    # Refresh member and get roles_after
                    refreshed = guild.get_member(member.id)
                    if refreshed:
                        member = refreshed
                    roles_after = [r.id for r in member.roles if r != guild.default_role]

                    # Store result
                    await purga_service.add_user_result(
                        purga_id=purga_id,
                        user_id=member.id,
                        action_type="cleaned",
                        roles_before=roles_before,
                        roles_after=roles_after,
                    )

                    # Audit level 2: log each user
                    if audit_level >= 2:
                        msg_template = config.get(
                            ConfigKey.EXEC_MSG_USER_CLEANED,
                            "  ↳ 🧹 Purgado: {user}",
                        )
                        msg = self._format_message(msg_template, user=member.display_name)
                        execution_logs.append(msg)

                    processed_users.add(member.id)
                    cleaned_count += 1

                # Update mod message after each role (to show progress)
                if audit_level >= 1:
                    await self._update_mod_message(
                        guild=guild,
                        record=record,
                        config=config,
                        execution_logs=execution_logs,
                    )

            # === PHASE 2: APPLY PROMOTIONS ===
            if audit_level >= 1:
                msg = config.get(
                    ConfigKey.EXEC_MSG_PROMOTIONS_START, "⬆️ **Aplicando promociones...**"
                )
                execution_logs.append(msg)

            # Build promotion map: from_role_id -> to_role_id
            promotion_map: dict[int, int] = {}
            for promo in promotions:
                from_role = promo.get("from_role")
                to_role = promo.get("to_role")
                if from_role and to_role:
                    # Handle both string and int IDs (legacy data may have strings)
                    promotion_map[int(from_role)] = int(to_role)

            promoted_users: set[int] = set()

            # Apply promotions based on roles
            for from_role_id, to_role_id in promotion_map.items():
                from_role = guild.get_role(from_role_id)
                to_role = guild.get_role(to_role_id)
                if not from_role or not to_role:
                    continue

                # Log level 2 message
                if audit_level >= 2:
                    msg_template = config.get(
                        ConfigKey.EXEC_MSG_PROMOTION_ROLE,
                        "📈 Promocionando {from_role} → {to_role}...",
                    )
                    msg = self._format_message(
                        msg_template, from_role=from_role.name, to_role=to_role.name
                    )
                    execution_logs.append(msg)

                # Find confirmed members with from_role
                for member in from_role.members:
                    if member.id not in confirmed_users:
                        continue
                    if member.id in promoted_users:
                        continue

                    roles_before = [r.id for r in member.roles if r != guild.default_role]
                    in_affected = from_role_id in affected_roles

                    try:
                        # If from_role is in affected_roles, remove it
                        if in_affected:
                            await member.remove_roles(from_role)
                        await member.add_roles(to_role)
                    except discord.Forbidden:
                        logger.warning(f"No se pudo promocionar a {member.name}")

                    # Refresh member and get roles_after
                    refreshed = guild.get_member(member.id)
                    if refreshed:
                        member = refreshed
                    roles_after = [r.id for r in member.roles if r != guild.default_role]

                    # Store result
                    await purga_service.add_user_result(
                        purga_id=purga_id,
                        user_id=member.id,
                        action_type="promoted",
                        roles_before=roles_before,
                        roles_after=roles_after,
                        in_affected_group=in_affected,
                    )

                    # Audit level 2: log each user
                    if audit_level >= 2:
                        msg_template = config.get(
                            ConfigKey.EXEC_MSG_USER_PROMOTED,
                            "  ↳ ⬆️ Promocionado: {user} ({from_role} → {to_role})",
                        )
                        msg = self._format_message(
                            msg_template,
                            user=member.display_name,
                            from_role=from_role.name,
                            to_role=to_role.name,
                        )
                        execution_logs.append(msg)

                    promoted_users.add(member.id)
                    if in_affected:
                        promoted_in_group += 1
                    else:
                        promoted_not_in_group += 1

            # Apply default promotion to confirmed users without any promotion
            if default_promotion:
                default_role = guild.get_role(default_promotion)
                if default_role:
                    # Log level 2 message
                    if audit_level >= 2:
                        msg_template = config.get(
                            ConfigKey.EXEC_MSG_PROMOTION_DEFAULT,
                            "📈 Aplicando promoción por defecto ({role})...",
                        )
                        msg = self._format_message(msg_template, role=default_role.name)
                        execution_logs.append(msg)

                    for user_id in confirmed_users:
                        if user_id in promoted_users:
                            continue
                        if user_id in processed_users:
                            continue

                        default_member = guild.get_member(user_id)
                        if not default_member:
                            continue

                        roles_before = [
                            r.id for r in default_member.roles if r != guild.default_role
                        ]

                        try:
                            await default_member.add_roles(default_role)
                        except discord.Forbidden:
                            logger.warning(
                                f"No se pudo aplicar rol a usuario no afectado: "
                                f"{default_member.name}"
                            )

                        # Refresh member and get roles_after
                        refreshed = guild.get_member(default_member.id)
                        if refreshed:
                            default_member = refreshed
                        roles_after = [
                            r.id for r in default_member.roles if r != guild.default_role
                        ]

                        # Store result
                        await purga_service.add_user_result(
                            purga_id=purga_id,
                            user_id=default_member.id,
                            action_type="promoted",
                            roles_before=roles_before,
                            roles_after=roles_after,
                            in_affected_group=False,
                        )

                        # Audit level 2: log each user
                        if audit_level >= 2:
                            msg_template = config.get(
                                ConfigKey.EXEC_MSG_USER_PROMOTED_DEFAULT,
                                "  ↳ ⬆️ Promocionado: {user} (→ {role})",
                            )
                            msg = self._format_message(
                                msg_template,
                                user=default_member.display_name,
                                role=default_role.name,
                            )
                            execution_logs.append(msg)

                        promoted_users.add(user_id)
                        promoted_not_in_group += 1

                    # Update mod message after default promotions
                    if audit_level >= 1:
                        await self._update_mod_message(
                            guild=guild,
                            record=record,
                            config=config,
                            execution_logs=execution_logs,
                        )

            # === REMOVE REACTION ROLE FROM ALL CONFIRMED ===
            reaction_role_id = record.config_snapshot.get("reaction_role")
            if reaction_role_id:
                reaction_role = guild.get_role(reaction_role_id)
                if reaction_role:
                    for user_id in confirmed_users:
                        reaction_member = guild.get_member(user_id)
                        if reaction_member and reaction_role in reaction_member.roles:
                            try:
                                await reaction_member.remove_roles(reaction_role)
                            except discord.Forbidden:
                                logger.warning(
                                    f"No se pudo quitar rol de reacción a {reaction_member.name}"
                                )

            # === LOG FINISH MESSAGE (level 1) ===
            if audit_level >= 1:
                msg_template = config.get(
                    ConfigKey.EXEC_MSG_FINISH,
                    "✅ **Purga finalizada.** Purgados: {cleaned} | "
                    "Promocionados (grupo): {promoted_in_group} | "
                    "Promocionados (otros): {promoted_not_in_group}",
                )
                msg = self._format_message(
                    msg_template,
                    cleaned=str(cleaned_count),
                    promoted_in_group=str(promoted_in_group),
                    promoted_not_in_group=str(promoted_not_in_group),
                )
                execution_logs.append(msg)

            # Update execution result
            execution_result = {
                "test_mode": test_mode,
                "confirmed_count": len(confirmed_users),
                "cleaned_count": cleaned_count,
                "promoted_in_group": promoted_in_group,
                "promoted_not_in_group": promoted_not_in_group,
            }

            record = await purga_service.update_status(
                purga_id=purga_id,
                status=PurgaStatus.EXECUTED,
                execution_result=execution_result,
            )

            if record:
                # Eliminar mensaje de usuarios
                if record.user_message_id and record.user_channel_id:
                    await delete_message(
                        guild=guild,
                        channel_id=record.user_channel_id,
                        message_id=record.user_message_id,
                    )

                # Actualizar mensaje de moderación con logs finales
                await self._update_mod_message(
                    guild=guild,
                    record=record,
                    config=config,
                    remove_view=True,
                    execution_logs=execution_logs if audit_level >= 1 else None,
                )

                # Programar eliminación si hay retención configurada
                retention = config.get(ConfigKey.MOD_MESSAGE_RETENTION, 0)
                if retention > 0 and record.mod_channel_id and record.mod_message_id:
                    self._schedule_message_deletion(
                        channel_id=record.mod_channel_id,
                        message_id=record.mod_message_id,
                        retention_minutes=retention,
                    )

                logger.info(
                    f"[{guild.name}] {'[MODO PRUEBA] ' if test_mode else ''}"
                    f"Purga {purga_id} ejecutada: cleaned={cleaned_count}, "
                    f"promoted_in={promoted_in_group}, promoted_out={promoted_not_in_group}"
                )

            await session.commit()

    @tasks.loop(minutes=1)
    async def expiration_check_loop(self) -> None:
        """Loop que verifica purgas expiradas, ejecuciones y mensajes pendientes."""
        await self._check_expired_purgas()
        await self._check_ready_purgas()
        await self._check_pending_deletions()

    @expiration_check_loop.before_loop
    async def before_expiration_check(self) -> None:
        """Esperar a que el bot esté listo antes de iniciar el loop."""
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Registrar comandos cuando el bot se une a un guild.

        Args:
            guild (discord.Guild): Guild al que se unió el bot.
        """
        logger.info(f"PurgaCog: Bot unido a {guild.name}, registrando comandos...")
        await self._register_guild_commands(guild)
        if guild.id in self._registered_commands:
            await self._sync_guild_commands(guild)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Manejar interacciones de botones con IDs dinámicos.

        Los botones tienen custom_ids como 'purga:authorize:123' que incluyen
        el purga_id. Este listener maneja estos botones para que funcionen
        incluso después de reiniciar el bot.

        Args:
            interaction (discord.Interaction): Interacción recibida.
        """
        if interaction.type != discord.InteractionType.component:
            return

        custom_id: str = str(interaction.data.get("custom_id", "") if interaction.data else "")

        # Manejar botón de autorizar: purga:authorize:{purga_id}
        if custom_id.startswith("purga:authorize:"):
            try:
                purga_id = int(custom_id.split(":")[2])
                await self._handle_authorize(interaction=interaction, purga_id=purga_id)
            except (ValueError, IndexError):
                logger.error(f"Custom ID inválido para authorize: {custom_id}")
            return

        # Manejar botón de cancelar: purga:cancel:{purga_id}
        if custom_id.startswith("purga:cancel:"):
            try:
                purga_id = int(custom_id.split(":")[2])
                await self._handle_cancel(interaction=interaction, purga_id=purga_id)
            except (ValueError, IndexError):
                logger.error(f"Custom ID inválido para cancel: {custom_id}")
            return

        # Manejar botón de confirmar: purga:confirm:{purga_id}
        if custom_id.startswith("purga:confirm:"):
            try:
                purga_id = int(custom_id.split(":")[2])
                await self._handle_confirm(interaction=interaction, purga_id=purga_id)
            except (ValueError, IndexError):
                logger.error(f"Custom ID inválido para confirm: {custom_id}")
            return

    # =========================================================================
    # Config change callbacks
    # =========================================================================

    async def on_cog_toggled(self, guild: discord.Guild, enabled: bool) -> None:
        """Callback cuando el cog es habilitado o deshabilitado.

        Args:
            guild (discord.Guild): Guild donde cambió el estado.
            enabled (bool): True si fue habilitado.
        """
        if enabled:
            logger.info(f"PurgaCog habilitado en {guild.name}, registrando comandos...")
            await self._register_guild_commands(guild)
            if guild.id in self._registered_commands:
                await self._sync_guild_commands(guild)
        else:
            logger.info(f"PurgaCog deshabilitado en {guild.name}, eliminando comandos...")
            await self._unregister_guild_commands(guild)
            await self._sync_guild_commands(guild)

    async def on_config_changed(self, guild: discord.Guild, key: str) -> None:
        """Callback cuando cambia la configuración del cog.

        Args:
            guild (discord.Guild): Guild donde cambió la configuración.
            key (str): Clave de configuración que cambió.
        """
        # Keys that affect command registration
        essential_keys = {
            ConfigKey.WAR_COMMAND_NAME,
            ConfigKey.MOD_CHANNEL,
            ConfigKey.USER_CHANNEL,
            ConfigKey.WAR_ADMIN_ROLES,
            ConfigKey.WAR_AFFECTED_ROLES,
        }

        if key in essential_keys:
            logger.debug(
                f"Configuración esencial '{key}' cambiada en {guild.name}, "
                "programando re-evaluación de comandos..."
            )
            # Use debounced sync to batch multiple config changes
            await self._debounced_register_and_sync(guild)


async def setup(bot: DiscordBot) -> None:
    """Configurar el cog.

    Args:
        bot (DiscordBot): Instancia del bot de Discord.
    """
    get_config_schema_service().register_schema(PURGA_CONFIG_SCHEMA)
    await bot.add_cog(PurgaCog(bot))
    logger.info("PurgaCog cargado")


async def teardown(bot: DiscordBot) -> None:
    """Limpiar el cog.

    Args:
        bot (DiscordBot): Instancia del bot de Discord.
    """
    cog = bot.get_cog("PurgaCog")
    if cog and isinstance(cog, PurgaCog):
        # Unregister all commands
        for guild_id in list(cog._registered_commands.keys()):
            guild = bot.get_guild(guild_id)
            if guild:
                await cog._unregister_guild_commands(guild)
    get_config_schema_service().unregister_schema(COG_NAME)
    logger.info("PurgaCog descargado")
