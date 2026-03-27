"""Configuration and schema for the autoname cog."""

from enum import StrEnum

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption

COG_NAME = "autoname"


class ConfigKey(StrEnum):
    """Configuration keys for the autoname cog."""

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
    description="Automatic nickname formatting based on server roles",
    icon="🏷️",
    options=[
        ConfigOption(
            key=ConfigKey.REQUIRED_ROLES,
            name="Required roles",
            description=(
                "Only nicknames of members with one of these roles will be modified. "
                "Leave empty to process all members."
            ),
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.ROLE_TAGS,
            name="Role tags",
            description="Ordered list of roles and their tags. First matching role wins.",
            option_type=ConfigOptionType.TABLE,
            default=[],
            columns=[
                {
                    "key": "role_id",
                    "name": "Role",
                    "type": "role",
                    "required": True,
                },
                {
                    "key": "tag",
                    "name": "Tag",
                    "type": "string",
                    "max_length": 10,
                    "required": True,
                    "placeholder": "CAP",
                },
            ],
        ),
        ConfigOption(
            key=ConfigKey.ROLE_PREFIXES,
            name="Role prefixes",
            description=(
                "Ordered list of roles and their prefixes. First matching role wins.\n"
                "Suggestions: ★ ☆ ◆ ◇ ● ○ ■ □ ▲ △ ♦ ♢ ✦ ✧ ⬥ ⬦ ◈ ❖ ✪ ⚜"
            ),
            option_type=ConfigOptionType.TABLE,
            default=[],
            columns=[
                {
                    "key": "role_id",
                    "name": "Role",
                    "type": "role",
                    "required": True,
                },
                {
                    "key": "prefix",
                    "name": "Prefix",
                    "type": "string",
                    "max_length": 5,
                    "required": True,
                    "placeholder": "★",
                },
            ],
        ),
        ConfigOption(
            key=ConfigKey.TAG_FORMAT,
            name="Tag format",
            description="Tag format. Use {tag} as placeholder. Example: [ABC | {tag}]",
            option_type=ConfigOptionType.STRING,
            default="[ABC | {tag}]",
            max_length=50,
        ),
        ConfigOption(
            key=ConfigKey.SYNC_INTERVAL,
            name="Sync interval (minutes)",
            description="Periodic nickname sync frequency (0 to disable)",
            option_type=ConfigOptionType.INTEGER,
            default=30,
            min_value=0,
            max_value=1440,
        ),
        ConfigOption(
            key=ConfigKey.LOG_CHANNEL,
            name="Log channel",
            description="Channel where nickname change logs will be sent",
            option_type=ConfigOptionType.CHANNEL,
            default=None,
        ),
        ConfigOption(
            key=ConfigKey.LOG_MESSAGE_SUCCESS,
            name="Success change message",
            description=(
                "Message when a nickname is changed. "
                "Placeholders: {old_name}, {new_name}. Leave empty to not send."
            ),
            option_type=ConfigOptionType.STRING,
            default="Nickname changed from **{old_name}** to **{new_name}**",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.LOG_MESSAGE_NO_PERMS,
            name="No permission message",
            description=(
                "Message when a nickname cannot be changed due to permissions. "
                "Placeholder: {name}. Leave empty to not send."
            ),
            option_type=ConfigOptionType.STRING,
            default="Could not change nickname of **{name}** (no permission)",
            max_length=200,
        ),
    ],
)
