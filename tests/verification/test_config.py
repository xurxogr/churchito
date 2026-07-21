"""Tests for discord_bot/verification/config.py."""

from discord_bot.verification.config import (
    COG_NAME,
    VERIFICATION_CONFIG_SCHEMA,
)


class TestCogName:
    """Tests for COG_NAME."""

    def test_cog_name_value(self) -> None:
        """Test that the cog name is correct."""
        assert COG_NAME == "verification"


class TestVerificationConfigSchema:
    """Tests for VERIFICATION_CONFIG_SCHEMA."""

    def test_schema_cog_name(self) -> None:
        """Test cog name in the schema."""
        assert VERIFICATION_CONFIG_SCHEMA.cog_name == "verification"

    def test_schema_display_name(self) -> None:
        """Test display name."""
        assert VERIFICATION_CONFIG_SCHEMA.display_name == "Verification"

    def test_schema_has_icon(self) -> None:
        """Test that the schema has an icon."""
        assert VERIFICATION_CONFIG_SCHEMA.icon is not None
        assert VERIFICATION_CONFIG_SCHEMA.icon == "✅"

    def test_schema_has_options(self) -> None:
        """Test that the schema has options."""
        assert len(VERIFICATION_CONFIG_SCHEMA.options) > 0

    def test_schema_has_verification_enabled_option(self) -> None:
        """Test that verification enabled option exists."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "verification_enabled" in keys

    def test_schema_has_verification_channel_option(self) -> None:
        """Test that verification channel option exists."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "verification_channel" in keys

    def test_schema_has_mod_channel_option(self) -> None:
        """Test that moderation channel option exists."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "mod_notification_channel" in keys

    def test_schema_has_mod_roles_option(self) -> None:
        """Test that moderator roles option exists."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "mod_roles" in keys

    def test_schema_has_regular_roles_options(self) -> None:
        """Test that regular verification role options exist."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "regular_roles_add" in keys
        assert "regular_roles_remove" in keys

    def test_schema_has_ally_roles_options(self) -> None:
        """Test that ally verification role options exist."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "ally_roles_add" in keys
        assert "ally_roles_remove" in keys

    def test_schema_has_rejection_reason_options(self) -> None:
        """Test that rejection reason options exist."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "reject_wrong_captures" in keys
        assert "reject_name_mismatch" in keys
        assert "reject_has_regiment" in keys
        assert "reject_time_diff" in keys
        assert "reject_wrong_shard" in keys
        assert "reject_wrong_faction" in keys

    def test_schema_has_status_options(self) -> None:
        """Test that status options exist."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "status_awaiting_screenshots" in keys
        assert "status_pending_review" in keys
        assert "status_approved" in keys
        assert "status_rejected" in keys

    def test_schema_has_message_template_options(self) -> None:
        """Test that message template options exist."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "verification_panel_message" in keys
        assert "dm_instructions_message" in keys
        assert "dm_instructions_ally_message" in keys
        # mod_message_template was replaced by configurable embeds
        assert "mod_embed_regular" in keys
        assert "mod_embed_ally" in keys

    def test_schema_has_api_verification_options(self) -> None:
        """Test that API verification options exist."""
        # Note: api_url and api_key are in global settings, not per-guild config
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "verification_faction" in keys
        assert "verification_shard" in keys
        assert "verification_time_diff" in keys
        assert "verification_automatic" in keys
        assert "verification_match_name" in keys
        assert "player_info_sections" in keys

    def test_schema_has_steam_profile_options(self) -> None:
        """Test that Steam profile options exist."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "steam_profile_required_regular" in keys
        assert "steam_profile_required_ally" in keys
        assert "steam_profile_request_message" in keys
        assert "screenshots_received_awaiting_steam_message" in keys
        assert "steam_url_received_message" in keys
        assert "invalid_steam_url_message" in keys
        assert "auto_reject_steam_private" in keys
        assert "reject_steam_private" in keys

    def test_steam_profile_options_grouped_together(self) -> None:
        """Test that all Steam profile options share the same dashboard group."""
        steam_keys = {
            "steam_profile_required_regular",
            "steam_profile_required_ally",
            "steam_profile_request_message",
            "screenshots_received_awaiting_steam_message",
            "steam_url_received_message",
            "invalid_steam_url_message",
            "auto_reject_steam_private",
            "reject_steam_private",
        }
        groups = {opt.group for opt in VERIFICATION_CONFIG_SCHEMA.options if opt.key in steam_keys}
        assert groups == {"Steam Profile"}

    def test_mod_embed_options_have_steam_status_placeholder(self) -> None:
        """Test that mod embed options include the steam_status placeholder."""
        for opt in VERIFICATION_CONFIG_SCHEMA.options:
            if opt.key in ("mod_embed_regular", "mod_embed_ally"):
                assert "steam_status" in (opt.placeholders or [])

    def test_mod_embed_options_have_steam_profile_url_placeholder(self) -> None:
        """Test that mod embed options include the steam_profile_url placeholder."""
        for opt in VERIFICATION_CONFIG_SCHEMA.options:
            if opt.key in ("mod_embed_regular", "mod_embed_ally"):
                assert "steam_profile_url" in (opt.placeholders or [])
