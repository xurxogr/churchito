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
        # ===== 1. GENERAL =====
        ConfigOption(
            key=ConfigKey.COMMAND_CHANNEL,
            name="Stockpile channel",
            description=(
                "Channel for stockpile commands and notifications. Leave empty to disable the cog."
            ),
            option_type=ConfigOptionType.CHANNEL,
            default=None,
            group="General",
        ),
        ConfigOption(
            key=ConfigKey.ADD_COMMAND_NAME,
            name="Add command name",
            description="Name for the command to add stockpiles (without slash)",
            option_type=ConfigOptionType.STRING,
            default="stockpile_add",
            max_length=32,
            group="General",
        ),
        ConfigOption(
            key=ConfigKey.SHOW_COMMAND_NAME,
            name="Show command name",
            description="Name for the command to show stockpiles (without slash)",
            option_type=ConfigOptionType.STRING,
            default="stockpile_show",
            max_length=32,
            group="General",
        ),
        ConfigOption(
            key=ConfigKey.DELETE_COMMAND_NAME,
            name="Delete command name",
            description="Name for the command to delete stockpiles (without slash)",
            option_type=ConfigOptionType.STRING,
            default="stockpile_delete",
            max_length=32,
            group="General",
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
        # ===== 3. ADD COMMAND =====
        ConfigOption(
            key=ConfigKey.ADD_SUCCESS_TEXT,
            name="Response to user",
            description=(
                "Ephemeral message shown to the user after adding a stockpile. "
                "Leave empty to not send any message."
            ),
            option_type=ConfigOptionType.TEXTAREA,
            default=("Stockpile **{name}** added at **{hex}** - **{city}**\nCode: `{code}`"),
            max_length=1000,
            placeholders=[
                "name",
                "hex",
                "city",
                "code",
                "roles",
                "roles_mention",
                "creator",
                "creator_mention",
                "created_at",
                "created_at_relative",
            ],
            group="Add Command",
        ),
        ConfigOption(
            key=ConfigKey.ADD_NOTIFICATION_TEXT,
            name="Channel notification",
            description=(
                "Embed sent to the channel when a stockpile is added. Leave empty to disable."
            ),
            option_type=ConfigOptionType.EMBED,
            default={
                "sections": [
                    {
                        "type": "text",
                        "content": ("📦 **{name}** added at {hex} - {city} by {creator_mention}"),
                    }
                ],
            },
            placeholders=[
                "name",
                "hex",
                "city",
                "code",
                "roles",
                "roles_mention",
                "creator",
                "creator_mention",
                "created_at",
                "created_at_relative",
            ],
            group="Add Command",
        ),
        # ===== 4. SHOW COMMAND =====
        ConfigOption(
            key=ConfigKey.SHOW_HEADER_TEXT,
            name="Location header",
            description=(
                "Header shown before stockpiles at each location. "
                "Leave empty to show stockpiles without location grouping."
            ),
            option_type=ConfigOptionType.STRING,
            default="**{hex} - {city}** ({count})",
            max_length=200,
            placeholders=["hex", "city", "count"],
            group="Show Command",
        ),
        ConfigOption(
            key=ConfigKey.SHOW_LOCATION_EMBED,
            name="Stockpile embed",
            description="Embed shown for each stockpile. One embed is sent per stockpile.",
            option_type=ConfigOptionType.EMBED,
            default={
                "description": "**{name}**: `{code}` (by {creator_mention})",
            },
            placeholders=[
                "hex",
                "city",
                "name",
                "code",
                "roles",
                "roles_mention",
                "creator",
                "creator_mention",
                "created_at",
                "created_at_relative",
            ],
            group="Show Command",
        ),
        ConfigOption(
            key=ConfigKey.SHOW_EMPTY_EMBED,
            name="Empty message",
            description="Embed shown when no stockpiles are found at the location",
            option_type=ConfigOptionType.EMBED,
            default={
                "title": "No stockpiles found",
                "description": "No stockpiles found at **{hex}** - **{city}**",
            },
            placeholders=["hex", "city"],
            group="Show Command",
        ),
        # ===== 5. DELETE COMMAND =====
        ConfigOption(
            key=ConfigKey.DELETE_SUCCESS_TEXT,
            name="Response to user",
            description=(
                "Ephemeral message shown to the user after deleting a stockpile. "
                "Leave empty to not send any message."
            ),
            option_type=ConfigOptionType.STRING,
            default="Stockpile **{name}** at **{hex}** - **{city}** has been deleted.",
            max_length=200,
            placeholders=[
                "name",
                "hex",
                "city",
                "code",
                "roles",
                "roles_mention",
                "creator",
                "creator_mention",
                "created_at",
                "created_at_relative",
            ],
            group="Delete Command",
        ),
        ConfigOption(
            key=ConfigKey.DELETE_NOTIFICATION_TEXT,
            name="Channel notification",
            description=(
                "Embed sent to the channel when a stockpile is deleted. Leave empty to disable."
            ),
            option_type=ConfigOptionType.EMBED,
            default={
                "sections": [
                    {
                        "type": "text",
                        "content": (
                            "🗑️ **{name}** at {hex} - {city} deleted by {deleted_by_mention}"
                        ),
                    }
                ],
            },
            placeholders=[
                "name",
                "hex",
                "city",
                "code",
                "roles",
                "roles_mention",
                "creator",
                "creator_mention",
                "created_at",
                "created_at_relative",
                "deleted_by",
                "deleted_by_mention",
            ],
            group="Delete Command",
        ),
        # ===== 6. PINNED MESSAGE =====
        ConfigOption(
            key=ConfigKey.PINNED_HEADER_TEXT,
            name="Location header",
            description=(
                "Header template for each location in the pinned message. "
                "Leave empty to disable pinned message feature."
            ),
            option_type=ConfigOptionType.TEXTAREA,
            default=None,
            max_length=500,
            placeholders=["hex", "city", "count"],
            group="Pinned Message",
        ),
        ConfigOption(
            key=ConfigKey.PINNED_ITEM_TEXT,
            name="Stockpile item",
            description=(
                "Template for each stockpile in the pinned message. "
                "Leave empty to disable pinned message feature."
            ),
            option_type=ConfigOptionType.TEXTAREA,
            default=None,
            max_length=500,
            placeholders=[
                "name",
                "code",
                "hex",
                "city",
                "roles",
                "roles_mention",
                "creator",
                "creator_mention",
                "created_at",
                "created_at_relative",
            ],
            group="Pinned Message",
        ),
        # ===== 7. ERROR MESSAGES =====
        ConfigOption(
            key=ConfigKey.NO_PERMISSION_TEXT,
            name="No permission",
            description="Message when user lacks permission to perform an action",
            option_type=ConfigOptionType.STRING,
            default="You don't have permission to perform this action.",
            max_length=200,
            group="Error Messages",
        ),
        ConfigOption(
            key=ConfigKey.NOT_FOUND_TEXT,
            name="Not found",
            description="Message when the stockpile is not found",
            option_type=ConfigOptionType.STRING,
            default="Stockpile not found.",
            max_length=200,
            group="Error Messages",
        ),
        ConfigOption(
            key=ConfigKey.INVALID_CODE_TEXT,
            name="Invalid code",
            description="Message when code format is invalid (must be 6 digits)",
            option_type=ConfigOptionType.STRING,
            default="Code must be exactly 6 digits.",
            max_length=200,
            group="Error Messages",
        ),
        ConfigOption(
            key=ConfigKey.INVALID_ROLES_TEXT,
            name="Invalid roles",
            description="Message when selected roles are not in the allowed view roles list",
            option_type=ConfigOptionType.STRING,
            default="One or more selected roles are not in the allowed view roles list.",
            max_length=200,
            group="Error Messages",
        ),
        ConfigOption(
            key=ConfigKey.WRONG_CHANNEL_TEXT,
            name="Wrong channel",
            description="Message when command is used in the wrong channel",
            option_type=ConfigOptionType.STRING,
            default="This command can only be used in {channel}.",
            max_length=200,
            placeholders=["channel"],
            group="Error Messages",
        ),
    ],
)
