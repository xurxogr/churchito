"""Configuration and schema for the stockpile cog."""

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.stockpile.enums import ConfigKey

COG_NAME = "stockpile"

STOCKPILE_CONFIG_SCHEMA = CogConfigSchema(
    cog_name=COG_NAME,
    display_name="Stockpile",
    description="Manage stockpile information with location and access codes",
    icon="📦",
    options=[
        # ===== 1. COMMAND NAMES =====
        ConfigOption(
            key=ConfigKey.ADD_COMMAND_NAME,
            name="Add command name",
            description="Name for the command to add stockpiles (without slash)",
            option_type=ConfigOptionType.STRING,
            default="stockpile_add",
            max_length=32,
            group="Commands",
        ),
        ConfigOption(
            key=ConfigKey.SHOW_COMMAND_NAME,
            name="Show command name",
            description="Name for the command to show stockpiles (without slash)",
            option_type=ConfigOptionType.STRING,
            default="stockpile_show",
            max_length=32,
            group="Commands",
        ),
        ConfigOption(
            key=ConfigKey.DELETE_COMMAND_NAME,
            name="Delete command name",
            description="Name for the command to delete stockpiles (without slash)",
            option_type=ConfigOptionType.STRING,
            default="stockpile_delete",
            max_length=32,
            group="Commands",
        ),
        ConfigOption(
            key=ConfigKey.COMMAND_CHANNEL,
            name="Stockpile channel",
            description=(
                "Channel for stockpile commands and notifications. Leave empty to disable the cog."
            ),
            option_type=ConfigOptionType.CHANNEL,
            default=None,
            group="Commands",
        ),
        # ===== 2. PERMISSIONS =====
        ConfigOption(
            key=ConfigKey.ADD_ROLES,
            name="Roles that can add stockpiles",
            description="Only users with these roles can add new stockpiles",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Permissions",
        ),
        ConfigOption(
            key=ConfigKey.DELETE_ROLES,
            name="Roles that can delete stockpiles",
            description="Only users with these roles can delete stockpiles",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Permissions",
        ),
        ConfigOption(
            key=ConfigKey.ALLOWED_VIEW_ROLES,
            name="Allowed view roles",
            description=(
                "Roles that can be assigned to stockpiles for viewing. "
                "When adding a stockpile, only these roles can be selected."
            ),
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Permissions",
        ),
        # ===== 3. MESSAGES =====
        ConfigOption(
            key=ConfigKey.ADD_SUCCESS_TEXT,
            name="Add success message",
            description="Message shown when a stockpile is added successfully",
            option_type=ConfigOptionType.TEXTAREA,
            default=("Stockpile **{name}** added at **{hex}** - **{city}**\nCode: `{code}`"),
            max_length=1000,
            placeholders=["name", "hex", "city", "code"],
            group="Messages",
        ),
        ConfigOption(
            key=ConfigKey.SHOW_HEADER_TEXT,
            name="Show header message",
            description="Header text when displaying stockpiles",
            option_type=ConfigOptionType.STRING,
            default="**Stockpiles at {hex} - {city}** ({count})",
            max_length=200,
            placeholders=["hex", "city", "count"],
            group="Messages",
        ),
        ConfigOption(
            key=ConfigKey.SHOW_ITEM_TEXT,
            name="Show item message",
            description="Text for each stockpile in the list",
            option_type=ConfigOptionType.TEXTAREA,
            default="**{name}**: `{code}` (by <@{creator}>)",
            max_length=500,
            placeholders=["name", "code", "hex", "city", "roles", "creator", "created_at"],
            group="Messages",
        ),
        ConfigOption(
            key=ConfigKey.SHOW_EMPTY_TEXT,
            name="Show empty message",
            description="Message when no stockpiles are found",
            option_type=ConfigOptionType.STRING,
            default="No stockpiles found at **{hex}** - **{city}**",
            max_length=200,
            placeholders=["hex", "city"],
            group="Messages",
        ),
        ConfigOption(
            key=ConfigKey.DELETE_SUCCESS_TEXT,
            name="Delete success message",
            description="Message shown when a stockpile is deleted",
            option_type=ConfigOptionType.STRING,
            default="Stockpile **{name}** at **{hex}** - **{city}** has been deleted.",
            max_length=200,
            placeholders=["name", "hex", "city"],
            group="Messages",
        ),
        ConfigOption(
            key=ConfigKey.NO_PERMISSION_TEXT,
            name="No permission message",
            description="Message when user lacks permission",
            option_type=ConfigOptionType.STRING,
            default="You don't have permission to perform this action.",
            max_length=200,
            group="Messages",
        ),
        ConfigOption(
            key=ConfigKey.NOT_FOUND_TEXT,
            name="Not found message",
            description="Message when stockpile is not found",
            option_type=ConfigOptionType.STRING,
            default="Stockpile not found.",
            max_length=200,
            group="Messages",
        ),
        ConfigOption(
            key=ConfigKey.INVALID_CODE_TEXT,
            name="Invalid code message",
            description="Message when code format is invalid",
            option_type=ConfigOptionType.STRING,
            default="Code must be exactly 6 digits.",
            max_length=200,
            group="Messages",
        ),
        ConfigOption(
            key=ConfigKey.INVALID_ROLES_TEXT,
            name="Invalid roles message",
            description="Message when selected roles are not allowed",
            option_type=ConfigOptionType.STRING,
            default="One or more selected roles are not in the allowed view roles list.",
            max_length=200,
            group="Messages",
        ),
        ConfigOption(
            key=ConfigKey.WRONG_CHANNEL_TEXT,
            name="Wrong channel message",
            description="Message when command is used in wrong channel",
            option_type=ConfigOptionType.STRING,
            default="This command can only be used in {channel}.",
            max_length=200,
            placeholders=["channel"],
            group="Messages",
        ),
        # ===== 4. NOTIFICATIONS =====
        ConfigOption(
            key=ConfigKey.ADD_NOTIFICATION_TEXT,
            name="Add notification message",
            description=(
                "Public message sent to notification channel when a stockpile is added. "
                "Leave empty to disable."
            ),
            option_type=ConfigOptionType.TEXTAREA,
            default="📦 **{name}** added at {hex} - {city} by {creator}",
            max_length=1000,
            placeholders=["name", "hex", "city", "code", "roles", "creator"],
            group="Notifications",
        ),
        ConfigOption(
            key=ConfigKey.DELETE_NOTIFICATION_TEXT,
            name="Delete notification message",
            description=(
                "Public message sent to notification channel when a stockpile is deleted. "
                "Leave empty to disable."
            ),
            option_type=ConfigOptionType.TEXTAREA,
            default="🗑️ **{name}** at {hex} - {city} deleted by {deleted_by}",
            max_length=1000,
            placeholders=["name", "hex", "city", "deleted_by"],
            group="Notifications",
        ),
    ],
)
