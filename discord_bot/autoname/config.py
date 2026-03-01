"""Configuracion y schema del cog de autoname."""

from enum import StrEnum

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption

COG_NAME = "autoname"


class ConfigKey(StrEnum):
    """Claves de configuracion para el cog de autoname."""

    REQUIRED_ROLES = "required_roles"
    ROLE_TAGS = "role_tags"
    ROLE_PREFIXES = "role_prefixes"
    TAG_FORMAT = "tag_format"
    SYNC_INTERVAL = "sync_interval"
    LOG_CHANNEL = "log_channel"
    LOG_MESSAGE_SUCCESS = "log_message_success"
    LOG_MESSAGE_NO_PERMS = "log_message_no_perms"


AUTONAME_CONFIG_SCHEMA = CogConfigSchema(
    cog_name=COG_NAME,
    display_name="Autoname",
    description="Formateo automatico de nicknames segun roles del servidor",
    icon="🏷️",
    options=[
        ConfigOption(
            key=ConfigKey.REQUIRED_ROLES,
            name="Roles requeridos",
            description=(
                "Solo se modificaran los nicknames de miembros que tengan alguno de estos roles. "
                "Dejar vacio para procesar todos los miembros."
            ),
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.ROLE_TAGS,
            name="Etiquetas por rol",
            description="Lista ordenada de roles y sus etiquetas. El primer rol coincidente gana.",
            option_type=ConfigOptionType.TABLE,
            default=[],
            columns=[
                {
                    "key": "role_id",
                    "name": "Rol",
                    "type": "role",
                    "required": True,
                },
                {
                    "key": "tag",
                    "name": "Etiqueta",
                    "type": "string",
                    "max_length": 10,
                    "required": True,
                    "placeholder": "CAP",
                },
            ],
        ),
        ConfigOption(
            key=ConfigKey.ROLE_PREFIXES,
            name="Prefijos por rol",
            description=(
                "Lista ordenada de roles y sus prefijos. El primer rol coincidente gana.\n"
                "Sugerencias: ★ ☆ ◆ ◇ ● ○ ■ □ ▲ △ ♦ ♢ ✦ ✧ ⬥ ⬦ ◈ ❖ ✪ ⚜"
            ),
            option_type=ConfigOptionType.TABLE,
            default=[],
            columns=[
                {
                    "key": "role_id",
                    "name": "Rol",
                    "type": "role",
                    "required": True,
                },
                {
                    "key": "prefix",
                    "name": "Prefijo",
                    "type": "string",
                    "max_length": 5,
                    "required": True,
                    "placeholder": "★",
                },
            ],
        ),
        ConfigOption(
            key=ConfigKey.TAG_FORMAT,
            name="Formato de etiqueta",
            description="Formato del tag. Usa {tag} como placeholder. Ejemplo: [ABC | {tag}]",
            option_type=ConfigOptionType.STRING,
            default="[ABC | {tag}]",
            max_length=50,
        ),
        ConfigOption(
            key=ConfigKey.SYNC_INTERVAL,
            name="Intervalo de sincronizacion (minutos)",
            description="Frecuencia de sincronizacion periodica de nicknames (0 para desactivar)",
            option_type=ConfigOptionType.INTEGER,
            default=30,
            min_value=0,
            max_value=1440,
        ),
        ConfigOption(
            key=ConfigKey.LOG_CHANNEL,
            name="Canal de logs",
            description="Canal donde se enviaran los logs de cambios de nickname",
            option_type=ConfigOptionType.CHANNEL,
            default=None,
        ),
        ConfigOption(
            key=ConfigKey.LOG_MESSAGE_SUCCESS,
            name="Mensaje de cambio exitoso",
            description=(
                "Mensaje cuando se cambia un nickname. "
                "Placeholders: {old_name}, {new_name}. Dejar vacio para no enviar."
            ),
            option_type=ConfigOptionType.STRING,
            default="Nickname cambiado de **{old_name}** a **{new_name}**",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.LOG_MESSAGE_NO_PERMS,
            name="Mensaje sin permisos",
            description=(
                "Mensaje cuando no se puede cambiar un nickname por permisos. "
                "Placeholder: {name}. Dejar vacio para no enviar."
            ),
            option_type=ConfigOptionType.STRING,
            default="No se pudo cambiar el nickname de **{name}** (sin permisos)",
            max_length=200,
        ),
    ],
)
