"""Tests for the derived roles rule validator."""

from typing import Any

from discord_bot.derived_roles.engine import RuleType
from discord_bot.derived_roles.validator import find_rule_conflicts, validate_rules

COLLIE = 100
WARDEN = 200
LOGI_COLLIE = 101
LOGI_WARDEN = 201


def _rule(trigger: int, rule_type: str, target: int) -> dict[str, Any]:
    """Build a rule row like the config table stores it."""
    return {"trigger_role": trigger, "rule_type": rule_type, "target_role": target}


class TestValidRulesets:
    """Rulesets that must pass validation."""

    def test_empty_rules(self) -> None:
        """An empty ruleset is valid."""
        assert validate_rules([]) is None
        assert find_rule_conflicts([]) == []

    def test_faction_scenario(self) -> None:
        """A realistic faction setup passes validation."""
        rules = [
            _rule(WARDEN, RuleType.INCOMPATIBLE, COLLIE),
            _rule(COLLIE, RuleType.REQUIRES, LOGI_COLLIE),
            _rule(WARDEN, RuleType.IMPLIES, LOGI_WARDEN),
            _rule(WARDEN, RuleType.REQUIRES, LOGI_WARDEN),
        ]

        assert validate_rules(rules) is None

    def test_add_only_cycle_is_allowed(self) -> None:
        """A implies B and B implies A converges, so it is allowed."""
        rules = [
            _rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE),
            _rule(LOGI_COLLIE, RuleType.IMPLIES, COLLIE),
        ]

        assert validate_rules(rules) is None

    def test_implies_and_requires_same_pair_is_allowed(self) -> None:
        """A implies X plus X requires A is a coherent full sync."""
        rules = [
            _rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE),
            _rule(COLLIE, RuleType.REQUIRES, LOGI_COLLIE),
        ]

        assert validate_rules(rules) is None


class TestRowErrors:
    """Per-row validation errors."""

    def test_self_reference(self) -> None:
        """A role cannot derive from itself."""
        rules = [_rule(COLLIE, RuleType.IMPLIES, COLLIE)]

        error = validate_rules(rules)

        assert error is not None
        conflicts = find_rule_conflicts(rules)
        assert len(conflicts) == 1
        assert conflicts[0].rows == [1]

    def test_duplicate_rule(self) -> None:
        """Exact duplicate rows are rejected."""
        rules = [
            _rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE),
            _rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE),
        ]

        error = validate_rules(rules)

        assert error is not None
        conflicts = find_rule_conflicts(rules)
        assert conflicts[0].rows == [1, 2]


class TestContradictions:
    """Contradictory rule combinations."""

    def test_implies_and_incompatible_same_pair(self) -> None:
        """A cannot both grant and forbid the same target."""
        rules = [
            _rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE),
            _rule(COLLIE, RuleType.INCOMPATIBLE, LOGI_COLLIE),
        ]

        error = validate_rules(rules)

        assert error is not None

    def test_requires_and_incompatible_same_pair(self) -> None:
        """Target removed both with and without the trigger can never be held."""
        rules = [
            _rule(COLLIE, RuleType.REQUIRES, LOGI_COLLIE),
            _rule(COLLIE, RuleType.INCOMPATIBLE, LOGI_COLLIE),
        ]

        error = validate_rules(rules)

        assert error is not None

    def test_mutual_incompatibility(self) -> None:
        """A forbids B and B forbids A would strip both roles at once."""
        rules = [
            _rule(WARDEN, RuleType.INCOMPATIBLE, COLLIE),
            _rule(COLLIE, RuleType.INCOMPATIBLE, WARDEN),
        ]

        error = validate_rules(rules)

        assert error is not None
        conflicts = find_rule_conflicts(rules)
        assert conflicts[0].rows == [1, 2]

    def test_cross_trigger_contradiction_is_allowed(self) -> None:
        """A implies X while B forbids X is resolved at runtime (remove wins)."""
        rules = [
            _rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE),
            _rule(WARDEN, RuleType.INCOMPATIBLE, LOGI_COLLIE),
        ]

        assert validate_rules(rules) is None


class TestCascadeConflicts:
    """Cascade chains where gaining a role removes that same role."""

    def test_gain_removes_self_via_implies(self) -> None:
        """A grants B and B forbids A: gaining A ultimately removes A."""
        rules = [
            _rule(COLLIE, RuleType.IMPLIES, WARDEN),
            _rule(WARDEN, RuleType.INCOMPATIBLE, COLLIE),
        ]

        error = validate_rules(rules)

        assert error is not None

    def test_gain_removes_self_via_longer_chain(self) -> None:
        """A grants B, B grants C, C forbids A."""
        rules = [
            _rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE),
            _rule(LOGI_COLLIE, RuleType.IMPLIES, WARDEN),
            _rule(WARDEN, RuleType.INCOMPATIBLE, COLLIE),
        ]

        error = validate_rules(rules)

        assert error is not None

    def test_removal_cascade_alone_is_valid(self) -> None:
        """Chains of requires rules (removal propagation) are fine."""
        rules = [
            _rule(COLLIE, RuleType.REQUIRES, LOGI_COLLIE),
            _rule(LOGI_COLLIE, RuleType.REQUIRES, LOGI_WARDEN),
        ]

        assert validate_rules(rules) is None


class TestRobustness:
    """Malformed input handling."""

    def test_malformed_rows_are_reported(self) -> None:
        """Rows that cannot be parsed produce a validation error."""
        rules = [{"trigger_role": "abc", "rule_type": "implies", "target_role": LOGI_COLLIE}]

        error = validate_rules(rules)

        assert error is not None

    def test_error_message_mentions_roles(self) -> None:
        """Error messages reference roles as mentions for UI rendering."""
        rules = [_rule(COLLIE, RuleType.IMPLIES, COLLIE)]

        error = validate_rules(rules)

        assert error is not None
        assert f"<@&{COLLIE}>" in error
