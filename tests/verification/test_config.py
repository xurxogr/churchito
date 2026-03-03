"""Tests para discord_bot/verification/config.py."""

from discord_bot.verification.config import (
    COG_NAME,
    VERIFICATION_CONFIG_SCHEMA,
)


class TestCogName:
    """Tests para COG_NAME."""

    def test_cog_name_value(self) -> None:
        """Probar que el nombre del cog es correcto."""
        assert COG_NAME == "verification"


class TestVerificationConfigSchema:
    """Tests para VERIFICATION_CONFIG_SCHEMA."""

    def test_schema_cog_name(self) -> None:
        """Probar nombre del cog en el schema."""
        assert VERIFICATION_CONFIG_SCHEMA.cog_name == "verification"

    def test_schema_display_name(self) -> None:
        """Probar nombre de display."""
        assert VERIFICATION_CONFIG_SCHEMA.display_name == "Verificación"

    def test_schema_has_icon(self) -> None:
        """Probar que el schema tiene un icono."""
        assert VERIFICATION_CONFIG_SCHEMA.icon is not None
        assert VERIFICATION_CONFIG_SCHEMA.icon == "✅"

    def test_schema_has_options(self) -> None:
        """Probar que el schema tiene opciones."""
        assert len(VERIFICATION_CONFIG_SCHEMA.options) > 0

    def test_schema_has_verification_enabled_option(self) -> None:
        """Probar que existe la opcion de verificacion habilitada."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "verification_enabled" in keys

    def test_schema_has_verification_channel_option(self) -> None:
        """Probar que existe la opcion de canal de verificacion."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "verification_channel" in keys

    def test_schema_has_mod_channel_option(self) -> None:
        """Probar que existe la opcion de canal de moderacion."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "mod_notification_channel" in keys

    def test_schema_has_mod_roles_option(self) -> None:
        """Probar que existe la opcion de roles de moderador."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "mod_roles" in keys

    def test_schema_has_regular_roles_options(self) -> None:
        """Probar que existen las opciones de roles para verificacion normal."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "regular_roles_add" in keys
        assert "regular_roles_remove" in keys

    def test_schema_has_ally_roles_options(self) -> None:
        """Probar que existen las opciones de roles para verificacion de aliado."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "ally_roles_add" in keys
        assert "ally_roles_remove" in keys

    def test_schema_has_rejection_reason_options(self) -> None:
        """Probar que existen las opciones de motivos de rechazo."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "reject_wrong_captures" in keys
        assert "reject_name_mismatch" in keys
        assert "reject_has_regiment" in keys
        assert "reject_time_diff" in keys
        assert "reject_wrong_shard" in keys
        assert "reject_wrong_faction" in keys

    def test_schema_has_status_options(self) -> None:
        """Probar que existen las opciones de estados."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "status_awaiting_screenshots" in keys
        assert "status_pending_review" in keys
        assert "status_approved" in keys
        assert "status_rejected" in keys

    def test_schema_has_message_template_options(self) -> None:
        """Probar que existen las opciones de plantillas de mensaje."""
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "verification_panel_message" in keys
        assert "dm_instructions_message" in keys
        assert "dm_instructions_ally_message" in keys
        # mod_message_template fue reemplazado por los embeds configurables
        assert "mod_embed_regular" in keys
        assert "mod_embed_ally" in keys

    def test_schema_has_api_verification_options(self) -> None:
        """Probar que existen las opciones de API de verificación."""
        # Note: api_url and api_key are in global settings, not per-guild config
        keys = [opt.key for opt in VERIFICATION_CONFIG_SCHEMA.options]
        assert "verification_faction" in keys
        assert "verification_shard" in keys
        assert "verification_time_diff" in keys
        assert "verification_automatic" in keys
        assert "verification_match_name" in keys
        assert "player_info_sections" in keys
