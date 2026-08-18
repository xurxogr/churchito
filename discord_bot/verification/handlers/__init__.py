"""Verification flow handlers.

This package contains handlers for the verification flow:
- start: Verification start (request creation, DM instructions, mod message)
- flow: Moderator actions (accept, reject, review)
- dm_intake: Screenshots / Steam URL received by DM
- mod_messages: Moderation message status updates and tracker management
- mod_review: Moderation message update when screenshots arrive (auto/manual review)
- auto_processing: Automatic processing (auto-approval/rejection)
- utils: Verification-specific utilities
"""

from discord_bot.verification.handlers.dm_intake import handle_dm_screenshots
from discord_bot.verification.handlers.flow import (
    ModActionContext,
    handle_accept,
    handle_reject,
    handle_review,
    show_rejection_select,
    validate_mod_action,
)
from discord_bot.verification.handlers.mod_messages import (
    build_initial_check_statuses,
    update_mod_message_cancelled,
    update_mod_message_for_manual_review,
    update_mod_message_status,
    update_tracker_message,
)
from discord_bot.verification.handlers.mod_review import update_mod_message_for_review
from discord_bot.verification.handlers.start import handle_verification_start
from discord_bot.verification.handlers.utils import get_ready_for_approval_status

__all__ = [
    # dm_intake
    "handle_dm_screenshots",
    # start
    "handle_verification_start",
    # flow
    "ModActionContext",
    "handle_accept",
    "handle_reject",
    "handle_review",
    "show_rejection_select",
    "validate_mod_action",
    # mod_messages
    "build_initial_check_statuses",
    "update_mod_message_cancelled",
    "update_mod_message_for_manual_review",
    "update_mod_message_status",
    "update_tracker_message",
    # mod_review
    "update_mod_message_for_review",
    # utils
    "get_ready_for_approval_status",
]
