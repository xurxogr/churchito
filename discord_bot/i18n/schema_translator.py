"""Schema translator for i18n support in config schemas."""

from typing import Any

from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.i18n import I18nService, get_i18n_service


class SchemaTranslator:
    """Translator for cog configuration schemas."""

    def __init__(self, i18n_service: I18nService | None = None) -> None:
        """Initialize the schema translator.

        Args:
            i18n_service: Optional I18nService instance (uses singleton if not provided)
        """
        self._i18n = i18n_service or get_i18n_service()

    def translate_schema(self, schema: CogConfigSchema, lang: str) -> dict[str, Any]:
        """Translate a cog config schema to a dictionary with translated labels.

        Args:
            schema: The cog configuration schema
            lang: Target language code

        Returns:
            dict: Schema dictionary with translated display_name, description, etc.
        """
        cog_name = schema.cog_name

        # Get cog-level translations
        cog_translations = self._i18n.get_cog_translations(cog_name, lang)

        # Build translated schema
        result: dict[str, Any] = {
            "cog_name": cog_name,
            "display_name": cog_translations.get("display_name", schema.display_name),
            "description": cog_translations.get("description", schema.description),
            "icon": schema.icon,
            "toggleable": schema.toggleable,
            "options": [],
        }

        # Get section and group translations
        sections_trans = cog_translations.get("sections", {})
        groups_trans = cog_translations.get("groups", {})

        # Translate each option
        for option in schema.options:
            translated_option = self._translate_option(
                cog_name=cog_name,
                option=option,
                lang=lang,
                sections_trans=sections_trans,
                groups_trans=groups_trans,
            )
            result["options"].append(translated_option)

        return result

    def _translate_option(
        self,
        cog_name: str,
        option: Any,
        lang: str,
        sections_trans: dict[str, str],
        groups_trans: dict[str, str],
    ) -> dict[str, Any]:
        """Translate a single config option.

        Args:
            cog_name: Name of the cog
            option: The ConfigOption to translate
            lang: Target language code
            sections_trans: Section name translations
            groups_trans: Group name translations

        Returns:
            dict: Translated option data
        """
        # Get option-specific translations
        option_trans = self._i18n.get_option_translation(cog_name, option.key, lang)

        # Build translated option
        translated: dict[str, Any] = {
            "key": option.key,
            "name": option_trans.get("name", option.name),
            "description": option_trans.get("description", option.description),
            "type": option.option_type.value,
            "default": option.default,
            "required": option.required,
            "min_value": option.min_value,
            "max_value": option.max_value,
            "max_length": option.max_length,
            "placeholders": option.placeholders,
        }

        # Translate section and group if present
        if option.section:
            translated["section"] = sections_trans.get(option.section, option.section)
        else:
            translated["section"] = None

        if option.group:
            translated["group"] = groups_trans.get(option.group, option.group)
        else:
            translated["group"] = None

        # Translate choices if present
        if option.choices:
            translated["choices"] = self._translate_choices(
                cog_name=cog_name,
                option_key=option.key,
                choices=option.choices,
                lang=lang,
            )
        else:
            translated["choices"] = None

        # Translate table columns if present
        if option.columns:
            translated["columns"] = self._translate_columns(
                cog_name=cog_name,
                columns=option.columns,
                lang=lang,
            )
        else:
            translated["columns"] = None

        return translated

    def _translate_choices(
        self,
        cog_name: str,
        option_key: str,
        choices: list[tuple[str, Any]],
        lang: str,
    ) -> list[tuple[str, Any]]:
        """Translate choice labels.

        Args:
            cog_name: Name of the cog
            option_key: Config option key
            choices: List of (label, value) tuples
            lang: Target language code

        Returns:
            list: Translated choices
        """
        # Try to get choice translations from cog
        cog_translations = self._i18n.get_cog_translations(cog_name, lang)
        choices_trans_nested = cog_translations.get("choices", {})

        # Flatten nested choices dict (e.g. {"faction": {"A": "A"}} -> {"A": "A"})
        choices_trans: dict[str, str] = {}
        for category_translations in choices_trans_nested.values():
            if isinstance(category_translations, dict):
                choices_trans.update(category_translations)

        # For specific option, check if there are option-specific translations
        option_trans = self._i18n.get_option_translation(cog_name, option_key, lang)
        option_choices_raw: str | dict[str, str] = (
            option_trans.get("choices", {}) if isinstance(option_trans, dict) else {}
        )
        option_choices_trans: dict[str, str] = (
            option_choices_raw if isinstance(option_choices_raw, dict) else {}
        )

        translated_choices: list[tuple[str, Any]] = []
        for label, value in choices:
            # Check option-specific translations first
            if label in option_choices_trans:
                translated_label = option_choices_trans[label]
            # Then check general cog choices (flattened)
            elif label in choices_trans:
                translated_label = choices_trans[label]
            else:
                # Fallback to original label
                translated_label = label
            translated_choices.append((translated_label, value))

        return translated_choices

    def _translate_columns(
        self,
        cog_name: str,
        columns: list[dict[str, Any]],
        lang: str,
    ) -> list[dict[str, Any]]:
        """Translate table column names.

        Args:
            cog_name: Name of the cog
            columns: List of column definitions
            lang: Target language code

        Returns:
            list: Translated column definitions
        """
        cog_translations = self._i18n.get_cog_translations(cog_name, lang)
        columns_trans = cog_translations.get("columns", {})

        translated_columns: list[dict[str, Any]] = []
        for col in columns:
            col_key = col.get("key", "")
            translated_col = col.copy()
            # Translate the 'name' field
            if col_key in columns_trans:
                translated_col["name"] = columns_trans[col_key]
            translated_columns.append(translated_col)

        return translated_columns

    def get_translated_default(
        self,
        cog_name: str,
        option_key: str,
        lang: str,
        original_default: Any,
    ) -> Any:
        """Get the translated default value for an option.

        Args:
            cog_name: Name of the cog
            option_key: Config option key
            lang: Target language code
            original_default: Original default value

        Returns:
            Translated default value or original if not found
        """
        return self._i18n.get_translated_default(
            cog_name=cog_name,
            key=option_key,
            lang=lang,
            fallback=original_default,
        )


def get_schema_translator() -> SchemaTranslator:
    """Get a SchemaTranslator instance.

    Returns:
        SchemaTranslator: A schema translator instance
    """
    return SchemaTranslator()
