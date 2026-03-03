"""Claves de configuracion del cog de verificacion."""

from enum import StrEnum


class ConfigKey(StrEnum):
    """Claves de configuracion para el cog de verificacion."""

    # Configuracion general
    VERIFICATION_ENABLED = "verification_enabled"
    VERIFICATION_CHANNEL = "verification_channel"
    MOD_NOTIFICATION_CHANNEL = "mod_notification_channel"
    HEALTH_CHECK_INTERVAL = "health_check_interval"

    # Textos de botones
    VERIFY_BUTTON_TEXT = "verify_button_text"
    VERIFY_ALLY_BUTTON_TEXT = "verify_ally_button_text"
    ACCEPT_BUTTON_TEXT = "accept_button_text"
    REJECT_BUTTON_TEXT = "reject_button_text"

    # Nombres de tipos de verificacion
    VERIFICATION_TYPE_REGULAR_DISPLAY = "verification_type_regular_display"
    VERIFICATION_TYPE_ALLY_DISPLAY = "verification_type_ally_display"
    HISTORY_LABEL = "history_label"

    # Mensajes del panel y DM
    VERIFICATION_PANEL_MESSAGE = "verification_panel_message"
    DM_INSTRUCTIONS_MESSAGE = "dm_instructions_message"
    DM_INSTRUCTIONS_ALLY_MESSAGE = "dm_instructions_ally_message"
    VERIFICATION_STARTED_MESSAGE = "verification_started_message"
    WRONG_IMAGES_MESSAGE = "wrong_images_message"
    SCREENSHOTS_RECEIVED_MESSAGE = "screenshots_received_message"
    MOD_MESSAGE_TEMPLATE = "mod_message_template"
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

    # Motivos de rechazo (usados tanto en rechazo automático como manual)
    REJECT_WRONG_CAPTURES = "reject_wrong_captures"
    REJECT_NAME_MISMATCH = "reject_name_mismatch"
    REJECT_HAS_REGIMENT = "reject_has_regiment"
    REJECT_TIME_DIFF = "reject_time_diff"
    REJECT_WRONG_SHARD = "reject_wrong_shard"
    REJECT_WRONG_FACTION = "reject_wrong_faction"

    # Selector de rechazo
    REJECTION_SELECT_MESSAGE = "rejection_select_message"
    REJECTION_SELECT_PLACEHOLDER = "rejection_select_placeholder"
    REJECTION_OTHER_LABEL = "rejection_other_label"
    REJECTION_OTHER_DESCRIPTION = "rejection_other_description"
    REJECTION_MODAL_TITLE = "rejection_modal_title"
    REJECTION_MODAL_LABEL = "rejection_modal_label"
    REJECTION_MODAL_PLACEHOLDER = "rejection_modal_placeholder"

    # Opciones
    DELETE_PROCESSED_MESSAGES = "delete_processed_messages"
    BLOCK_ALREADY_VERIFIED = "block_already_verified"
    AUTO_REJECT_REVIEW_WINDOW = "auto_reject_review_window"

    # Botón de revisión
    REVIEW_BUTTON_TEXT = "review_button_text"

    # API Verification Settings (API URL and Key are in global settings)
    VERIFICATION_FACTION = "verification_faction"
    VERIFICATION_SHARD = "verification_shard"
    VERIFICATION_TIME_DIFF = "verification_time_diff"
    VERIFICATION_AUTOMATIC = "verification_automatic"
    VERIFICATION_MATCH_NAME = "verification_match_name"
    VERIFICATION_VALID_REGIMENT = "verification_valid_regiment"
    PLAYER_INFO_TEMPLATE = "player_info_template"

    # Claves internas (prefijo _ indica que no son configurables por usuario)
    PANEL_MESSAGE_ID = "_panel_message_id"
    PANEL_CHANNEL_ID = "_panel_channel_id"
