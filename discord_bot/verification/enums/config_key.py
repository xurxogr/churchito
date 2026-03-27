"""Configuration keys for the verification cog."""

from enum import StrEnum


class ConfigKey(StrEnum):
    """Configuration keys for the verification cog."""

    # General configuration
    VERIFICATION_ENABLED = "verification_enabled"
    VERIFICATION_CHANNEL = "verification_channel"
    MOD_NOTIFICATION_CHANNEL = "mod_notification_channel"
    HEALTH_CHECK_INTERVAL = "health_check_interval"

    # Button texts
    VERIFY_BUTTON_TEXT = "verify_button_text"
    VERIFY_ALLY_BUTTON_TEXT = "verify_ally_button_text"
    ACCEPT_BUTTON_TEXT = "accept_button_text"
    REJECT_BUTTON_TEXT = "reject_button_text"

    # Verification type names
    VERIFICATION_TYPE_REGULAR_DISPLAY = "verification_type_regular_display"
    VERIFICATION_TYPE_ALLY_DISPLAY = "verification_type_ally_display"
    HISTORY_LABEL = "history_label"

    # Moderation embeds (ConfigOptionType.EMBED)
    MOD_EMBED_REGULAR = "mod_embed_regular"
    MOD_EMBED_ALLY = "mod_embed_ally"

    # Panel and DM messages
    VERIFICATION_PANEL_MESSAGE = "verification_panel_message"
    DM_INSTRUCTIONS_MESSAGE = "dm_instructions_message"
    DM_INSTRUCTIONS_ALLY_MESSAGE = "dm_instructions_ally_message"
    VERIFICATION_STARTED_MESSAGE = "verification_started_message"
    WRONG_IMAGES_MESSAGE = "wrong_images_message"
    SCREENSHOTS_RECEIVED_MESSAGE = "screenshots_received_message"
    MOD_PING_MESSAGE = "mod_ping_message"
    STATUS_AWAITING_SCREENSHOTS = "status_awaiting_screenshots"
    STATUS_PENDING_REVIEW = "status_pending_review"
    STATUS_READY_FOR_APPROVAL = "status_ready_for_approval"
    STATUS_APPROVED = "status_approved"
    STATUS_REJECTED = "status_rejected"
    STATUS_CANCELLED = "status_cancelled"
    APPROVAL_MESSAGE_REGULAR = "approval_message_regular"
    APPROVAL_MESSAGE_ALLY = "approval_message_ally"
    REJECTION_MESSAGE = "rejection_message"
    DM_DISABLED_MESSAGE = "dm_disabled_message"
    ALREADY_PENDING_MESSAGE = "already_pending_message"
    VERIFICATION_DISABLED_MESSAGE = "verification_disabled_message"
    ALREADY_VERIFIED_MESSAGE = "already_verified_message"
    REQUEST_NOT_FOUND_MESSAGE = "request_not_found_message"
    NO_PENDING_VERIFICATION_MESSAGE = "no_pending_verification_message"
    PENDING_IN_OTHER_SERVER_MESSAGE = "pending_in_other_server_message"
    REQUEST_ALREADY_PROCESSED_MESSAGE = "request_already_processed_message"
    NO_PERMISSION_APPROVE_MESSAGE = "no_permission_approve_message"
    NO_PERMISSION_REJECT_MESSAGE = "no_permission_reject_message"
    MOD_APPROVED_CONFIRMATION = "mod_approved_confirmation"
    MOD_REJECTED_CONFIRMATION = "mod_rejected_confirmation"

    # Roles
    REGULAR_ROLES_ADD = "regular_roles_add"
    REGULAR_ROLES_REMOVE = "regular_roles_remove"
    ALLY_ROLES_ADD = "ally_roles_add"
    ALLY_ROLES_REMOVE = "ally_roles_remove"
    MOD_ROLES = "mod_roles"

    # Rejection reasons (used for both automatic and manual rejection)
    REJECT_SCREENSHOT_TIMEOUT = "reject_screenshot_timeout"
    REJECT_WRONG_CAPTURES = "reject_wrong_captures"
    REJECT_NAME_MISMATCH = "reject_name_mismatch"
    REJECT_HAS_REGIMENT = "reject_has_regiment"
    REJECT_TIME_DIFF = "reject_time_diff"
    REJECT_WRONG_SHARD = "reject_wrong_shard"
    REJECT_WRONG_FACTION = "reject_wrong_faction"

    # Rejection selector
    REJECTION_SELECT_MESSAGE = "rejection_select_message"
    REJECTION_SELECT_PLACEHOLDER = "rejection_select_placeholder"
    REJECTION_OTHER_LABEL = "rejection_other_label"
    REJECTION_OTHER_DESCRIPTION = "rejection_other_description"
    REJECTION_MODAL_TITLE = "rejection_modal_title"
    REJECTION_MODAL_LABEL = "rejection_modal_label"
    REJECTION_MODAL_PLACEHOLDER = "rejection_modal_placeholder"

    # Options
    DELETE_PROCESSED_MESSAGES = "delete_processed_messages"
    BLOCKING_ROLES = "blocking_roles"
    AUTO_REJECT_REVIEW_WINDOW = "auto_reject_review_window"
    SCREENSHOT_TIMEOUT_MINUTES = "screenshot_timeout_minutes"

    # Review button
    REVIEW_BUTTON_TEXT = "review_button_text"

    # API Verification Settings (API URL and Key are in global settings)
    VERIFICATION_FACTION = "verification_faction"
    VERIFICATION_SHARD = "verification_shard"
    VERIFICATION_TIME_DIFF = "verification_time_diff"
    VERIFICATION_AUTOMATIC = "verification_automatic"
    VERIFICATION_MATCH_NAME = "verification_match_name"
    VERIFICATION_VALID_REGIMENT = "verification_valid_regiment"
    PLAYER_INFO_SECTIONS = "player_info_sections"

    # Pending verifications tracker
    TRACKER_TITLE = "tracker_title"

    # Internal keys (prefix _ indicates they are not user-configurable)
    PANEL_MESSAGE_ID = "_panel_message_id"
    PANEL_CHANNEL_ID = "_panel_channel_id"
    TRACKER_MESSAGE_ID = "_tracker_message_id"
