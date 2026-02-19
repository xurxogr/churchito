"""Configuración y esquema del cog de purga."""

import discord

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.purga.enums import ConfigKey

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
            key=ConfigKey.EXEC_MSG_GLOBAL_REMOVE_START,
            name="Mensaje: Inicio limpieza global",
            description="Mensaje al iniciar la eliminación de roles globales (nivel 1+)",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="🧹 **Eliminando roles globales...**",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_GLOBAL_REMOVE_USER,
            name="Mensaje: Usuario limpieza global",
            description="Mensaje por cada usuario al que se le quitan roles globales (nivel 2). "
            "Placeholders: {user}, {roles}",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="  ↳ 🧹 Roles eliminados: {user} ({roles})",
            max_length=200,
            placeholders=["user", "roles"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_FINISH,
            name="Mensaje: Fin de purga",
            description="Mensaje al finalizar (nivel 1+). "
            "Placeholders: {cleaned}, {promoted_in_group}, {promoted_not_in_group}, "
            "{global_removed}",
            option_type=ConfigOptionType.STRING,
            section="Común",
            group="Mensajes de ejecución",
            default="✅ **Purga finalizada.** "
            "Purgados: {cleaned} | Promocionados (grupo): {promoted_in_group} | "
            "Promocionados (otros): {promoted_not_in_group} | "
            "Roles globales eliminados: {global_removed}",
            max_length=500,
            placeholders=[
                "cleaned",
                "promoted_in_group",
                "promoted_not_in_group",
                "global_removed",
            ],
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
            key=ConfigKey.WAR_GLOBAL_ROLES_TO_REMOVE,
            name="Roles a eliminar (todos)",
            description="Roles que se eliminan a TODOS los miembros del servidor, "
            "independientemente de si reaccionaron o están en roles afectados",
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
