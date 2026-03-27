"""Purge cog configuration and schema."""

import discord

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.purge.enums import ConfigKey

COG_NAME = "purge"

# Color name to button style mapping
BUTTON_STYLES = {
    "blurple": discord.ButtonStyle.primary,
    "grey": discord.ButtonStyle.secondary,
    "green": discord.ButtonStyle.success,
    "red": discord.ButtonStyle.danger,
}

# Default template for moderation message
DEFAULT_MOD_MESSAGE = """**{purge_type}**

Status: {status}
Required authorizations: {required_reactions}
Execution date: {date}

Authorized by: {authorized_by}
Cancellations: {cancellations}

React to the button to authorize the purge."""

# Default template for user message (war purge)
DEFAULT_USER_MESSAGE = """**ACTIVE PURGE**

A purge has been initiated. The following roles are affected:
{roles}

Execution date: {date}

React to the button to confirm your stay and get the {reaction_role} role."""

# Default template for user message (global purge)
DEFAULT_GLOBAL_USER_MESSAGE = """**ACTIVE GLOBAL PURGE**

A global purge has been initiated that affects **all members**.

Execution date: {date}

React to the button to confirm your stay and get the {reaction_role} role."""


PURGE_CONFIG_SCHEMA = CogConfigSchema(
    cog_name="purge",
    display_name="Purge",
    description="Purge system for member activity management",
    icon="🗡️",
    toggleable=True,
    options=[
        # ====================================================================
        # COMMON - Moderation
        # ====================================================================
        ConfigOption(
            key=ConfigKey.MOD_CHANNEL,
            name="Moderation channel",
            description="Channel where moderators activate and manage purges",
            option_type=ConfigOptionType.CHANNEL,
            section="Common",
            group="Moderation",
        ),
        ConfigOption(
            key=ConfigKey.MOD_MESSAGE_TEMPLATE,
            name="Authorization message template",
            description="Message displayed when a purge is initiated. "
            "Dynamically updated with status and authorizer list.",
            option_type=ConfigOptionType.TEXTAREA,
            section="Common",
            group="Moderation",
            default=DEFAULT_MOD_MESSAGE,
            max_length=2000,
            placeholders=[
                "purge_type",
                "status",
                "authorized_by",
                "cancellations",
                "required_reactions",
                "date",
            ],
        ),
        ConfigOption(
            key=ConfigKey.MOD_BUTTON_COLOR,
            name="Authorization button color",
            description="Color of the button moderators use to authorize",
            option_type=ConfigOptionType.TEXT_CHOICE,
            section="Common",
            group="Moderation",
            default="green",
            choices=[
                ("Blue", "blurple"),
                ("Grey", "grey"),
                ("Green", "green"),
                ("Red", "red"),
            ],
        ),
        ConfigOption(
            key=ConfigKey.MOD_BUTTON_TEXT,
            name="Authorization button text",
            description="Text that appears on the button (can include emojis)",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Moderation",
            default="🔑 Authorize purge",
            max_length=80,
        ),
        ConfigOption(
            key=ConfigKey.MOD_REQUIRED_REACTIONS,
            name="Required reactions",
            description="Number of moderators that must authorize to activate the purge",
            option_type=ConfigOptionType.INTEGER,
            section="Common",
            group="Moderation",
            default=2,
            min_value=1,
            max_value=10,
        ),
        ConfigOption(
            key=ConfigKey.MOD_REACTION_TIMEOUT,
            name="Time limit (minutes)",
            description="Minutes to get the required authorizations. 0 = no limit.",
            option_type=ConfigOptionType.INTEGER,
            section="Common",
            group="Moderation",
            default=1,
            min_value=0,
            max_value=1440,
        ),
        ConfigOption(
            key=ConfigKey.MOD_MESSAGE_RETENTION,
            name="Message retention (minutes)",
            description="Minutes the message remains after completion. 0 = permanent.",
            option_type=ConfigOptionType.INTEGER,
            section="Common",
            group="Moderation",
            default=0,
            min_value=0,
            max_value=1440,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STATUS_PENDING,
            name="Status: Pending",
            description="Text when waiting for more authorizations",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Moderation",
            default="⏳ Pending approval",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STATUS_AUTHORIZED,
            name="Status: Authorized",
            description="Text when required authorizations are obtained",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Moderation",
            default="✅ Authorized",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STATUS_EXPIRED,
            name="Status: Expired",
            description="Text when authorizations are not obtained in time",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Moderation",
            default="⌛ Expired",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STATUS_CANCEL_PENDING,
            name="Status: Cancel pending",
            description="Text when cancellation is initiated but votes are missing",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Moderation",
            default="🟡 Cancel pending",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STATUS_CANCELLED,
            name="Status: Cancelled",
            description="Text when the purge is cancelled",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Moderation",
            default="❌ Cancelled",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STATUS_EXECUTED,
            name="Status: Executed",
            description="Text when the purge is executed successfully",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Moderation",
            default="✅ Executed",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.MOD_STOP_BUTTON_TEXT,
            name="Stop button text",
            description="Text of the button to stop an active purge",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Moderation",
            default="🛑 Stop purge",
            max_length=80,
        ),
        ConfigOption(
            key=ConfigKey.MOD_ACTIVE_PURGE_TEXT,
            name="Message: Active purge",
            description="Message when trying to start another purge while one is active",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Moderation",
            default="There is already an active purge. Wait for it to finish or cancel it.",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.MOD_NO_PERMISSION_TEXT,
            name="Message: No permissions",
            description="Message when the user doesn't have the role to use the command",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Moderation",
            default="You don't have permission to execute this command.",
            max_length=200,
        ),
        # ====================================================================
        # COMMON - Users
        # ====================================================================
        ConfigOption(
            key=ConfigKey.USER_CHANNEL,
            name="User channel",
            description="Channel where users see the purge message and react",
            option_type=ConfigOptionType.CHANNEL,
            section="Common",
            group="Users",
        ),
        ConfigOption(
            key=ConfigKey.USER_BUTTON_COLOR,
            name="Confirmation button color",
            description="Color of the button users use to confirm",
            option_type=ConfigOptionType.TEXT_CHOICE,
            section="Common",
            group="Users",
            default="green",
            choices=[
                ("Blue", "blurple"),
                ("Grey", "grey"),
                ("Green", "green"),
                ("Red", "red"),
            ],
        ),
        ConfigOption(
            key=ConfigKey.USER_BUTTON_TEXT,
            name="Confirmation button text",
            description="Text of the button users press (can include emojis)",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Users",
            default="🛡️ Confirm stay",
            max_length=80,
        ),
        ConfigOption(
            key=ConfigKey.USER_REACTION_ROLE,
            name="Role on reaction",
            description="Role assigned to users when they react to the button",
            option_type=ConfigOptionType.ROLE,
            section="Common",
            group="Users",
        ),
        ConfigOption(
            key=ConfigKey.USER_FIRST_REACTION_TEXT,
            name="Message: First reaction",
            description="Message (ephemeral) when the user confirms for the first time",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Users",
            default="You have confirmed your stay. Thank you!",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.USER_REMOVED_REACTION_TEXT,
            name="Message: Confirmation withdrawn",
            description="Message (ephemeral) when the user withdraws their confirmation",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Users",
            default="You have withdrawn your confirmation.",
            max_length=200,
        ),
        # ====================================================================
        # COMMON - General
        # ====================================================================
        ConfigOption(
            key=ConfigKey.TEST_MODE,
            name="Test mode",
            description="Allows skipping minimum restrictions: "
            "only requires 1 authorization and executes in 2 minutes.",
            option_type=ConfigOptionType.BOOLEAN,
            section="Common",
            group="General",
            default=False,
        ),
        ConfigOption(
            key=ConfigKey.AUDIT_LEVEL,
            name="Audit level",
            description="0 = No messages, 1 = Titles only, 2 = All actions",
            option_type=ConfigOptionType.INTEGER,
            section="Common",
            group="General",
            default=1,
            min_value=0,
            max_value=2,
        ),
        ConfigOption(
            key=ConfigKey.LOG_CHANNEL,
            name="Log channel",
            description="Channel where purge logs will be sent. Leave empty to disable.",
            option_type=ConfigOptionType.CHANNEL,
            section="Common",
            group="General",
            default=None,
        ),
        ConfigOption(
            key=ConfigKey.LOG_CREATED,
            name="Log: Purge created",
            description="Placeholders: {user}, {purge_type}, {hours}, {scheduled_for}",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="General",
            default="Purge **{purge_type}** created by **{user}** - "
            "Execution: {scheduled_for} ({hours}h)",
            max_length=500,
        ),
        ConfigOption(
            key=ConfigKey.LOG_AUTHORIZED,
            name="Log: Authorization",
            description="Placeholders: {user}, {auth_count}, {required}",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="General",
            default="**{user}** authorized ({auth_count}/{required})",
            max_length=500,
        ),
        ConfigOption(
            key=ConfigKey.LOG_CANCELLED,
            name="Log: Cancellation",
            description="Placeholders: {user}",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="General",
            default="Cancelled by **{user}**",
            max_length=500,
        ),
        # ====================================================================
        # COMMON - Execution messages
        # ====================================================================
        ConfigOption(
            key=ConfigKey.EXEC_MSG_SIMULATION,
            name="Message: Test mode",
            description="Indicator at the beginning of logs when running in test mode",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Execution messages",
            default="🧪 **[TEST MODE]**",
            max_length=100,
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_INIT,
            name="Message: Purge start",
            description="Message when starting execution (level 1+)",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Execution messages",
            default="🔥 **Starting purge...**",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_CLEANING_ROLE,
            name="Message: Cleaning role",
            description="Message for each affected role (level 2). Placeholder: {role}",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Execution messages",
            default="🧹 Applying purge to role {role}...",
            max_length=200,
            placeholders=["role"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_USER_CLEANED,
            name="Message: User purged",
            description="Message for each purged user (level 2). Placeholder: {user}",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Execution messages",
            default="  ↳ 🧹 Purged: {user}",
            max_length=200,
            placeholders=["user"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_PROMOTIONS_START,
            name="Message: Promotions start",
            description="Message when starting promotions (level 1+)",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Execution messages",
            default="⬆️ **Applying promotions...**",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_PROMOTION_ROLE,
            name="Message: Role promotion",
            description="Message for each role promotion (level 2). "
            "Placeholders: {from_role}, {to_role}",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Execution messages",
            default="📈 Promoting {from_role} → {to_role}...",
            max_length=200,
            placeholders=["from_role", "to_role"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_USER_PROMOTED,
            name="Message: User promoted",
            description="Message for each promoted user (level 2). "
            "Placeholders: {user}, {from_role}, {to_role}",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Execution messages",
            default="  ↳ ⬆️ Promoted: {user} ({from_role} → {to_role})",
            max_length=200,
            placeholders=["user", "from_role", "to_role"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_PROMOTION_DEFAULT,
            name="Message: Role for non-affected",
            description="Message when applying role to users who confirmed without being "
            "in affected roles (level 2). Placeholder: {role}",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Execution messages",
            default="🏷️ Marking non-affected users ({role})...",
            max_length=200,
            placeholders=["role"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_USER_PROMOTED_DEFAULT,
            name="Message: Non-affected user",
            description="Message for each non-affected user receiving the role (level 2). "
            "Placeholders: {user}, {role}",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Execution messages",
            default="  ↳ 🏷️ Marked: {user} (→ {role})",
            max_length=200,
            placeholders=["user", "role"],
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_GLOBAL_REMOVE_START,
            name="Message: Global cleanup start",
            description="Message when starting global role removal (level 1+)",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Execution messages",
            default="🧹 **Removing global roles...**",
            max_length=200,
        ),
        ConfigOption(
            key=ConfigKey.EXEC_MSG_GLOBAL_REMOVE_USER,
            name="Message: Global cleanup user",
            description="Message for each user having global roles removed (level 2). "
            "Placeholders: {user}, {roles}",
            option_type=ConfigOptionType.STRING,
            section="Common",
            group="Execution messages",
            default="  ↳ 🧹 Roles removed: {user} ({roles})",
            max_length=200,
            placeholders=["user", "roles"],
        ),
        # ====================================================================
        # WAR END PURGE
        # ====================================================================
        ConfigOption(
            key=ConfigKey.WAR_COMMAND_NAME,
            name="Command name",
            description="Name of the slash command to start the war end purge",
            option_type=ConfigOptionType.STRING,
            section="Purge: War end",
            default="purge_war",
            max_length=32,
        ),
        ConfigOption(
            key=ConfigKey.WAR_DISPLAY_NAME,
            name="Display name",
            description="Name that appears in the moderation message (e.g.: 'War end')",
            option_type=ConfigOptionType.STRING,
            section="Purge: War end",
            default="War end purge",
            max_length=50,
        ),
        ConfigOption(
            key=ConfigKey.WAR_MESSAGE_TEMPLATE,
            name="User message template",
            description="Message users see when the purge is active. "
            "{date} shows date with dynamic Discord countdown.",
            option_type=ConfigOptionType.TEXTAREA,
            section="Purge: War end",
            default=DEFAULT_USER_MESSAGE,
            max_length=2000,
            placeholders=["roles", "date", "relative_date", "day", "reaction_role"],
        ),
        ConfigOption(
            key=ConfigKey.WAR_ADMIN_ROLES,
            name="Admin roles",
            description="Roles that can start and authorize the purge",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purge: War end",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.WAR_AFFECTED_ROLES,
            name="Affected roles",
            description="Roles whose members must confirm to stay or will be purged",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purge: War end",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.WAR_ROLES_TO_REMOVE,
            name="Roles to remove (purged)",
            description="Roles removed from purged members. Leave empty to remove all roles.",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purge: War end",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.WAR_ROLES_TO_ADD,
            name="Roles to assign (purged)",
            description="Roles assigned to purged members after removing roles",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purge: War end",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.WAR_GLOBAL_ROLES_TO_REMOVE,
            name="Roles to remove (everyone)",
            description="Roles removed from ALL server members, "
            "regardless of whether they reacted or are in affected roles",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purge: War end",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.WAR_PROMOTIONS,
            name="Promotions",
            description="Role replacement for members who confirm. "
            "If the source role is in 'Affected roles', it is replaced. "
            "If not, the target role is added without removing the source.",
            option_type=ConfigOptionType.TABLE,
            section="Purge: War end",
            default=[],
            columns=[
                {
                    "key": "from_role",
                    "name": "Source role",
                    "type": "role",
                    "required": True,
                },
                {
                    "key": "to_role",
                    "name": "Target role",
                    "type": "role",
                    "required": True,
                },
            ],
        ),
        ConfigOption(
            key=ConfigKey.WAR_DEFAULT_PROMOTION,
            name="Role for non-affected",
            description="Role to assign to users who confirmed but did NOT have "
            "any affected role. Useful to identify who reacted without being "
            "in the target group. Leave empty to ignore them.",
            option_type=ConfigOptionType.ROLE,
            section="Purge: War end",
            default=None,
        ),
        ConfigOption(
            key=ConfigKey.WAR_EXEC_MSG_FINISH,
            name="Message: Purge end",
            description="Statistics message on completion. "
            "Placeholders: {cleaned}, {promoted_in_group}, {promoted_not_in_group}, "
            "{global_removed}",
            option_type=ConfigOptionType.TEXTAREA,
            section="Purge: War end",
            default="✅ **Purge completed.**\n\n"
            "🧹 Purged: {cleaned}\n"
            "⬆️ Promoted (group): {promoted_in_group}\n"
            "⬆️ Promoted (others): {promoted_not_in_group}\n"
            "🗑️ Global roles removed: {global_removed}",
            max_length=1000,
            placeholders=[
                "cleaned",
                "promoted_in_group",
                "promoted_not_in_group",
                "global_removed",
            ],
        ),
        # ====================================================================
        # GLOBAL PURGE
        # ====================================================================
        ConfigOption(
            key=ConfigKey.GLOBAL_COMMAND_NAME,
            name="Command name",
            description="Name of the slash command to start the global purge",
            option_type=ConfigOptionType.STRING,
            section="Purge: Global",
            default="purge_global",
            max_length=32,
        ),
        ConfigOption(
            key=ConfigKey.GLOBAL_DISPLAY_NAME,
            name="Display name",
            description="Name that appears in the moderation message (e.g.: 'Global purge')",
            option_type=ConfigOptionType.STRING,
            section="Purge: Global",
            default="Global purge",
            max_length=50,
        ),
        ConfigOption(
            key=ConfigKey.GLOBAL_MESSAGE_TEMPLATE,
            name="User message template",
            description="Message users see when the global purge is active. "
            "{date} shows date with dynamic Discord countdown.",
            option_type=ConfigOptionType.TEXTAREA,
            section="Purge: Global",
            default=DEFAULT_GLOBAL_USER_MESSAGE,
            max_length=2000,
            placeholders=["date", "relative_date", "day", "reaction_role"],
        ),
        ConfigOption(
            key=ConfigKey.GLOBAL_ADMIN_ROLES,
            name="Admin roles",
            description="Roles that can start and authorize global purges",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purge: Global",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.GLOBAL_EXCLUDED_ROLES,
            name="Excluded roles",
            description="Roles that will NOT be affected by the global purge "
            "(e.g.: moderators, bots, special roles)",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purge: Global",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.GLOBAL_ROLES_TO_REMOVE,
            name="Roles to remove",
            description="Roles removed from members who don't confirm",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purge: Global",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.GLOBAL_ROLES_TO_ADD,
            name="Roles to assign",
            description="Roles assigned to members who don't confirm "
            "(useful to mark them as inactive)",
            option_type=ConfigOptionType.ROLE_LIST,
            section="Purge: Global",
            default=[],
        ),
        ConfigOption(
            key=ConfigKey.GLOBAL_EXEC_MSG_FINISH,
            name="Message: Purge end",
            description="Statistics message on completion. Placeholders: {cleaned}",
            option_type=ConfigOptionType.TEXTAREA,
            section="Purge: Global",
            default="✅ **Global purge completed.**\n\n🧹 Users purged: {cleaned}",
            max_length=1000,
            placeholders=["cleaned"],
        ),
    ],
)
