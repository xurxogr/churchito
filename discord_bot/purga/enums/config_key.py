"""Claves de configuración del cog de purga."""

from enum import StrEnum


class ConfigKey(StrEnum):
    """Claves de configuración para el cog de purga."""

    # === COMMON - Moderación ===
    MOD_CHANNEL = "mod_channel"
    MOD_MESSAGE_TEMPLATE = "mod_message_template"
    MOD_BUTTON_COLOR = "mod_button_color"
    MOD_BUTTON_TEXT = "mod_button_text"
    MOD_REQUIRED_REACTIONS = "mod_required_reactions"
    MOD_REACTION_TIMEOUT = "mod_reaction_timeout"
    MOD_MESSAGE_RETENTION = "mod_message_retention"
    MOD_STATUS_PENDING = "mod_status_pending"
    MOD_STATUS_AUTHORIZED = "mod_status_authorized"
    MOD_STATUS_EXPIRED = "mod_status_expired"
    MOD_STATUS_CANCEL_PENDING = "mod_status_cancel_pending"
    MOD_STATUS_CANCELLED = "mod_status_cancelled"
    MOD_STATUS_EXECUTED = "mod_status_executed"
    MOD_STOP_BUTTON_TEXT = "mod_stop_button_text"
    MOD_ACTIVE_PURGE_TEXT = "mod_active_purge_text"
    MOD_NO_PERMISSION_TEXT = "mod_no_permission_text"

    # === COMMON - Usuarios ===
    USER_CHANNEL = "user_channel"
    USER_BUTTON_COLOR = "user_button_color"
    USER_BUTTON_TEXT = "user_button_text"
    USER_REACTION_ROLE = "user_reaction_role"
    USER_FIRST_REACTION_TEXT = "user_first_reaction_text"
    USER_ALREADY_REACTED_TEXT = "user_already_reacted_text"
    USER_REMOVED_REACTION_TEXT = "user_removed_reaction_text"

    # === COMMON - General ===
    PURGE_HOUR = "purge_hour"
    TEST_MODE = "test_mode"
    AUDIT_LEVEL = "audit_level"

    # === COMMON - Mensajes de ejecución ===
    EXEC_MSG_SIMULATION = "exec_msg_simulation"
    EXEC_MSG_INIT = "exec_msg_init"
    EXEC_MSG_CLEANING_ROLE = "exec_msg_cleaning_role"
    EXEC_MSG_USER_CLEANED = "exec_msg_user_cleaned"
    EXEC_MSG_PROMOTIONS_START = "exec_msg_promotions_start"
    EXEC_MSG_PROMOTION_ROLE = "exec_msg_promotion_role"
    EXEC_MSG_USER_PROMOTED = "exec_msg_user_promoted"
    EXEC_MSG_PROMOTION_DEFAULT = "exec_msg_promotion_default"
    EXEC_MSG_USER_PROMOTED_DEFAULT = "exec_msg_user_promoted_default"
    EXEC_MSG_FINISH = "exec_msg_finish"

    # === PURGA FIN DE GUERRA ===
    WAR_COMMAND_NAME = "war_command_name"
    WAR_MESSAGE_TEMPLATE = "war_message_template"
    WAR_ADMIN_ROLES = "war_admin_roles"
    WAR_AFFECTED_ROLES = "war_affected_roles"
    WAR_ROLES_TO_REMOVE = "war_roles_to_remove"
    WAR_ROLES_TO_ADD = "war_roles_to_add"
    WAR_PROMOTIONS = "war_promotions"
    WAR_DEFAULT_PROMOTION = "war_default_promotion"
