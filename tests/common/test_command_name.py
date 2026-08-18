"""Tests for the slash command name helpers."""

import logging

import pytest

from discord_bot.common.utils.command_name import (
    normalize_command_name,
    resolve_command_name,
    validate_command_name,
)

DECOMPOSED_ENYE = "an\u0303adir_stockpile"  # n + combining tilde, as pasted from some editors
PRECOMPOSED_ENYE = "a\u00f1adir_stockpile"


class TestNormalizeCommandName:
    """Tests for normalize_command_name."""

    def test_composes_unicode_and_strips_whitespace(self) -> None:
        """Decomposed accents are composed and surrounding whitespace is dropped."""
        assert normalize_command_name(f"  {DECOMPOSED_ENYE} ") == PRECOMPOSED_ENYE

    def test_keeps_valid_names_untouched(self) -> None:
        """A plain valid name is returned as-is."""
        assert normalize_command_name("stockpile_add") == "stockpile_add"


class TestValidateCommandName:
    """Tests for validate_command_name."""

    @pytest.mark.parametrize(
        "name",
        ["stockpile_add", "purge-war", "abc123", PRECOMPOSED_ENYE, DECOMPOSED_ENYE, "  ok_name "],
    )
    def test_accepts_valid_names(self, name: str) -> None:
        """Lowercase letters, digits, hyphens and underscores (after normalization) pass."""
        assert validate_command_name(name) is None

    def test_accepts_empty_as_use_default(self) -> None:
        """An empty value means "use the default name" and is not an error."""
        assert validate_command_name("") is None
        assert validate_command_name("   ") is None

    @pytest.mark.parametrize(
        "name",
        [
            "Añadir_stockpile",
            "añadir stockpile",
            "/añadir_stockpile",
            "stockpile.add",
            "a" * 33,
        ],
    )
    def test_rejects_invalid_names(self, name: str) -> None:
        """Uppercase, spaces, slashes, punctuation and long names are rejected with a hint."""
        error = validate_command_name(name)

        assert error is not None
        assert "lowercase" in error

    def test_rejects_non_strings(self) -> None:
        """Non-string values are rejected."""
        assert validate_command_name(123) is not None


class TestResolveCommandName:
    """Tests for resolve_command_name."""

    def test_returns_normalized_configured_name(self) -> None:
        """A valid configured name wins, normalized."""
        result = resolve_command_name(
            configured=f" {DECOMPOSED_ENYE} ", default="stockpile_add", guild_name="G"
        )

        assert result == PRECOMPOSED_ENYE

    def test_falls_back_to_default_when_empty(self) -> None:
        """Empty or missing values resolve to the default silently."""
        assert (
            resolve_command_name(configured="", default="stockpile_add", guild_name="G")
            == "stockpile_add"
        )
        assert (
            resolve_command_name(configured=None, default="stockpile_add", guild_name="G")
            == "stockpile_add"
        )

    def test_falls_back_to_default_when_invalid(self, caplog: pytest.LogCaptureFixture) -> None:
        """An invalid stored name falls back to the default and logs the reason."""
        with caplog.at_level(logging.WARNING):
            result = resolve_command_name(
                configured="Añadir_stockpile", default="stockpile_add", guild_name="Guild"
            )

        assert result == "stockpile_add"
        assert "[Guild]" in caplog.text
        assert "Añadir_stockpile" in caplog.text
        assert "stockpile_add" in caplog.text
