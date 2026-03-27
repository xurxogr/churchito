"""Internationalization (i18n) module for web dashboard."""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LOCALES_DIR = Path(__file__).parent / "locales"


class I18nService:
    """Service for handling translations in the web dashboard."""

    SUPPORTED_LANGUAGES: dict[str, str] = {"en": "English", "es": "Español"}
    DEFAULT_LANGUAGE: str = "en"

    def __init__(self) -> None:
        """Initialize the i18n service and load all locale files."""
        self._translations: dict[str, dict[str, Any]] = {}
        self._load_translations()

    def _load_translations(self) -> None:
        """Load all translation files from the locales directory."""
        for lang_code in self.SUPPORTED_LANGUAGES:
            locale_file = LOCALES_DIR / f"{lang_code}.json"
            if locale_file.exists():
                try:
                    with open(locale_file, encoding="utf-8") as f:
                        self._translations[lang_code] = json.load(f)
                    logger.debug(f"Loaded translations for {lang_code}")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse {locale_file}: {e}")
                    self._translations[lang_code] = {}
            else:
                logger.warning(f"Locale file not found: {locale_file}")
                self._translations[lang_code] = {}

    def translate(
        self,
        key: str,
        lang: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Translate a key to the specified language.

        Args:
            key: Dot-separated key (e.g., 'ui.nav.logout')
            lang: Language code (defaults to DEFAULT_LANGUAGE)
            **kwargs: Format arguments for string interpolation

        Returns:
            str: Translated string or key if not found
        """
        if lang is None or lang not in self.SUPPORTED_LANGUAGES:
            lang = self.DEFAULT_LANGUAGE

        value = self._get_nested_value(key, lang)

        # Fallback to default language if not found
        if value is None and lang != self.DEFAULT_LANGUAGE:
            value = self._get_nested_value(key, self.DEFAULT_LANGUAGE)

        # Return key if still not found
        if value is None:
            logger.debug(f"Translation not found: {key} ({lang})")
            return key

        # Apply string formatting if kwargs provided
        if kwargs and isinstance(value, str):
            try:
                return value.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Missing format key {e} in translation: {key}")
                return value

        return str(value)

    def _get_nested_value(self, key: str, lang: str) -> Any | None:
        """Get a nested value from translations using dot notation.

        Args:
            key: Dot-separated key path
            lang: Language code

        Returns:
            The value at the key path, or None if not found
        """
        translations = self._translations.get(lang, {})
        parts = key.split(".")
        current: Any = translations

        for part in parts:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
            if current is None:
                return None

        return current

    def get_translated_default(
        self,
        cog_name: str,
        key: str,
        lang: str,
        fallback: Any,
    ) -> Any:
        """Get a translated default value for a config option.

        Args:
            cog_name: Name of the cog (e.g., 'verification')
            key: Config option key
            lang: Language code
            fallback: Value to return if no translation found

        Returns:
            Translated default value or fallback
        """
        translation_key = f"cogs.{cog_name}.options.{key}.default"
        value = self._get_nested_value(translation_key, lang)

        if value is None:
            return fallback

        return value

    def get_cog_translations(self, cog_name: str, lang: str) -> dict[str, Any]:
        """Get all translations for a specific cog.

        Args:
            cog_name: Name of the cog
            lang: Language code

        Returns:
            dict: All translations for the cog
        """
        translation_key = f"cogs.{cog_name}"
        value = self._get_nested_value(translation_key, lang)
        return value if isinstance(value, dict) else {}

    def get_option_translation(
        self,
        cog_name: str,
        option_key: str,
        lang: str,
    ) -> dict[str, str]:
        """Get translations for a specific config option.

        Args:
            cog_name: Name of the cog
            option_key: Config option key
            lang: Language code

        Returns:
            dict: Option translations (name, description, default)
        """
        translation_key = f"cogs.{cog_name}.options.{option_key}"
        value = self._get_nested_value(translation_key, lang)
        return value if isinstance(value, dict) else {}

    def reload(self) -> None:
        """Reload all translation files."""
        self._translations.clear()
        self._load_translations()
        # Clear cached service
        get_i18n_service.cache_clear()
        logger.info("Translations reloaded")


@lru_cache(maxsize=1)
def get_i18n_service() -> I18nService:
    """Get or create the singleton I18nService instance.

    Returns:
        I18nService: The shared i18n service instance
    """
    return I18nService()
