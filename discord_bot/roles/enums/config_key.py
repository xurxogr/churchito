"""Configuration keys for the roles cog."""


class ConfigKey:
    """Configuration keys for the roles cog.

    Using class constants instead of StrEnum for simpler key access
    in dictionary operations.
    """

    # Command names
    COMMAND_PREFIX = "command_prefix"

    # Permissions
    MANAGE_ROLES = "manage_roles"

    # Audit channel
    AUDIT_CHANNEL = "audit_channel"

    # Audit notification switches
    AUDIT_PANEL_CREATED = "audit_panel_created"
    AUDIT_PANEL_EDITED = "audit_panel_edited"
    AUDIT_PANEL_DELETED = "audit_panel_deleted"
    AUDIT_USER_ROLE_ADD = "audit_user_role_add"
    AUDIT_USER_ROLE_REMOVE = "audit_user_role_remove"

    # Audit message templates
    AUDIT_PANEL_CREATED_MSG = "audit_panel_created_msg"
    AUDIT_PANEL_EDITED_MSG = "audit_panel_edited_msg"
    AUDIT_PANEL_DELETED_MSG = "audit_panel_deleted_msg"
    AUDIT_USER_ROLE_ADD_MSG = "audit_user_role_add_msg"
    AUDIT_USER_ROLE_REMOVE_MSG = "audit_user_role_remove_msg"

    # User DM settings
    DM_MISSING_ROLE_MSG = "dm_missing_role_msg"
    DM_ROLE_ADDED_MSG = "dm_role_added_msg"
    DM_ROLE_REMOVED_MSG = "dm_role_removed_msg"

    # Error messages
    NO_PERMISSION_TEXT = "no_permission_text"
    NOT_FOUND_TEXT = "not_found_text"
    MISSING_REQUIRED_ROLE_TEXT = "missing_required_role_text"
