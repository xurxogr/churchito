"""Tests for derived roles translations in the web panel locales."""

import json
from pathlib import Path
from typing import Any

import pytest

from discord_bot.derived_roles.config import COG_NAME, DERIVED_ROLES_CONFIG_SCHEMA, ConfigKey
from discord_bot.i18n import I18nService
from discord_bot.i18n.schema_translator import SchemaTranslator

LOCALES_DIR = Path("discord_bot/i18n/locales")

TEXTAREA_MESSAGE_KEYS = [
    ConfigKey.AUDIT_APPLIED_MSG,
    ConfigKey.AUDIT_ERROR_MSG,
    ConfigKey.AUDIT_RECOVERED_MSG,
    ConfigKey.AUDIT_RECONCILIATION_MSG,
]


def _load_cog_block(lang: str) -> dict[str, Any]:
    """Load the derived_roles translation block from a locale file.

    Args:
        lang (str): Language code

    Returns:
        dict[str, Any]: The cogs.derived_roles block, empty if missing
    """
    with open(LOCALES_DIR / f"{lang}.json", encoding="utf-8") as f:
        data = json.load(f)
    block: dict[str, Any] = data.get("cogs", {}).get(COG_NAME, {})
    return block


class TestLocaleCompleteness:
    """The derived_roles cog must be translated in every supported language."""

    @pytest.mark.parametrize("lang", list(I18nService.SUPPORTED_LANGUAGES))
    def test_cog_block_exists(self, lang: str) -> None:
        """Each locale file has a cogs.derived_roles block."""
        block = _load_cog_block(lang)

        assert block, f"cogs.{COG_NAME} missing in {lang}.json"
        assert block.get("display_name")
        assert block.get("description")

    @pytest.mark.parametrize("lang", list(I18nService.SUPPORTED_LANGUAGES))
    def test_all_options_translated(self, lang: str) -> None:
        """Every schema option has name and description in each locale."""
        options = _load_cog_block(lang).get("options", {})

        for option in DERIVED_ROLES_CONFIG_SCHEMA.options:
            assert option.key in options, f"{option.key} missing in {lang}.json"
            assert options[option.key].get("name"), f"{option.key}.name missing in {lang}.json"
            assert options[option.key].get("description"), (
                f"{option.key}.description missing in {lang}.json"
            )

    @pytest.mark.parametrize("lang", list(I18nService.SUPPORTED_LANGUAGES))
    def test_all_groups_translated(self, lang: str) -> None:
        """Every option group has a translation in each locale."""
        groups = _load_cog_block(lang).get("groups", {})
        schema_groups = {
            option.group for option in DERIVED_ROLES_CONFIG_SCHEMA.options if option.group
        }

        for group in schema_groups:
            assert group in groups, f"group '{group}' missing in {lang}.json"

    @pytest.mark.parametrize("lang", list(I18nService.SUPPORTED_LANGUAGES))
    def test_all_table_columns_translated(self, lang: str) -> None:
        """Every table column has a translation in each locale."""
        columns = _load_cog_block(lang).get("columns", {})

        for option in DERIVED_ROLES_CONFIG_SCHEMA.options:
            for column in option.columns or []:
                assert column["key"] in columns, f"column {column['key']} missing in {lang}.json"

    @pytest.mark.parametrize("lang", list(I18nService.SUPPORTED_LANGUAGES))
    def test_all_column_choice_labels_translated(self, lang: str) -> None:
        """Every choice label used in table columns has a translation in each locale."""
        choices_nested = _load_cog_block(lang).get("choices", {})
        translated_labels: set[str] = set()
        for category in choices_nested.values():
            translated_labels.update(category)

        for option in DERIVED_ROLES_CONFIG_SCHEMA.options:
            for column in option.columns or []:
                for label, _value in column.get("choices", []):
                    assert label in translated_labels, (
                        f"choice label '{label}' missing in {lang}.json"
                    )

    def test_textarea_defaults_have_spanish_translations(self) -> None:
        """Audit message defaults are translated so the default migrator can swap them."""
        options = _load_cog_block("es").get("options", {})

        for key in TEXTAREA_MESSAGE_KEYS:
            assert options.get(key, {}).get("default"), f"{key}.default missing in es.json"


class TestSchemaTranslation:
    """The schema translator must produce Spanish labels for the panel."""

    def test_schema_translates_to_spanish(self) -> None:
        """Display name and rules option are translated to Spanish."""
        translator = SchemaTranslator()

        result = translator.translate_schema(DERIVED_ROLES_CONFIG_SCHEMA, "es")

        assert result["display_name"] == "Roles Derivados"
        rules = next(opt for opt in result["options"] if opt["key"] == ConfigKey.RULES)
        assert rules["name"] == "Reglas"

    def test_rule_type_choices_translate_to_spanish(self) -> None:
        """The rule type dropdown inside the rules table is translated to Spanish."""
        translator = SchemaTranslator()

        result = translator.translate_schema(DERIVED_ROLES_CONFIG_SCHEMA, "es")

        rules = next(opt for opt in result["options"] if opt["key"] == ConfigKey.RULES)
        rule_type_col = next(col for col in rules["columns"] if col["key"] == "rule_type")
        labels = [label for label, _value in rule_type_col["choices"]]
        values = [value for _label, value in rule_type_col["choices"]]

        schema_rules = next(
            option
            for option in DERIVED_ROLES_CONFIG_SCHEMA.options
            if option.key == ConfigKey.RULES
        )
        schema_col = next(col for col in schema_rules.columns or [] if col["key"] == "rule_type")
        english_labels = [label for label, _value in schema_col["choices"]]

        assert values == ["implies", "requires", "incompatible"]
        for english_label in english_labels:
            assert english_label not in labels
