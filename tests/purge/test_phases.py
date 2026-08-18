"""Tests for the pure helpers in discord_bot/purge/phases.py."""

from unittest.mock import MagicMock

from discord_bot.purge.enums import ConfigKey
from discord_bot.purge.phases import PhaseContext, _append_log, build_promotion_map


def _context(config: dict, audit_level: int) -> PhaseContext:
    """Build a phase context with mocked live objects.

    Args:
        config (dict): Cog configuration.
        audit_level (int): Audit level.

    Returns:
        PhaseContext: Context with an empty execution log.
    """
    return PhaseContext(
        cog=MagicMock(),
        guild=MagicMock(),
        record=MagicMock(),
        config=config,
        audit_level=audit_level,
        execution_logs=[],
    )


class TestBuildPromotionMap:
    """Promotion list → from_role_id → to_role_id map."""

    def test_maps_int_and_legacy_string_ids(self) -> None:
        """String IDs from legacy data are coerced to int."""
        promotions = [
            {"from_role": 1, "to_role": 2},
            {"from_role": "3", "to_role": "4"},
        ]

        assert build_promotion_map(promotions) == {1: 2, 3: 4}

    def test_skips_incomplete_entries(self) -> None:
        """Entries missing either side are ignored."""
        promotions = [{"from_role": 1}, {"to_role": 2}, {"from_role": 0, "to_role": 5}, {}]

        assert build_promotion_map(promotions) == {}

    def test_last_duplicate_wins(self) -> None:
        """A repeated from_role keeps the last target."""
        promotions = [{"from_role": 1, "to_role": 2}, {"from_role": 1, "to_role": 3}]

        assert build_promotion_map(promotions) == {1: 3}


class TestAppendLog:
    """Audit-gated log lines."""

    def test_appends_formatted_line_when_level_reached(self) -> None:
        """The configured template is formatted and appended."""
        config = {ConfigKey.EXEC_MSG_PROMOTION_DEFAULT: "Default {role}"}
        ctx = _context(config=config, audit_level=2)

        _append_log(
            ctx=ctx,
            min_level=2,
            key=ConfigKey.EXEC_MSG_PROMOTION_DEFAULT,
            default="unused {role}",
            role="Member",
        )

        assert list(ctx.execution_logs) == ["Default Member"]

    def test_uses_default_template_when_not_configured(self) -> None:
        """Without a configured template the default is used."""
        ctx = _context(config={}, audit_level=1)

        _append_log(
            ctx=ctx,
            min_level=1,
            key=ConfigKey.EXEC_MSG_CLEANING_START,
            default="Start {role}",
            role="X",
        )

        assert list(ctx.execution_logs) == ["Start X"]

    def test_skips_below_audit_level(self) -> None:
        """Nothing is appended when the audit level is too low."""
        ctx = _context(config={}, audit_level=1)

        _append_log(ctx=ctx, min_level=2, key=ConfigKey.EXEC_MSG_CLEANING_ROLE, default="x")

        assert list(ctx.execution_logs) == []
