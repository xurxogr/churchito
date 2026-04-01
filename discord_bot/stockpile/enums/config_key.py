"""Configuration keys for the stockpile cog."""


class ConfigKey:
    """Configuration keys for the stockpile cog.

    Using class constants instead of StrEnum for simpler key access
    in dictionary operations.
    """

    # Command names
    ADD_COMMAND_NAME = "add_command_name"
    SHOW_COMMAND_NAME = "show_command_name"
    DELETE_COMMAND_NAME = "delete_command_name"

    # Channels
    COMMAND_CHANNEL = "command_channel"

    # Permissions
    ADD_ROLES = "add_roles"
    DELETE_ROLES = "delete_roles"
    ALLOWED_VIEW_ROLES = "allowed_view_roles"

    # Messages
    ADD_SUCCESS_TEXT = "add_success_text"
    SHOW_HEADER_TEXT = "show_header_text"
    SHOW_LOCATION_EMBED = "show_location_embed"
    SHOW_EMPTY_EMBED = "show_empty_embed"
    DELETE_SUCCESS_TEXT = "delete_success_text"
    NO_PERMISSION_TEXT = "no_permission_text"
    NOT_FOUND_TEXT = "not_found_text"
    INVALID_CODE_TEXT = "invalid_code_text"
    INVALID_ROLES_TEXT = "invalid_roles_text"
    WRONG_CHANNEL_TEXT = "wrong_channel_text"

    # Legacy keys (kept for migration)
    SHOW_ITEM_TEXT = "show_item_text"
    SHOW_EMPTY_TEXT = "show_empty_text"

    # Notifications
    ADD_NOTIFICATION_TEXT = "add_notification_text"
    DELETE_NOTIFICATION_TEXT = "delete_notification_text"

    # Pinned Message
    PINNED_HEADER_TEXT = "pinned_header_text"
    PINNED_ITEM_TEXT = "pinned_item_text"

    # Internal keys (prefix _ indicates they are not user-configurable)
    PINNED_MESSAGE_ID = "_pinned_message_id"
    PINNED_CHANNEL_ID = "_pinned_channel_id"
