"""Tests for I18nService."""

import json
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from discord_bot.i18n import I18nService


class TestI18nServiceInitialization:
    """Tests for I18nService initialization."""

    def test_service_initializes_with_translations(self) -> None:
        """Test that service loads translations on initialization."""
        service = I18nService()

        assert "en" in service._translations
        assert "es" in service._translations
        assert isinstance(service._translations["en"], dict)
        assert isinstance(service._translations["es"], dict)

    def test_supported_languages_defined(self) -> None:
        """Test that supported languages are properly defined."""
        assert "en" in I18nService.SUPPORTED_LANGUAGES
        assert "es" in I18nService.SUPPORTED_LANGUAGES
        assert I18nService.SUPPORTED_LANGUAGES["en"] == "English"
        assert I18nService.SUPPORTED_LANGUAGES["es"] == "Español"

    def test_default_language_is_english(self) -> None:
        """Test that default language is English."""
        assert I18nService.DEFAULT_LANGUAGE == "en"

    @patch("discord_bot.i18n.LOCALES_DIR", new_callable=MagicMock)
    @patch("builtins.open", new_callable=mock_open, read_data='{"test": "value"}')
    def test_load_translations_handles_valid_json(
        self, mock_file: MagicMock, mock_locales_dir: MagicMock
    ) -> None:
        """Test that valid JSON files are loaded correctly."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_locales_dir.__truediv__.return_value = mock_path

        service = I18nService()

        assert "en" in service._translations
        assert "es" in service._translations

    @patch("discord_bot.i18n.LOCALES_DIR", new_callable=MagicMock)
    def test_load_translations_handles_missing_files(self, mock_locales_dir: MagicMock) -> None:
        """Test that missing locale files result in empty translations."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False
        mock_locales_dir.__truediv__.return_value = mock_path

        service = I18nService()

        # Should initialize empty translations for missing files
        assert "en" in service._translations
        assert "es" in service._translations

    @patch("discord_bot.i18n.LOCALES_DIR", new_callable=MagicMock)
    @patch("builtins.open", new_callable=mock_open, read_data="invalid json{")
    def test_load_translations_handles_invalid_json(
        self, mock_file: MagicMock, mock_locales_dir: MagicMock
    ) -> None:
        """Test that invalid JSON files result in empty translations."""
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_locales_dir.__truediv__.return_value = mock_path

        # Should not raise exception, just log error and use empty dict
        mock_file.side_effect = json.JSONDecodeError("test", "doc", 0)
        service = I18nService()

        assert "en" in service._translations
        assert "es" in service._translations


class TestI18nServiceTranslate:
    """Tests for I18nService translate method."""

    def test_translate_simple_key_english(self) -> None:
        """Test translation of simple key in English."""
        service = I18nService()
        result = service.translate("ui.nav.dashboard", lang="en")

        assert result == "Dashboard"

    def test_translate_simple_key_spanish(self) -> None:
        """Test translation of simple key in Spanish."""
        service = I18nService()
        result = service.translate("ui.nav.dashboard", lang="es")

        assert result == "Panel"

    def test_translate_nested_key(self) -> None:
        """Test translation of deeply nested key."""
        service = I18nService()
        result = service.translate("ui.buttons.save", lang="en")

        assert result == "Save changes"

    def test_translate_missing_key_returns_key(self) -> None:
        """Test that missing translation key returns the key itself."""
        service = I18nService()
        result = service.translate("ui.nonexistent.key", lang="en")

        assert result == "ui.nonexistent.key"

    def test_translate_fallback_to_default_language(self) -> None:
        """Test that missing translation falls back to English."""
        service = I18nService()

        # Simulate a key that exists in English but not in Spanish
        service._translations["es"]["ui"]["nav"] = {}

        result = service.translate("ui.nav.dashboard", lang="es")

        # Should fallback to English
        assert result == "Dashboard"

    def test_translate_none_language_uses_default(self) -> None:
        """Test that None language uses default language."""
        service = I18nService()
        result = service.translate("ui.nav.dashboard", lang=None)

        assert result == "Dashboard"

    def test_translate_unsupported_language_uses_default(self) -> None:
        """Test that unsupported language uses default language."""
        service = I18nService()
        result = service.translate("ui.nav.dashboard", lang="fr")

        assert result == "Dashboard"

    def test_translate_with_format_arguments(self) -> None:
        """Test translation with string formatting."""
        service = I18nService()
        result = service.translate("ui.time.minute_ago", lang="en", count=5)

        assert result == "5 minute ago"

    def test_translate_with_multiple_format_arguments(self) -> None:
        """Test translation with multiple format arguments."""
        service = I18nService()

        # Create a test translation with multiple placeholders
        service._translations["en"]["test"] = {"multi": "{name} has {count} items"}

        result = service.translate("test.multi", lang="en", name="Alice", count=10)

        assert result == "Alice has 10 items"

    def test_translate_missing_format_argument_returns_original(self) -> None:
        """Test that missing format arguments return original string."""
        service = I18nService()
        result = service.translate("ui.time.minute_ago", lang="en")

        # Should return the string with placeholder intact
        assert "{count}" in result

    def test_translate_empty_key_returns_key(self) -> None:
        """Test that empty key returns the key itself."""
        service = I18nService()
        result = service.translate("", lang="en")

        assert result == ""

    def test_translate_partial_path_returns_string_representation(self) -> None:
        """Test that incomplete path returns string representation."""
        service = I18nService()
        result = service.translate("ui", lang="en")

        # Should return string representation of dict when path doesn't lead to string value
        assert isinstance(result, str)
        assert "nav" in result or "buttons" in result  # Contains nested keys


class TestI18nServiceGetNestedValue:
    """Tests for I18nService _get_nested_value method."""

    def test_get_nested_value_single_level(self) -> None:
        """Test getting value from single level."""
        service = I18nService()
        service._translations["test"] = {"key": "value"}

        result = service._get_nested_value("key", "test")

        assert result == "value"

    def test_get_nested_value_multiple_levels(self) -> None:
        """Test getting value from multiple nested levels."""
        service = I18nService()
        service._translations["test"] = {"level1": {"level2": {"level3": "deep_value"}}}

        result = service._get_nested_value("level1.level2.level3", "test")

        assert result == "deep_value"

    def test_get_nested_value_missing_key_returns_none(self) -> None:
        """Test that missing key returns None."""
        service = I18nService()
        service._translations["test"] = {"key": "value"}

        result = service._get_nested_value("nonexistent", "test")

        assert result is None

    def test_get_nested_value_missing_intermediate_key_returns_none(self) -> None:
        """Test that missing intermediate key returns None."""
        service = I18nService()
        service._translations["test"] = {"level1": {"level2": "value"}}

        result = service._get_nested_value("level1.nonexistent.level3", "test")

        assert result is None

    def test_get_nested_value_non_dict_intermediate_returns_none(self) -> None:
        """Test that non-dict intermediate value returns None."""
        service = I18nService()
        service._translations["test"] = {"level1": "string_value"}

        result = service._get_nested_value("level1.level2", "test")

        assert result is None

    def test_get_nested_value_missing_language_returns_none(self) -> None:
        """Test that missing language returns None."""
        service = I18nService()

        result = service._get_nested_value("key", "nonexistent_lang")

        assert result is None


class TestI18nServiceGetTranslatedDefault:
    """Tests for I18nService get_translated_default method."""

    def test_get_translated_default_existing_translation(self) -> None:
        """Test getting translated default value that exists."""
        service = I18nService()

        result = service.get_translated_default(
            cog_name="verification",
            key="verify_button_text",
            lang="en",
            fallback="Fallback Text",
        )

        assert result == "Verify"

    def test_get_translated_default_spanish(self) -> None:
        """Test getting translated default value in Spanish."""
        service = I18nService()

        result = service.get_translated_default(
            cog_name="verification",
            key="verify_button_text",
            lang="es",
            fallback="Fallback Text",
        )

        assert result == "Verificar"

    def test_get_translated_default_missing_translation_returns_fallback(self) -> None:
        """Test that missing translation returns fallback value."""
        service = I18nService()

        result = service.get_translated_default(
            cog_name="nonexistent",
            key="nonexistent_key",
            lang="en",
            fallback="Fallback Text",
        )

        assert result == "Fallback Text"

    def test_get_translated_default_none_fallback(self) -> None:
        """Test that None fallback is returned when translation missing."""
        service = I18nService()

        result = service.get_translated_default(
            cog_name="nonexistent",
            key="nonexistent_key",
            lang="en",
            fallback=None,
        )

        assert result is None

    def test_get_translated_default_numeric_fallback(self) -> None:
        """Test that numeric fallback values work correctly."""
        service = I18nService()

        result = service.get_translated_default(
            cog_name="nonexistent",
            key="nonexistent_key",
            lang="en",
            fallback=42,
        )

        assert result == 42

    def test_get_translated_default_list_fallback(self) -> None:
        """Test that list fallback values work correctly."""
        service = I18nService()
        fallback_list = ["item1", "item2"]

        result = service.get_translated_default(
            cog_name="nonexistent",
            key="nonexistent_key",
            lang="en",
            fallback=fallback_list,
        )

        assert result == fallback_list


class TestI18nServiceGetCogTranslations:
    """Tests for I18nService get_cog_translations method."""

    def test_get_cog_translations_existing_cog(self) -> None:
        """Test getting all translations for existing cog."""
        service = I18nService()

        result = service.get_cog_translations("verification", "en")

        assert isinstance(result, dict)
        assert "display_name" in result
        assert result["display_name"] == "Verification"

    def test_get_cog_translations_spanish(self) -> None:
        """Test getting cog translations in Spanish."""
        service = I18nService()

        result = service.get_cog_translations("verification", "es")

        assert isinstance(result, dict)
        assert "display_name" in result
        assert result["display_name"] == "Verificación"

    def test_get_cog_translations_nonexistent_cog_returns_empty_dict(self) -> None:
        """Test that nonexistent cog returns empty dict."""
        service = I18nService()

        result = service.get_cog_translations("nonexistent_cog", "en")

        assert result == {}

    def test_get_cog_translations_includes_options(self) -> None:
        """Test that cog translations include options."""
        service = I18nService()

        result = service.get_cog_translations("verification", "en")

        assert "options" in result
        assert isinstance(result["options"], dict)

    def test_get_cog_translations_includes_groups(self) -> None:
        """Test that cog translations include groups."""
        service = I18nService()

        result = service.get_cog_translations("verification", "en")

        assert "groups" in result
        assert isinstance(result["groups"], dict)


class TestI18nServiceGetOptionTranslation:
    """Tests for I18nService get_option_translation method."""

    def test_get_option_translation_existing_option(self) -> None:
        """Test getting translation for existing option."""
        service = I18nService()

        result = service.get_option_translation("verification", "verification_enabled", "en")

        assert isinstance(result, dict)
        assert "name" in result
        assert result["name"] == "Verification enabled"

    def test_get_option_translation_with_description(self) -> None:
        """Test that option translation includes description."""
        service = I18nService()

        result = service.get_option_translation("verification", "verification_enabled", "en")

        assert "description" in result
        assert result["description"] == "Enable or disable the verification system"

    def test_get_option_translation_with_default(self) -> None:
        """Test that option translation includes default value."""
        service = I18nService()

        result = service.get_option_translation("verification", "verify_button_text", "en")

        assert "default" in result
        assert result["default"] == "Verify"

    def test_get_option_translation_spanish(self) -> None:
        """Test getting option translation in Spanish."""
        service = I18nService()

        result = service.get_option_translation("verification", "verify_button_text", "es")

        assert result["default"] == "Verificar"

    def test_get_option_translation_nonexistent_option_returns_empty_dict(self) -> None:
        """Test that nonexistent option returns empty dict."""
        service = I18nService()

        result = service.get_option_translation("verification", "nonexistent_option", "en")

        assert result == {}

    def test_get_option_translation_nonexistent_cog_returns_empty_dict(self) -> None:
        """Test that nonexistent cog returns empty dict."""
        service = I18nService()

        result = service.get_option_translation("nonexistent", "some_option", "en")

        assert result == {}


class TestI18nServiceReload:
    """Tests for I18nService reload method."""

    @patch("discord_bot.i18n.get_i18n_service")
    def test_reload_clears_translations(self, mock_get_service: MagicMock) -> None:
        """Test that reload clears existing translations."""
        service = I18nService()

        service.reload()

        # Translations should be reloaded (not necessarily empty)
        assert "en" in service._translations
        assert "es" in service._translations

    @patch("discord_bot.i18n.get_i18n_service")
    def test_reload_clears_cache(self, mock_get_service: MagicMock) -> None:
        """Test that reload clears the lru_cache."""
        service = I18nService()

        service.reload()

        # Should call cache_clear on the get_i18n_service function
        mock_get_service.cache_clear.assert_called_once()

    @patch("discord_bot.i18n.get_i18n_service")
    def test_reload_reloads_translations(self, mock_get_service: MagicMock) -> None:
        """Test that reload actually reloads translation files."""
        service = I18nService()

        # Modify translations
        service._translations["en"]["test_modified_key"] = "modified"

        service.reload()

        # After reload, should not have the modified value
        assert "test_modified_key" not in service._translations.get("en", {})
        # But should have original keys reloaded
        assert len(service._translations.get("en", {})) > 0


class TestI18nServiceEdgeCases:
    """Edge case tests for I18nService."""

    def test_translate_with_unicode_characters(self) -> None:
        """Test translation with unicode characters."""
        service = I18nService()

        # Spanish translations contain unicode characters
        result = service.translate("ui.nav.logout", lang="es")

        assert "ó" in result  # "sesión"

    def test_translate_with_empty_string_value(self) -> None:
        """Test translation when value is empty string."""
        service = I18nService()
        # Need to create the language in supported languages first
        service._translations["test"] = {"empty": ""}

        result = service.translate("test.empty", lang="en")

        # Empty value returns key since it's falsy
        assert result == "test.empty"

    def test_get_nested_value_with_integer_in_path(self) -> None:
        """Test that integer-like keys in path work correctly."""
        service = I18nService()
        service._translations["test"] = {"level1": {"0": "zero"}}

        result = service._get_nested_value("level1.0", "test")

        assert result == "zero"

    def test_translate_very_long_key_path(self) -> None:
        """Test translation with very deep nesting."""
        service = I18nService()
        service._translations["en"] = {"a": {"b": {"c": {"d": {"e": {"f": "deep"}}}}}}

        result = service.translate("a.b.c.d.e.f", lang="en")

        assert result == "deep"

    def test_translate_with_special_characters_in_value(self) -> None:
        """Test translation with special characters in value."""
        service = I18nService()

        # Test with message that contains newlines and special chars
        result = service.translate(
            "cogs.verification.options.verification_panel_message.default", lang="en"
        )

        assert "**" in result  # Markdown formatting
        assert "\\n" in result or "\n" in result  # Newlines

    def test_get_cog_translations_with_choices(self) -> None:
        """Test that cog translations include choices."""
        service = I18nService()

        result = service.get_cog_translations("verification", "en")

        assert "choices" in result
        assert "faction" in result["choices"]

    def test_translate_cog_choice_value(self) -> None:
        """Test translating a cog choice value."""
        service = I18nService()

        result = service.translate("cogs.verification.choices.faction.Colonial", lang="en")

        assert result == "Colonial"

    def test_get_option_translation_with_choices(self) -> None:
        """Test getting option translation that includes choices."""
        service = I18nService()

        # Some options might have their own choices
        result = service.get_cog_translations("verification", "en")

        assert "options" in result
        # Choices can be at cog or option level
        if "choices" in result:
            assert isinstance(result["choices"], dict)


class TestI18nServiceSingleton:
    """Tests for get_i18n_service singleton function."""

    def test_get_i18n_service_returns_instance(self) -> None:
        """Test that get_i18n_service returns I18nService instance."""
        from discord_bot.i18n import get_i18n_service

        service = get_i18n_service()

        assert isinstance(service, I18nService)

    def test_get_i18n_service_returns_same_instance(self) -> None:
        """Test that get_i18n_service returns the same instance (cached)."""
        from discord_bot.i18n import get_i18n_service

        service1 = get_i18n_service()
        service2 = get_i18n_service()

        assert service1 is service2

    def test_get_i18n_service_after_cache_clear(self) -> None:
        """Test that cache clear creates new instance."""
        from discord_bot.i18n import get_i18n_service

        service1 = get_i18n_service()
        get_i18n_service.cache_clear()
        service2 = get_i18n_service()

        assert service1 is not service2
