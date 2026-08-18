"""Tests for the slash command name helpers."""

import logging
from unittest.mock import MagicMock

import pytest

from discord_bot.common.utils.command_name import (
    choose_command_name,
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


def _tree(taken: set[str]) -> MagicMock:
    """Command tree stub where ``taken`` names already belong to another command.

    Args:
        taken (set[str]): Names that ``get_command`` reports as registered.

    Returns:
        MagicMock: Tree with ``get_command`` configured.
    """
    tree = MagicMock()
    tree.get_command = MagicMock(
        side_effect=lambda name, guild=None: MagicMock() if name in taken else None
    )
    return tree


class TestChooseCommandName:
    """Tests for choose_command_name (validation + collision check)."""

    def test_returns_configured_name_when_free(self) -> None:
        """A valid, unused configured name is chosen."""
        guild = MagicMock(name="guild")
        guild.name = "G"

        result = choose_command_name(
            tree=_tree(set()), guild=guild, configured="ver_stockpile", default="stockpile_show"
        )

        assert result == "ver_stockpile"

    def test_keeps_current_name_even_if_registered(self) -> None:
        """The name this command already holds is not treated as a collision."""
        guild = MagicMock()
        guild.name = "G"

        result = choose_command_name(
            tree=_tree({"ver_stockpile"}),
            guild=guild,
            configured="ver_stockpile",
            default="stockpile_show",
            current="ver_stockpile",
        )

        assert result == "ver_stockpile"

    def test_falls_back_to_default_on_collision(self, caplog: pytest.LogCaptureFixture) -> None:
        """A name used by another command falls back to the default with a warning."""
        guild = MagicMock()
        guild.name = "Guild"

        with caplog.at_level(logging.WARNING):
            result = choose_command_name(
                tree=_tree({"purge_war"}),
                guild=guild,
                configured="purge_war",
                default="stockpile_add",
            )

        assert result == "stockpile_add"
        assert "[Guild]" in caplog.text and "purge_war" in caplog.text

    def test_returns_none_when_default_is_taken_too(self, caplog: pytest.LogCaptureFixture) -> None:
        """When even the default collides nothing can be registered."""
        guild = MagicMock()
        guild.name = "Guild"

        with caplog.at_level(logging.ERROR):
            result = choose_command_name(
                tree=_tree({"purge_war", "stockpile_add"}),
                guild=guild,
                configured="purge_war",
                default="stockpile_add",
            )

        assert result is None
        assert "stockpile_add" in caplog.text
