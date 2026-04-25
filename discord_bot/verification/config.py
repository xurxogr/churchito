"""Configuration and schema for the verification cog."""

from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.common.schemas.config_option import ConfigOption
from discord_bot.verification.enums import AutoProcessMode, ConfigKey, NameMatchMode

COG_NAME = "verification"

VERIFICATION_CONFIG_SCHEMA = CogConfigSchema(
    cog_name=COG_NAME,
    display_name="Verification",
    description="User verification system with screenshots",
    icon="✅",
    options=[
        # ===== 1. GENERAL OPTIONS =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_ENABLED,
            name="Verification enabled",
            description="Enable or disable the verification system",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
            group="Options",
        ),
        ConfigOption(
            key=ConfigKey.BLOCKING_ROLES,
            name="Roles that block verification",
            description=(
                "Users with any of these roles will not be able to start verification. "
                "Use to prevent already verified users from verifying again."
            ),
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Options",
        ),
        ConfigOption(
            key=ConfigKey.AUTO_REJECT_REVIEW_WINDOW,
            name="Review window (minutes)",
            description=(
                "Minutes during which a moderator can review an auto-rejection. 0 to disable."
            ),
            option_type=ConfigOptionType.INTEGER,
            default=30,
            min_value=0,
            max_value=1440,
            group="Options",
        ),
        ConfigOption(
            key=ConfigKey.SCREENSHOT_TIMEOUT_MINUTES,
            name="Screenshot timeout (minutes)",
            description=(
                "Minutes the user has to send screenshots before the request is "
                "automatically rejected. 0 to disable."
            ),
            option_type=ConfigOptionType.INTEGER,
            default=0,
            min_value=0,
            max_value=1440,
            group="Options",
        ),
        # ===== 2. VERIFICATION PANEL =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_CHANNEL,
            name="Verification channel",
            description=(
                "Channel where the verification panel with buttons is published. "
                "Only channels where the bot has write permission are shown."
            ),
            option_type=ConfigOptionType.CHANNEL,
            group="Verification Panel",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_PANEL_MESSAGE,
            name="Panel message",
            description=(
                "Message that appears in the verification panel. "
                "If you include an image URL (ending in .png, .jpg, .gif, etc.) "
                "it will be displayed as an image in the embed."
            ),
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Welcome to {server_name}!**\n\n"
                "To access the server, you need to verify. "
                "Click the corresponding button to get started."
            ),
            max_length=4000,
            placeholders=["server_name"],
            group="Verification Panel",
        ),
        ConfigOption(
            key=ConfigKey.VERIFY_BUTTON_TEXT,
            name="Verify button text",
            description="Text of the normal verification button",
            option_type=ConfigOptionType.STRING,
            default="Verify",
            max_length=80,
            group="Verification Panel",
        ),
        ConfigOption(
            key=ConfigKey.VERIFY_ALLY_BUTTON_TEXT,
            name="Ally button text",
            description="Text of the ally verification button",
            option_type=ConfigOptionType.STRING,
            default="Verify as Ally",
            max_length=80,
            group="Verification Panel",
        ),
        ConfigOption(
            key=ConfigKey.HEALTH_CHECK_INTERVAL,
            name="Health check interval (minutes)",
            description="Frequency of panel verification (0 to disable)",
            option_type=ConfigOptionType.INTEGER,
            default=30,
            min_value=0,
            max_value=1440,
            group="Verification Panel",
        ),
        # ===== 2. NORMAL VERIFICATION =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY,
            name="Normal type name",
            description="Name to display for normal verification in messages",
            option_type=ConfigOptionType.STRING,
            default="Normal",
            max_length=50,
            group="Verification (Normal)",
        ),
        ConfigOption(
            key=ConfigKey.DM_INSTRUCTIONS_MESSAGE,
            name="DM instructions",
            description="Message sent to user via DM with instructions",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Verification Instructions**\n\n"
                "Hello {username}! To complete your verification in **{server_name}**, "
                "send **2 screenshots** in a single message."
            ),
            max_length=4000,
            placeholders=[
                "username",
                "user_mention",
                "server_name",
                "verification_type",
                "expires",
            ],
            group="Verification (Normal)",
        ),
        ConfigOption(
            key=ConfigKey.REGULAR_ROLES_ADD,
            name="Roles to add",
            description="Roles that are added when approving normal verification",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Verification (Normal)",
        ),
        ConfigOption(
            key=ConfigKey.REGULAR_ROLES_REMOVE,
            name="Roles to remove",
            description="Roles that are removed when approving normal verification",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Verification (Normal)",
        ),
        ConfigOption(
            key=ConfigKey.APPROVAL_MESSAGE_REGULAR,
            name="Approval message",
            description="Message sent to user when approved",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Verification approved!**\n\n"
                "Your verification in **{server_name}** has been approved. "
                "You now have full access to the server."
            ),
            max_length=2000,
            placeholders=["username", "server_name"],
            group="Verification (Normal)",
        ),
        # ===== 3. ALLY VERIFICATION =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY,
            name="Ally type name",
            description="Name to display for ally verification in messages",
            option_type=ConfigOptionType.STRING,
            default="Ally",
            max_length=50,
            group="Verification (Ally)",
        ),
        ConfigOption(
            key=ConfigKey.DM_INSTRUCTIONS_ALLY_MESSAGE,
            name="DM instructions",
            description="Message sent to user via DM with instructions",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Verification Instructions (Ally)**\n\n"
                "Hello {username}! To complete your verification as an ally in **{server_name}**, "
                "send **2 screenshots** in a single message."
            ),
            max_length=4000,
            placeholders=[
                "username",
                "user_mention",
                "server_name",
                "verification_type",
                "expires",
            ],
            group="Verification (Ally)",
        ),
        ConfigOption(
            key=ConfigKey.ALLY_ROLES_ADD,
            name="Roles to add",
            description="Roles that are added when approving ally verification",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Verification (Ally)",
        ),
        ConfigOption(
            key=ConfigKey.ALLY_ROLES_REMOVE,
            name="Roles to remove",
            description="Roles that are removed when approving ally verification",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Verification (Ally)",
        ),
        ConfigOption(
            key=ConfigKey.APPROVAL_MESSAGE_ALLY,
            name="Approval message",
            description="Message sent to user when approved as ally",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Ally verification approved!**\n\n"
                "Your verification as an ally in **{server_name}** has been approved. "
                "You now have access as an ally to the server."
            ),
            max_length=2000,
            placeholders=["username", "server_name"],
            group="Verification (Ally)",
        ),
        # ===== 4. MODERATION PANEL =====
        ConfigOption(
            key=ConfigKey.MOD_NOTIFICATION_CHANNEL,
            name="Moderation channel",
            description=(
                "Channel where moderators receive verification notifications. "
                "Only channels where the bot has write permission are shown."
            ),
            option_type=ConfigOptionType.CHANNEL,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.TRACKER_TITLE,
            name="Tracker title",
            description=(
                "Title of the message with the list of pending verifications. "
                "Leave empty to disable the tracker."
            ),
            option_type=ConfigOptionType.STRING,
            default="📋 Pending Verifications",
            max_length=100,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.MOD_ROLES,
            name="Moderator roles",
            description="Roles that can approve/reject verifications",
            option_type=ConfigOptionType.ROLE_LIST,
            default=[],
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.MOD_EMBED_REGULAR,
            name="Moderation embed (Normal)",
            description="Embed configuration for normal verifications",
            option_type=ConfigOptionType.EMBED,
            default={
                "color": "#FFA500",
                "sections": [
                    {
                        "type": "text",
                        "content": (
                            "**User:** {user_mention} ({username})\n"
                            "**Type:** {verification_type}\n"
                            "**Date:** {created_at}\n\n"
                            "{status}"
                        ),
                    }
                ],
            },
            placeholders=[
                "username",
                "user_mention",
                "user_avatar_url",
                "verification_type",
                "status",
                "created_at",
                "created_at_relative",
                "faction_status",
                "shard_status",
                "regiment_status",
                "name_status",
                "time_status",
            ],
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.MOD_EMBED_ALLY,
            name="Moderation embed (Ally)",
            description="Embed configuration for ally verifications",
            option_type=ConfigOptionType.EMBED,
            default={
                "color": "#FFA500",
                "sections": [
                    {
                        "type": "text",
                        "content": (
                            "**User:** {user_mention} ({username})\n"
                            "**Type:** {verification_type}\n"
                            "**Date:** {created_at}\n\n"
                            "{status}"
                        ),
                    }
                ],
            },
            placeholders=[
                "username",
                "user_mention",
                "user_avatar_url",
                "verification_type",
                "status",
                "created_at",
                "created_at_relative",
                "faction_status",
                "shard_status",
                "regiment_status",
                "name_status",
                "time_status",
            ],
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.MOD_PING_MESSAGE,
            name="Moderator ping message",
            description=(
                "Message sent to notify moderators when there is a pending verification. "
                "Use {roles} to mention roles. Leave empty to not send ping."
            ),
            option_type=ConfigOptionType.STRING,
            default="{roles} - New verification pending review",
            max_length=500,
            placeholders=["roles"],
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.DELETE_PROCESSED_MESSAGES,
            name="Delete processed messages",
            description="Delete messages from moderation channel after approving/rejecting",
            option_type=ConfigOptionType.BOOLEAN,
            default=False,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.ACCEPT_BUTTON_TEXT,
            name="Accept button text",
            description=(
                "Text of the accept button for moderators. "
                "Use {verification_type} to show the verification type."
            ),
            option_type=ConfigOptionType.STRING,
            default="Accept",
            max_length=80,
            placeholders=["verification_type"],
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_BUTTON_TEXT,
            name="Reject button text",
            description="Text of the reject button for moderators",
            option_type=ConfigOptionType.STRING,
            default="Reject",
            max_length=80,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REVIEW_BUTTON_TEXT,
            name="Review button text",
            description="Text of the button to review auto-rejections",
            option_type=ConfigOptionType.STRING,
            default="Review",
            max_length=80,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.HISTORY_LABEL,
            name="History label",
            description="Text for the history section in the review message",
            option_type=ConfigOptionType.STRING,
            default="History",
            max_length=50,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_AWAITING_SCREENSHOTS,
            name="Status: Awaiting screenshots",
            description="Status text when waiting for user to send screenshots",
            option_type=ConfigOptionType.STRING,
            default="⏳ **Status:** Awaiting screenshots...",
            max_length=200,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_PENDING_REVIEW,
            name="Status: Pending review",
            description="Status text when screenshots are ready for review",
            option_type=ConfigOptionType.STRING,
            default="🔍 **Status:** Pending review",
            max_length=200,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_READY_FOR_APPROVAL,
            name="Status: Ready for approval",
            description=(
                "Status text when automatic checks pass but requires manual approval. "
                "Use {roles} to mention the roles that can approve."
            ),
            option_type=ConfigOptionType.STRING,
            default="✅ **Status:** Ready for approval - {roles}",
            max_length=300,
            placeholders=["roles"],
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_APPROVED,
            name="Status: Approved",
            description="Status text when verification was approved",
            option_type=ConfigOptionType.STRING,
            default="✅ **Status:** Approved by {moderator}",
            max_length=200,
            placeholders=["moderator"],
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_REJECTED,
            name="Status: Rejected",
            description="Status text when verification was rejected",
            option_type=ConfigOptionType.STRING,
            default="❌ **Status:** Rejected by {moderator}\n**Reason:** {reason}",
            max_length=200,
            placeholders=["moderator", "reason"],
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.STATUS_CANCELLED,
            name="Status: Cancelled",
            description="Status text when verification was cancelled",
            option_type=ConfigOptionType.STRING,
            default="🚫 **Status:** Cancelled (user left the server)",
            max_length=200,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_SCREENSHOT_TIMEOUT,
            name="Rejection: Screenshot timeout",
            description="Reason when user does not send screenshots in time",
            option_type=ConfigOptionType.STRING,
            default="Timeout waiting for screenshots",
            max_length=200,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_WRONG_CAPTURES,
            name="Rejection: Wrong screenshots",
            description="Reason when screenshots are incorrect or unreadable (API error 422)",
            option_type=ConfigOptionType.STRING,
            default="Screenshots incorrect or unreadable",
            max_length=200,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_NAME_MISMATCH,
            name="Rejection: Name mismatch",
            description="Reason when game name does not match Discord",
            option_type=ConfigOptionType.STRING,
            default="Username does not match",
            max_length=200,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_HAS_REGIMENT,
            name="Rejection: Has regiment",
            description="Reason when user already belongs to a regiment",
            option_type=ConfigOptionType.STRING,
            default="User already belongs to a regiment",
            max_length=200,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_TIME_DIFF,
            name="Rejection: Old screenshot",
            description="Reason when screenshot is too old",
            option_type=ConfigOptionType.STRING,
            default="Screenshot too old",
            max_length=200,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_WRONG_SHARD,
            name="Rejection: Wrong shard",
            description="Reason when shard is incorrect. Use {shard} for the expected one",
            option_type=ConfigOptionType.STRING,
            default="Wrong shard, must be {shard}",
            max_length=200,
            placeholders=["shard"],
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECT_WRONG_FACTION,
            name="Rejection: Wrong faction",
            description="Reason when faction is incorrect",
            option_type=ConfigOptionType.STRING,
            default="Wrong faction",
            max_length=200,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_SELECT_PLACEHOLDER,
            name="Rejection selector placeholder",
            description="Placeholder text for the rejection reason selector",
            option_type=ConfigOptionType.STRING,
            default="Select rejection reason...",
            max_length=100,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_SELECT_MESSAGE,
            name="Rejection selector message",
            description="Message shown to moderator before the rejection reason selector",
            option_type=ConfigOptionType.STRING,
            default="Select rejection reason:",
            max_length=200,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_OTHER_LABEL,
            name="'Other reason' label",
            description="Text of the option to write a custom reason",
            option_type=ConfigOptionType.STRING,
            default="Other reason...",
            max_length=100,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_OTHER_DESCRIPTION,
            name="'Other reason' description",
            description="Description of the option to write a custom reason",
            option_type=ConfigOptionType.STRING,
            default="Write a custom reason",
            max_length=100,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_MODAL_TITLE,
            name="Rejection modal title",
            description="Title of the modal to write a custom reason",
            option_type=ConfigOptionType.STRING,
            default="Rejection Reason",
            max_length=45,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_MODAL_LABEL,
            name="Rejection modal field label",
            description="Label of the text field in the rejection modal",
            option_type=ConfigOptionType.STRING,
            default="Reason",
            max_length=45,
            group="Moderation Panel",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_MODAL_PLACEHOLDER,
            name="Rejection modal placeholder",
            description="Help text in the rejection modal text field",
            option_type=ConfigOptionType.STRING,
            default="Explain why the verification is rejected...",
            max_length=100,
            group="Moderation Panel",
        ),
        # ===== 5. USER MESSAGES =====
        ConfigOption(
            key=ConfigKey.VERIFICATION_STARTED_MESSAGE,
            name="Verification started",
            description="Message shown to user when starting verification",
            option_type=ConfigOptionType.STRING,
            default="Check your direct messages to continue with verification.",
            max_length=500,
            group="User Messages",
        ),
        ConfigOption(
            key=ConfigKey.SCREENSHOTS_RECEIVED_MESSAGE,
            name="Screenshots received",
            description="Confirmation message when user sends screenshots",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "Your screenshots have been received successfully. "
                "A moderator will review your request soon."
            ),
            max_length=2000,
            placeholders=["username", "server_name"],
            group="User Messages",
        ),
        ConfigOption(
            key=ConfigKey.REJECTION_MESSAGE,
            name="Rejection message",
            description="Message sent to user when rejected",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "**Verification rejected**\n\n"
                "Your verification in **{server_name}** has been rejected.\n"
                "**Reason:** {reason}\n\n"
                "You can try again if you wish."
            ),
            max_length=2000,
            placeholders=["username", "server_name", "verification_type", "reason"],
            group="User Messages",
        ),
        ConfigOption(
            key=ConfigKey.WRONG_IMAGES_MESSAGE,
            name="Error: wrong images",
            description="Message when exactly 2 images are not sent",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "You must send exactly **2 screenshots** in the same message. Please try again."
            ),
            max_length=2000,
            placeholders=["username"],
            group="User Messages",
        ),
        ConfigOption(
            key=ConfigKey.DM_DISABLED_MESSAGE,
            name="Error: DMs disabled",
            description="Message when DM cannot be sent to user",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "I couldn't send you a direct message. "
                "Please enable DMs from server members and try again."
            ),
            max_length=1000,
            group="User Messages",
        ),
        ConfigOption(
            key=ConfigKey.ALREADY_PENDING_MESSAGE,
            name="Error: verification pending",
            description="Message when user already has a pending verification",
            option_type=ConfigOptionType.TEXTAREA,
            default="You already have a pending verification request. Please wait.",
            max_length=1000,
            group="User Messages",
        ),
        ConfigOption(
            key=ConfigKey.ALREADY_VERIFIED_MESSAGE,
            name="Error: already verified",
            description="Message when user already has verification roles",
            option_type=ConfigOptionType.STRING,
            default="You already have verification roles. You don't need to verify again.",
            max_length=500,
            group="User Messages",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_DISABLED_MESSAGE,
            name="Error: verification disabled",
            description="Message shown when verification is not configured",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "⚠️ **Verification not available**\n\n"
                "Verification is temporarily disabled. "
                "Please contact an administrator."
            ),
            max_length=2000,
            group="User Messages",
        ),
        ConfigOption(
            key=ConfigKey.REQUEST_NOT_FOUND_MESSAGE,
            name="Error: request not found",
            description="Message when verification request is not found",
            option_type=ConfigOptionType.STRING,
            default="Error: Your verification request was not found.",
            max_length=500,
            group="User Messages",
        ),
        ConfigOption(
            key=ConfigKey.NO_PENDING_VERIFICATION_MESSAGE,
            name="Error: no active verification",
            description="Message when user sends DM without having verification in progress",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "You don't have any verification in progress. "
                "If you want to verify, use the verification panel in the server."
            ),
            max_length=1000,
            group="User Messages",
        ),
        ConfigOption(
            key=ConfigKey.PENDING_IN_OTHER_SERVER_MESSAGE,
            name="Error: verification in other server",
            description="Message when user has pending verification in another server",
            option_type=ConfigOptionType.TEXTAREA,
            default=(
                "You already have verification in progress on another server. "
                "You must complete it or wait for it to be processed before starting another."
            ),
            max_length=1000,
            group="User Messages",
        ),
        # ===== 6. MODERATION MESSAGES =====
        ConfigOption(
            key=ConfigKey.MOD_APPROVED_CONFIRMATION,
            name="Approval confirmation",
            description="Message shown to moderator when approving",
            option_type=ConfigOptionType.STRING,
            default="Verification approved for {username}.",
            max_length=500,
            placeholders=["username"],
            group="Moderation Messages",
        ),
        ConfigOption(
            key=ConfigKey.MOD_REJECTED_CONFIRMATION,
            name="Rejection confirmation",
            description="Message shown to moderator when rejecting",
            option_type=ConfigOptionType.STRING,
            default="Verification rejected for {username}.",
            max_length=500,
            placeholders=["username"],
            group="Moderation Messages",
        ),
        ConfigOption(
            key=ConfigKey.REQUEST_ALREADY_PROCESSED_MESSAGE,
            name="Error: request already processed",
            description="Message when attempting to process an already processed request",
            option_type=ConfigOptionType.STRING,
            default="This request has already been processed.",
            max_length=500,
            group="Moderation Messages",
        ),
        ConfigOption(
            key=ConfigKey.NO_PERMISSION_APPROVE_MESSAGE,
            name="Error: no permission to approve",
            description="Message when moderator does not have permission to approve",
            option_type=ConfigOptionType.STRING,
            default="You do not have permission to approve verifications.",
            max_length=500,
            group="Moderation Messages",
        ),
        ConfigOption(
            key=ConfigKey.NO_PERMISSION_REJECT_MESSAGE,
            name="Error: no permission to reject",
            description="Message when moderator does not have permission to reject",
            option_type=ConfigOptionType.STRING,
            default="You do not have permission to reject verifications.",
            max_length=500,
            group="Moderation Messages",
        ),
        # ===== 7. VERIFICATION API =====
        # Note: API URL and Key are in global settings (verification.api_url, api_key)
        ConfigOption(
            key=ConfigKey.VERIFICATION_FACTION,
            name="Required faction",
            description="Faction that users must have to pass verification",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=[
                ("Colonial", "colonial"),
                ("Warden", "wardens"),
            ],
            default="",
            group="Verification API",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_SHARD,
            name="Required shard",
            description="Shard that users must have to pass verification",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=[
                ("ABLE", "ABLE"),
                ("CHARLIE", "CHARLIE"),
            ],
            default="",
            group="Verification API",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_TIME_DIFF,
            name="Maximum time difference (days)",
            description=("Maximum difference between game time and current time (0 to disable)"),
            option_type=ConfigOptionType.INTEGER,
            default=0,
            min_value=0,
            max_value=999,
            group="Verification API",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_AUTOMATIC,
            name="Automatic processing",
            description="Approve/reject automatically based on configured rules",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=[
                ("None", AutoProcessMode.NONE),
                ("Rejections only", AutoProcessMode.REJECT_ONLY),
                ("Approvals only", AutoProcessMode.APPROVE_ONLY),
                ("Both", AutoProcessMode.BOTH),
            ],
            default=AutoProcessMode.NONE,
            group="Verification API",
        ),
        ConfigOption(
            key=ConfigKey.AUTO_REJECT_INVALID_SCREENSHOTS,
            name="Auto-reject: Invalid screenshots",
            description="Automatically reject when screenshots are unreadable or invalid",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
            group="Verification API",
        ),
        ConfigOption(
            key=ConfigKey.AUTO_REJECT_NAME_MISMATCH,
            name="Auto-reject: Name mismatch",
            description="Automatically reject when game name doesn't match Discord name",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
            group="Verification API",
        ),
        ConfigOption(
            key=ConfigKey.AUTO_REJECT_HAS_REGIMENT,
            name="Auto-reject: Wrong regiment",
            description="Automatically reject when user has a regiment (or wrong regiment)",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
            group="Verification API",
        ),
        ConfigOption(
            key=ConfigKey.AUTO_REJECT_TIME_DIFF,
            name="Auto-reject: Old screenshot",
            description="Automatically reject when screenshot is too old",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
            group="Verification API",
        ),
        ConfigOption(
            key=ConfigKey.AUTO_REJECT_WRONG_SHARD,
            name="Auto-reject: Wrong shard",
            description="Automatically reject when shard doesn't match the required one",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
            group="Verification API",
        ),
        ConfigOption(
            key=ConfigKey.AUTO_REJECT_WRONG_FACTION,
            name="Auto-reject: Wrong faction",
            description="Automatically reject when faction doesn't match the required one",
            option_type=ConfigOptionType.BOOLEAN,
            default=True,
            group="Verification API",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_MATCH_NAME,
            name="Verify name",
            description="Comparison mode between Discord name and game name",
            option_type=ConfigOptionType.TEXT_CHOICE,
            choices=[
                ("Do not check", NameMatchMode.NONE),
                ("Exact", NameMatchMode.EXACT),
                ("Must contain", NameMatchMode.CONTAINS),
            ],
            default=NameMatchMode.NONE,
            group="Verification API",
        ),
        ConfigOption(
            key=ConfigKey.VERIFICATION_VALID_REGIMENT,
            name="Valid regiment",
            description=(
                "ID of the regiment allowed for normal verification. "
                "Use the full content in brackets "
                "(e.g., for '[7-HP#8707] 7th Hispanic Platoon' use '7-HP#8707'). "
                "If empty, any user with a regiment is rejected."
            ),
            option_type=ConfigOptionType.STRING,
            default="",
            max_length=50,
            group="Verification API",
        ),
        ConfigOption(
            key=ConfigKey.PLAYER_INFO_SECTIONS,
            name="Player information sections",
            description=(
                "Sections to display player information in the moderation message. "
                "Use the 'Fields (3 col)' type to display data in columns."
            ),
            option_type=ConfigOptionType.EMBED_SECTIONS,
            default=[
                {
                    "type": "text",
                    "title": "Player Information",
                    "content": "",
                },
                {
                    "type": "fields",
                    "inline": True,
                    "field_1_name": "Name",
                    "field_1_value": "{name}",
                    "field_2_name": "Regiment",
                    "field_2_value": "{regiment}",
                    "field_3_name": "Level",
                    "field_3_value": "{level}",
                },
                {
                    "type": "fields",
                    "inline": True,
                    "field_1_name": "Faction",
                    "field_1_value": "{faction}",
                    "field_2_name": "Shard",
                    "field_2_value": "{shard}",
                    "field_3_name": "Game time",
                    "field_3_value": "{time}",
                },
                {
                    "type": "fields",
                    "inline": True,
                    "field_1_name": "War",
                    "field_1_value": "{war}",
                    "field_2_name": "Current time",
                    "field_2_value": "{war_time}",
                    "field_3_name": "",
                    "field_3_value": "",
                },
            ],
            placeholders=[
                "name",
                "regiment",
                "level",
                "faction",
                "shard",
                "time",
                "war",
                "war_time",
                "faction_status",
                "shard_status",
                "regiment_status",
                "name_status",
                "time_status",
            ],
            group="Verification API",
        ),
    ],
)
