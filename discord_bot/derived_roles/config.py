"""Configuration and schema for the derived roles cog."""

from enum import StrEnum

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.derived_roles.validator import validate_rules

COG_NAME = "derived_roles"


class ConfigKey(StrEnum):
    """Configuration keys for the derived roles cog."""

    RULES = "rules"
    SYNC_INTERVAL = "sync_interval"
    AUDIT_CHANNEL = "audit_channel"
    AUDIT_APPLIED = "audit_applied"
    AUDIT_ERROR = "audit_error"
    AUDIT_RECONCILIATION = "audit_reconciliation"
    AUDIT_APPLIED_MSG = "audit_applied_msg"
    AUDIT_ERROR_MSG = "audit_error_msg"
    AUDIT_RECOVERED_MSG = "audit_recovered_msg"
    AUDIT_RECONCILIATION_MSG = "audit_reconciliation_msg"


DERIVED_ROLES_CONFIG_SCHEMA = CogConfigSchema(
    cog_name=COG_NAME,
    display_name="Derived Roles",
    description="Automatic role dependencies: grant, require, or forbid roles based on other roles",
    icon="🔗",
    options=[
        # ===== 1. RULES =====
        ConfigOption(
            key=ConfigKey.RULES,
            name="Rules",
            description=(
                "Rules evaluated on every role change and on periodic sync, always read "
                "left to right. Grants: with the trigger role, the target role is added. "
                "Is required for: without the trigger role, the target role is removed. "
                "Forbids: with the trigger role, the target role is removed. "
                "Rules cascade, contradictory or circular sets are rejected on save, "
                "and on conflict removal wins."
            ),
            option_type=ConfigOptionType.TABLE,
            default=[],
            columns=[
                {
                    "key": "trigger_role",
                    "name": "Trigger role",
                    "type": "role",
                    "required": True,
                    "allow_duplicates": True,
                },
                {
                    "key": "rule_type",
                    "name": "Rule",
                    "type": "choice",
                    "required": True,
                    "choices": [
                        ["Grants (with trigger, target is added)", "implies"],
                        ["Is required for (without trigger, target is removed)", "requires"],
                        ["Forbids (with trigger, target is removed)", "incompatible"],
                    ],
                },
                {
                    "key": "target_role",
                    "name": "Target role",
                    "type": "role",
                    "manageable_only": True,
                    "required": True,
                    "allow_duplicates": True,
                },
            ],
            custom_validator=validate_rules,
            group="Rules",
        ),
        # ===== 2. GENERAL =====
        ConfigOption(
            key=ConfigKey.SYNC_INTERVAL,
            name="Reconciliation interval (minutes)",
            description=(
                "Periodic sweep that re-applies all rules to all members, repairing any "
                "state missed while the bot was offline (0 to disable)"
            ),
            option_type=ConfigOptionType.INTEGER,
            default=60,
            min_value=0,
            max_value=1440,
            group="General",
        ),
        # ===== 3. AUDIT =====
        ConfigOption(
            key=ConfigKey.AUDIT_CHANNEL,
            name="Audit channel",
            description="Channel for audit notifications (rule applications, errors)",
            option_type=ConfigOptionType.CHANNEL,
            default=None,
            group="Audit",
        ),
        ConfigOption(
            key=ConfigKey.AUDIT_APPLIED,
            name="Notify on rule applied",
            description="Send notification when rules change a member's roles",
            option_type=ConfigOptionType.BOOLEAN,
            default=False,
            group="Audit",
        ),
        ConfigOption(
            key=ConfigKey.AUDIT_ERROR,
            name="Notify on errors",
            description=(
                "Send notification when roles cannot be modified (missing permissions or "
                "role hierarchy). Notifies once per failure state and once on recovery, "
                "not on every retry"
            ),
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
            group="Audit",
        ),
        ConfigOption(
            key=ConfigKey.AUDIT_RECONCILIATION,
            name="Notify on reconciliation fixes",
            description="Send a summary when the periodic sweep corrects members",
            option_type=ConfigOptionType.BOOLEAN,
            default=False,
            group="Audit",
        ),
        # ===== 4. AUDIT MESSAGES =====
        ConfigOption(
            key=ConfigKey.AUDIT_APPLIED_MSG,
            name="Rule applied message",
            description="Audit message when rules change a member's roles",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Derived roles:** {user_mention} — trigger: {trigger_changes} | "
                "added: {added_roles} | removed: {removed_roles}"
            ),
            max_length=500,
            placeholders=[
                "user_name",
                "user_mention",
                "added_roles",
                "removed_roles",
                "trigger_changes",
            ],
            group="Audit Messages",
        ),
        ConfigOption(
            key=ConfigKey.AUDIT_ERROR_MSG,
            name="Error message",
            description="Audit message when roles cannot be modified",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "⚠️ **Derived roles:** cannot modify roles for {user_name}. "
                "Check that the bot's role is above the managed roles."
            ),
            max_length=500,
            placeholders=[
                "user_name",
                "user_mention",
            ],
            group="Audit Messages",
        ),
        ConfigOption(
            key=ConfigKey.AUDIT_RECOVERED_MSG,
            name="Recovery message",
            description="Audit message when role management works again after an error",
            option_type=ConfigOptionType.TEXTAREA,
            default="✅ **Derived roles:** role management recovered.",
            max_length=500,
            placeholders=[],
            group="Audit Messages",
        ),
        ConfigOption(
            key=ConfigKey.AUDIT_RECONCILIATION_MSG,
            name="Reconciliation message",
            description="Audit summary when the periodic sweep corrects members",
            option_type=ConfigOptionType.TEXTAREA,
            default="🔄 **Derived roles:** reconciliation corrected {count} member(s).",
            max_length=500,
            placeholders=[
                "count",
            ],
            group="Audit Messages",
        ),
    ],
)
