"""Configuración y esquema del cog de verificación."""

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.verification.enums import AutoProcessMode, ConfigKey, NameMatchMode

COG_NAME = "verification"

VERIFICATION_CONFIG_SCHEMA = CogConfigSchema(
    cog_name=COG_NAME,
    display_name="Verificación",
    description="Sistema de verificación de usuarios con capturas de pantalla",
    icon="✅",
    options=[
        # ===== 1. OPCIONES GENERALES =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_ENABLED,
            name="Verificación habilitada",
            description="Habilitar o deshabilitar el sistema de verificación",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
            group="Opciones",
        ),
        ConfigOption(
            key=ConfigKey.BLOCK_ALREADY_VERIFIED,
            name="Bloquear usuarios verificados",
            description="Impedir que usuarios con roles de verificado inicien nueva verificación",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
            group="Opciones",
        ),
        ConfigOption(
            key=ConfigKey.AUTO_REJECT_REVIEW_WINDOW,
            name="Ventana de revisión (minutos)",
            description=(
                "Minutos durante los cuales un moderador puede revisar un auto-rechazo. "
                "0 para desactivar."
            ),
            option_type=ConfigOptionType.INTEGER,
            default=30,
            min_value=0,
            max_value=1440,
            group="Opciones",
        ),
        # ===== 2. PANEL DE VERIFICACIÓN =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_CHANNEL,
            name="Canal de verificación",
            description=(
                "Canal donde se publica el panel de verificación con botónes. "
                "Solo se muestran canales donde el bot tiene permiso de escritura."
            ),
            option_type=ConfigOptionType.CHANNEL,
            group="Panel de verificación",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_PANEL_MESSAGE,
            name="Mensaje del panel",
            description=(
                "Mensaje que aparece en el panel de verificación. "
                "Si incluyes una URL de imagen (terminada en .png, .jpg, .gif, etc.) "
                "se mostrará como imagen en el embed."
            ),
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Bienvenido a {server_name}!**\n\n"
                "Para acceder al servidor, necesitas verificarte. "
                "Haz clic en el botón correspondiente para comenzar."
            ),
            max_length=4000,
            placeholders=["server_name"],
            group="Panel de verificación",
        ),
        ConfigOption(
            key=ConfigKey.VERIFY_BUTTON_TEXT,
            name="Texto botón verificar",
            description="Texto del botón de verificación normal",
            option_type=ConfigOptionType.STRING,
            default="Verificar",
            max_length=80,
            group="Panel de verificación",
        ),
        ConfigOption(
            key=ConfigKey.VERIFY_ALLY_BUTTON_TEXT,
            name="Texto botón aliado",
            description="Texto del botón de verificación como aliado",
            option_type=ConfigOptionType.STRING,
            default="Verificar como Aliado",
            max_length=80,
            group="Panel de verificación",
        ),
        ConfigOption(
            key=ConfigKey.HEALTH_CHECK_INTERVAL,
            name="Intervalo de verificación (minutos)",
            description="Frecuencia de verificación del panel (0 para desactivar)",
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
            description="Nombre a mostrar para verificación normal en mensajes",
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
                "**Instrucciones de Verificación**\n\n"
                "Hola {username}! Para completar tu verificación en **{server_name}**, "
                "envia **2 capturas de pantalla** en un solo mensaje."
            ),
            max_length=4000,
            placeholders=["username", "user_mention", "server_name", "verification_type"],
            group="Verificación (Normal)",
        ),
        ConfigOption(
            key=ConfigKey.REGULAR_ROLES_ADD,
            name="Roles a agregar",
            description="Roles que se agregan al aprobar verificación normal",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Verificación (Normal)",
        ),
        ConfigOption(
            key=ConfigKey.REGULAR_ROLES_REMOVE,
            name="Roles a quitar",
            description="Roles que se quitan al aprobar verificación normal",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Verificación (Normal)",
        ),
        ConfigOption(
            key=ConfigKey.APPROVAL_MESSAGE_REGULAR,
            name="Mensaje de aprobación",
            description="Mensaje enviado al usuario cuando es aprobado",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Verificación aprobada!**\n\n"
                "Tu verificación en **{server_name}** ha sido aprobada. "
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
            description="Nombre a mostrar para verificación de aliado en mensajes",
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
                "**Instrucciones de Verificación (Aliado)**\n\n"
                "Hola {username}! Para completar tu verificación como aliado en **{server_name}**, "
                "envia **2 capturas de pantalla** en un solo mensaje."
            ),
            max_length=4000,
            placeholders=["username", "user_mention", "server_name", "verification_type"],
            group="Verificación (Aliado)",
        ),
        ConfigOption(
            key=ConfigKey.ALLY_ROLES_ADD,
            name="Roles a agregar",
            description="Roles que se agregan al aprobar verificación de aliado",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Verificación (Aliado)",
        ),
        ConfigOption(
            key=ConfigKey.ALLY_ROLES_REMOVE,
            name="Roles a quitar",
            description="Roles que se quitan al aprobar verificación de aliado",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Verificación (Aliado)",
        ),
        ConfigOption(
            key=ConfigKey.APPROVAL_MESSAGE_ALLY,
            name="Mensaje de aprobación",
            description="Mensaje enviado al usuario cuando es aprobado como aliado",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Verificación de aliado aprobada!**\n\n"
                "Tu verificación como aliado en **{server_name}** ha sido aprobada. "
                "Ya tienes acceso como aliado al servidor."
            ),
            max_length=2000,
            placeholders=["username", "server_name"],
            group="Verificación (Aliado)",
        ),
        # ===== 4. PANEL DE MODERACIÓN =====
        ConfigOption(
            key=ConfigKey.MOD_NOTIFICATION_CHANNEL,
            name="Canal de moderación",
            description=(
                "Canal donde los moderadores reciben notificaciones de verificación. "
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
            key=ConfigKey.MOD_EMBED_COLOR_REGULAR,
            name="Color embed (Normal)",
            description=(
                "Color del embed para verificaciones normales (formato hex: #FF5733). "
                "Dejar vacío para usar naranja por defecto."
            ),
            option_type=ConfigOptionType.STRING,
            default="",
            max_length=7,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.MOD_EMBED_COLOR_ALLY,
            name="Color embed (Aliado)",
            description=(
                "Color del embed para verificaciones de aliados (formato hex: #FF5733). "
                "Dejar vacío para usar naranja por defecto."
            ),
            option_type=ConfigOptionType.STRING,
            default="",
            max_length=7,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.MOD_EMBED_ICON_REGULAR,
            name="Icono embed (Normal)",
            description=(
                "URL de la imagen para el thumbnail en verificaciones normales. "
                "Dejar vacío para usar el avatar por defecto del usuario."
            ),
            option_type=ConfigOptionType.STRING,
            default="",
            max_length=500,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.MOD_EMBED_ICON_ALLY,
            name="Icono embed (Aliado)",
            description=(
                "URL de la imagen para el thumbnail en verificaciones de aliados. "
                "Dejar vacío para usar el avatar por defecto del usuario."
            ),
            option_type=ConfigOptionType.STRING,
            default="",
            max_length=500,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.MOD_EMBED_TITLE_REGULAR,
            name="Título embed (Normal)",
            description=(
                "Título del embed para verificaciones normales. Dejar vacío para no mostrar título."
            ),
            option_type=ConfigOptionType.STRING,
            default="",
            max_length=256,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.MOD_EMBED_TITLE_ALLY,
            name="Título embed (Aliado)",
            description=(
                "Título del embed para verificaciones de aliados. "
                "Dejar vacío para no mostrar título."
            ),
            option_type=ConfigOptionType.STRING,
            default="",
            max_length=256,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.MOD_MESSAGE_TEMPLATE,
            name="Mensaje de moderación",
            description="Mensaje en el canal de moderación (se actualiza con el progreso)",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Solicitud de verificación**\n\n"
                "**Usuario:** {user_mention} ({username})\n"
                "**Tipo:** {verification_type}\n"
                "**Fecha:** {created_at}\n\n"
                "{status}"
            ),
            max_length=2000,
            placeholders=[
                "username",
                "user_mention",
                "verification_type",
                "status",
                "created_at",
            ],
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.MOD_PING_MESSAGE,
            name="Mensaje de ping a moderadores",
            description=(
                "Mensaje que se envía para notificar a los moderadores cuando hay una "
                "verificación pendiente. Usa {roles} para mencionar los roles. "
                "Déjalo vacío para no enviar ping."
            ),
            option_type=ConfigOptionType.STRING,
            default="{roles} - Nueva verificación pendiente de revisión",
            max_length=500,
            placeholders=["roles"],
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.DELETE_PROCESSED_MESSAGES,
            name="Eliminar mensajes procesados",
            description="Eliminar mensajes del canal de moderación tras aceptar/rechazar",
            option_type=ConfigOptionType.BOOLEAN,
            default=False,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.ACCEPT_BUTTON_TEXT,
            name="Texto botón aceptar",
            description="Texto del botón de aceptar para moderadores",
            option_type=ConfigOptionType.STRING,
            default="Aceptar",
            max_length=80,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_BUTTON_TEXT,
            name="Texto botón rechazar",
            description="Texto del botón de rechazar para moderadores",
            option_type=ConfigOptionType.STRING,
            default="Rechazar",
            max_length=80,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REVIEW_BUTTON_TEXT,
            name="Texto botón revisar",
            description="Texto del botón para revisar auto-rechazos",
            option_type=ConfigOptionType.STRING,
            default="Revisar",
            max_length=80,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.HISTORY_LABEL,
            name="Etiqueta historial",
            description="Texto para la sección de historial en el mensaje de revisión",
            option_type=ConfigOptionType.STRING,
            default="Historial",
            max_length=50,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_AWAITING_SCREENSHOTS,
            name="Estado: Esperando capturas",
            description="Texto del estado cuando se espera que el usuario envíe capturas",
            option_type=ConfigOptionType.STRING,
            default="⏳ **Estado:** Esperando capturas de pantalla...",
            max_length=200,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_PENDING_REVIEW,
            name="Estado: Pendiente de revisión",
            description="Texto del estado cuando las capturas están listas para revisión",
            option_type=ConfigOptionType.STRING,
            default="🔍 **Estado:** Pendiente de revisión",
            max_length=200,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_READY_FOR_APPROVAL,
            name="Estado: Listo para aprobar",
            description=(
                "Texto cuando las comprobaciones automáticas pasan pero requiere "
                "aprobación manual. Usa {roles} para mencionar los roles que pueden aprobar."
            ),
            option_type=ConfigOptionType.STRING,
            default="✅ **Estado:** Listo para aprobar - {roles}",
            max_length=300,
            placeholders=["roles"],
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_APPROVED,
            name="Estado: Aprobado",
            description="Texto del estado cuando la verificación fue aprobada",
            option_type=ConfigOptionType.STRING,
            default="✅ **Estado:** Aprobado por {moderator}",
            max_length=200,
            placeholders=["moderator"],
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_REJECTED,
            name="Estado: Rechazado",
            description="Texto del estado cuando la verificación fue rechazada",
            option_type=ConfigOptionType.STRING,
            default="❌ **Estado:** Rechazado por {moderator}\n**Motivo:** {reason}",
            max_length=200,
            placeholders=["moderator", "reason"],
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_CANCELLED,
            name="Estado: Cancelado",
            description="Texto del estado cuando la verificación fue cancelada",
            option_type=ConfigOptionType.STRING,
            default="🚫 **Estado:** Cancelado (el usuario salió del servidor)",
            max_length=200,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_WRONG_CAPTURES,
            name="Rechazo: Capturas incorrectas",
            description="Motivo cuando las capturas son incorrectas o ilegibles (error API 422)",
            option_type=ConfigOptionType.STRING,
            default="Capturas incorrectas o ilegibles",
            max_length=200,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_NAME_MISMATCH,
            name="Rechazo: Nombre no coincide",
            description="Motivo cuando el nombre del juego no coincide con Discord",
            option_type=ConfigOptionType.STRING,
            default="Nombre de usuario no coincide",
            max_length=200,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_HAS_REGIMENT,
            name="Rechazo: Tiene regimiento",
            description="Motivo cuando el usuario ya pertenece a un regimiento",
            option_type=ConfigOptionType.STRING,
            default="El usuario ya pertenece a un regimiento",
            max_length=200,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_TIME_DIFF,
            name="Rechazo: Captura antigua",
            description="Motivo cuando la captura es demasiado antigua",
            option_type=ConfigOptionType.STRING,
            default="Captura demasiado antigua",
            max_length=200,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_WRONG_SHARD,
            name="Rechazo: Shard incorrecto",
            description="Motivo cuando el shard es incorrecto. Usa {shard} para el esperado",
            option_type=ConfigOptionType.STRING,
            default="Shard incorrecto, debe ser {shard}",
            max_length=200,
            placeholders=["shard"],
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_WRONG_FACTION,
            name="Rechazo: Facción incorrecta",
            description="Motivo cuando la facción es incorrecta",
            option_type=ConfigOptionType.STRING,
            default="Facción incorrecta",
            max_length=200,
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
            description="Texto de la opción para escribir un motivo personalizado",
            option_type=ConfigOptionType.STRING,
            default="Otro motivo...",
            max_length=100,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_OTHER_DESCRIPTION,
            name="Descripción 'Otro motivo'",
            description="Descripción de la opción para escribir un motivo personalizado",
            option_type=ConfigOptionType.STRING,
            default="Escribir un motivo personalizado",
            max_length=100,
            group="Panel de moderación",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_MODAL_TITLE,
            name="Título modal de rechazo",
            description="Título del modal para escribir un motivo personalizado",
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
            default="Explica por que se rechaza la verificación...",
            max_length=100,
            group="Panel de moderación",
        ),
        # ===== 5. MENSAJES AL USUARIO =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_STARTED_MESSAGE,
            name="Verificación iniciada",
            description="Mensaje mostrado al usuario cuando inicia la verificación",
            option_type=ConfigOptionType.STRING,
            default="Revisa tus mensajes directos para continuar con la verificación.",
            max_length=500,
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.SCREENSHOTS_RECEIVED_MESSAGE,
            name="Capturas recibidas",
            description="Mensaje de confirmación cuando el usuario envía las capturas",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "Tus capturas han sido recibidas correctamente. "
                "Un moderador revisará tu solicitud pronto."
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
                "**Verificación rechazada**\n\n"
                "Tu verificación en **{server_name}** ha sido rechazada.\n"
                "**Motivo:** {reason}\n\n"
                "Puedes intentarlo de nuevo si lo deseas."
            ),
            max_length=2000,
            placeholders=["username", "server_name", "verification_type", "reason"],
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.WRONG_IMAGES_MESSAGE,
            name="Error: imágenes incorrectas",
            description="Mensaje cuando no se envían exactamente 2 imágenes",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "Debes enviar exactamente **2 capturas de pantalla** "
                "en el mismo mensaje. Por favor, inténtalo de nuevo."
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
                "Por favor, habilita los DMs de miembros del servidor e inténtalo de nuevo."
            ),
            max_length=1000,
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.ALREADY_PENDING_MESSAGE,
            name="Error: verificación pendiente",
            description="Mensaje cuando el usuario ya tiene una verificación pendiente",
            option_type=ConfigOptionType.TEXTAREA,
            default="Ya tienes una solicitud de verificación pendiente. Por favor, espera.",
            max_length=1000,
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.ALREADY_VERIFIED_MESSAGE,
            name="Error: ya verificado",
            description="Mensaje cuando el usuario ya tiene los roles de verificación",
            option_type=ConfigOptionType.STRING,
            default="Ya tienes los roles de verificación. No necesitas verificarte de nuevo.",
            max_length=500,
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_DISABLED_MESSAGE,
            name="Error: verificación deshabilitada",
            description="Mensaje mostrado cuando la verificación no está configurada",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "⚠️ **Verificación no disponible**\n\n"
                "La verificación está temporalmente deshabilitada."
                "Por favor, contacta a un administrador."
            ),
            max_length=2000,
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.REQUEST_NOT_FOUND_MESSAGE,
            name="Error: solicitud no encontrada",
            description="Mensaje cuando no se encuentra la solicitud de verificación",
            option_type=ConfigOptionType.STRING,
            default="Error: No se encontró tu solicitud de verificación.",
            max_length=500,
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.NO_PENDING_VERIFICATION_MESSAGE,
            name="Error: sin verificación activa",
            description="Mensaje cuando el usuario envía un DM sin tener verificación en curso",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "No tienes ninguna verificación en curso. "
                "Si deseas verificarte, usa el panel de verificación en el servidor."
            ),
            max_length=1000,
            group="Mensajes al usuario",
        ),
        ConfigOption(
            key=ConfigKey.PENDING_IN_OTHER_SERVER_MESSAGE,
            name="Error: verificación en otro servidor",
            description="Mensaje cuando el usuario tiene verificación pendiente en otro servidor",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "Ya tienes una verificación en curso en otro servidor. "
                "Debes completarla o esperar a que sea procesada antes de iniciar otra."
            ),
            max_length=1000,
            group="Mensajes al usuario",
        ),
        # ===== 6. MENSAJES DE MODERACIÓN =====
        ConfigOption(
            key=ConfigKey.MOD_APPROVED_CONFIRMATION,
            name="Confirmación de aprobación",
            description="Mensaje mostrado al moderador al aprobar",
            option_type=ConfigOptionType.STRING,
            default="Verificación aprobada para {username}.",
            max_length=500,
            placeholders=["username"],
            group="Mensajes de moderación",
        ),
        ConfigOption(
            key=ConfigKey.MOD_REJECTED_CONFIRMATION,
            name="Confirmación de rechazo",
            description="Mensaje mostrado al moderador al rechazar",
            option_type=ConfigOptionType.STRING,
            default="Verificación rechazada para {username}.",
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
            default="No tienes permisos para aprobar verificaciónes.",
            max_length=500,
            group="Mensajes de moderación",
        ),
        ConfigOption(
            key=ConfigKey.NO_PERMISSION_REJECT_MESSAGE,
            name="Error: sin permisos para rechazar",
            description="Mensaje cuando el moderador no tiene permisos para rechazar",
            option_type=ConfigOptionType.STRING,
            default="No tienes permisos para rechazar verificaciónes.",
            max_length=500,
            group="Mensajes de moderación",
        ),
        # ===== 7. API DE VERIFICACIÓN =====
        # Note: API URL and Key are in global settings (verification.api_url, api_key)
        ConfigOption(
            key=ConfigKey.VERIFICATION_FACTION,
            name="Facción requerida",
            description="Facción que deben tener los usuarios para aprobar verificación",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=[
                ("Colonial", "colonial"),
                ("Warden", "wardens"),
            ],
            default="",
            group="API de Verificación",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_SHARD,
            name="Shard requerido",
            description="Shard que deben tener los usuarios para aprobar verificación",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=[
                ("ABLE", "ABLE"),
                ("CHARLIE", "CHARLIE"),
            ],
            default="",
            group="API de Verificación",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_TIME_DIFF,
            name="Diferencia de tiempo máxima (días)",
            description=(
                "Máxima diferencia entre tiempo de juego y tiempo actual (0 para desactivar)"
            ),
            option_type=ConfigOptionType.INTEGER,
            default=0,
            min_value=0,
            max_value=999,
            group="API de Verificación",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_AUTOMATIC,
            name="Procesamiento automático",
            description="Aprobar/rechazar automáticamente según las reglas configuradas",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=[
                ("Ninguno", AutoProcessMode.NONE),
                ("Sólo rechazos", AutoProcessMode.REJECT_ONLY),
                ("Sólo aceptaciones", AutoProcessMode.APPROVE_ONLY),
                ("Ambos", AutoProcessMode.BOTH),
            ],
            default=AutoProcessMode.NONE,
            group="API de Verificación",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_MATCH_NAME,
            name="Verificar nombre",
            description="Modo de comparación entre el nombre de Discord y el nombre del juego",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=[
                ("No comprobar", NameMatchMode.NONE),
                ("Exacto", NameMatchMode.EXACT),
                ("Debe contener", NameMatchMode.CONTAINS),
            ],
            default=NameMatchMode.NONE,
            group="API de Verificación",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_VALID_REGIMENT,
            name="Regimiento válido",
            description=(
                "ID del regimiento permitido para verificación normal. "
                "Usar el contenido completo entre corchetes "
                "(ej: para '[7-HP#8707] 7th Hispanic Platoon' usar '7-HP#8707'). "
                "Si está vacío, se rechaza cualquier usuario con regimiento."
            ),
            option_type=ConfigOptionType.STRING,
            default="",
            max_length=50,
            group="API de Verificación",
        ),
        ConfigOption(
            key=ConfigKey.PLAYER_INFO_TEMPLATE,
            name="Plantilla de información del jugador",
            description=(
                "Plantilla para mostrar la información del jugador en el mensaje de moderación"
            ),
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Información del jugador:**\n"
                "Nombre: {name}\n"
                "Regimiento: {regiment}\n"
                "Nivel: {level}\n"
                "Facción: {faction}\n"
                "Shard: {shard}\n"
                "Tiempo de juego: {time}\n"
                "Guerra: {war}\n"
                "Tiempo actual: {war_time}"
            ),
            max_length=2000,
            placeholders=[
                "name",
                "regiment",
                "level",
                "faction",
                "shard",
                "time",
                "war",
                "war_time",
            ],
            group="API de Verificación",
        ),
    ],
)
