"""Tests for the derived roles config schema."""

from discord_bot.derived_roles.config import DERIVED_ROLES_CONFIG_SCHEMA, ConfigKey


class TestRulesTableColumns:
    """The rules table must let the same role appear in multiple rows."""

    def test_role_columns_allow_duplicates(self) -> None:
        """Both role columns opt out of the table editor's used-role filtering.

        One trigger role commonly appears in many rules (e.g. one row per
        granted role), so the panel must not hide already-used roles.
        """
        rules_option = next(
            option
            for option in DERIVED_ROLES_CONFIG_SCHEMA.options
            if option.key == ConfigKey.RULES
        )

        role_columns = [col for col in rules_option.columns or [] if col["type"] == "role"]

        assert role_columns, "rules table must have role columns"
        for column in role_columns:
            assert column.get("allow_duplicates") is True, (
                f"column {column['key']} must allow duplicates"
            )
