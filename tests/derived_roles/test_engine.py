"""Tests for the derived roles rule engine."""

from typing import Any

from discord_bot.derived_roles.engine import MAX_PASSES, RuleType, compute_role_changes

COLLIE = 100
WARDEN = 200
LOGI_COLLIE = 101
SQUAD_COLLIE = 102
LOGI_WARDEN = 201


def _rule(trigger: int, rule_type: str, target: int) -> dict[str, Any]:
    """Build a rule row like the config table stores it."""
    return {"trigger_role": trigger, "rule_type": rule_type, "target_role": target}


class TestImplies:
    """Tests for the 'implies' invariant (has trigger -> must have target)."""

    def test_adds_target_when_trigger_present(self) -> None:
        """Member with trigger but without target gets the target added."""
        rules = [_rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE)]

        to_add, to_remove = compute_role_changes(member_role_ids={COLLIE}, rules=rules)

        assert to_add == {LOGI_COLLIE}
        assert to_remove == set()

    def test_noop_when_invariant_satisfied(self) -> None:
        """No changes when member already has trigger and target."""
        rules = [_rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE)]

        to_add, to_remove = compute_role_changes(member_role_ids={COLLIE, LOGI_COLLIE}, rules=rules)

        assert to_add == set()
        assert to_remove == set()

    def test_noop_when_trigger_absent(self) -> None:
        """No changes when member lacks the trigger."""
        rules = [_rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE)]

        to_add, to_remove = compute_role_changes(member_role_ids={WARDEN}, rules=rules)

        assert to_add == set()
        assert to_remove == set()

    def test_cascade_of_implies(self) -> None:
        """A implies B and B implies C: gaining A adds both B and C."""
        rules = [
            _rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE),
            _rule(LOGI_COLLIE, RuleType.IMPLIES, SQUAD_COLLIE),
        ]

        to_add, to_remove = compute_role_changes(member_role_ids={COLLIE}, rules=rules)

        assert to_add == {LOGI_COLLIE, SQUAD_COLLIE}
        assert to_remove == set()


class TestRequires:
    """Tests for the 'requires' invariant (lacks trigger -> must lack target)."""

    def test_removes_target_when_trigger_absent(self) -> None:
        """Member holding a dependent role without its trigger loses it."""
        rules = [_rule(COLLIE, RuleType.REQUIRES, LOGI_COLLIE)]

        to_add, to_remove = compute_role_changes(member_role_ids={LOGI_COLLIE}, rules=rules)

        assert to_add == set()
        assert to_remove == {LOGI_COLLIE}

    def test_keeps_target_when_trigger_present(self) -> None:
        """Dependent role is kept while the trigger is held."""
        rules = [_rule(COLLIE, RuleType.REQUIRES, LOGI_COLLIE)]

        to_add, to_remove = compute_role_changes(member_role_ids={COLLIE, LOGI_COLLIE}, rules=rules)

        assert to_add == set()
        assert to_remove == set()

    def test_does_not_auto_add_target(self) -> None:
        """'requires' never adds the target, only removes it."""
        rules = [_rule(COLLIE, RuleType.REQUIRES, LOGI_COLLIE)]

        to_add, to_remove = compute_role_changes(member_role_ids={COLLIE}, rules=rules)

        assert to_add == set()
        assert to_remove == set()


class TestIncompatible:
    """Tests for the 'incompatible' invariant (has trigger -> must lack target)."""

    def test_removes_target_when_trigger_present(self) -> None:
        """Incompatible role is removed while the trigger is held."""
        rules = [_rule(WARDEN, RuleType.INCOMPATIBLE, COLLIE)]

        to_add, to_remove = compute_role_changes(member_role_ids={WARDEN, COLLIE}, rules=rules)

        assert to_add == set()
        assert to_remove == {COLLIE}

    def test_noop_when_target_absent(self) -> None:
        """No changes when the incompatible role is not held."""
        rules = [_rule(WARDEN, RuleType.INCOMPATIBLE, COLLIE)]

        to_add, to_remove = compute_role_changes(member_role_ids={WARDEN}, rules=rules)

        assert to_add == set()
        assert to_remove == set()


class TestConflictResolution:
    """Tests for conflict resolution between rules."""

    def test_remove_wins_over_add_in_same_pass(self) -> None:
        """When one rule adds X and another removes X, removal wins."""
        rules = [
            _rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE),
            _rule(WARDEN, RuleType.INCOMPATIBLE, LOGI_COLLIE),
        ]

        to_add, to_remove = compute_role_changes(member_role_ids={COLLIE, WARDEN}, rules=rules)

        assert LOGI_COLLIE not in to_add

    def test_faction_switch_cascades_removals(self) -> None:
        """Gaining Warden removes Collie and all Collie-dependent roles."""
        rules = [
            _rule(WARDEN, RuleType.INCOMPATIBLE, COLLIE),
            _rule(COLLIE, RuleType.REQUIRES, LOGI_COLLIE),
            _rule(COLLIE, RuleType.REQUIRES, SQUAD_COLLIE),
            _rule(WARDEN, RuleType.IMPLIES, LOGI_WARDEN),
        ]

        to_add, to_remove = compute_role_changes(
            member_role_ids={WARDEN, COLLIE, LOGI_COLLIE, SQUAD_COLLIE}, rules=rules
        )

        assert to_remove == {COLLIE, LOGI_COLLIE, SQUAD_COLLIE}
        assert to_add == {LOGI_WARDEN}

    def test_pass_limit_terminates(self) -> None:
        """Pathological rules terminate within the pass limit."""
        # A implies B, B incompatible A: converges to {B} in a couple of passes
        rules = [
            _rule(COLLIE, RuleType.IMPLIES, WARDEN),
            _rule(WARDEN, RuleType.INCOMPATIBLE, COLLIE),
        ]

        to_add, to_remove = compute_role_changes(member_role_ids={COLLIE}, rules=rules)

        assert to_add == {WARDEN}
        assert to_remove == {COLLIE}

    def test_max_passes_is_bounded(self) -> None:
        """The pass limit constant is a small positive number."""
        assert 1 <= MAX_PASSES <= 100


class TestRobustness:
    """Tests for malformed input handling."""

    def test_ignores_malformed_rows(self) -> None:
        """Rows with missing or invalid fields are skipped."""
        rules: list[dict[str, Any]] = [
            {"trigger_role": None, "rule_type": "implies", "target_role": LOGI_COLLIE},
            {"rule_type": "implies", "target_role": LOGI_COLLIE},
            {"trigger_role": COLLIE, "rule_type": "bogus", "target_role": LOGI_COLLIE},
            {"trigger_role": "not-a-number", "rule_type": "implies", "target_role": LOGI_COLLIE},
            _rule(COLLIE, RuleType.IMPLIES, SQUAD_COLLIE),
        ]

        to_add, to_remove = compute_role_changes(member_role_ids={COLLIE}, rules=rules)

        assert to_add == {SQUAD_COLLIE}
        assert to_remove == set()

    def test_accepts_string_role_ids(self) -> None:
        """Role IDs stored as strings (from JSON) are converted."""
        rules = [
            {"trigger_role": str(COLLIE), "rule_type": "implies", "target_role": str(LOGI_COLLIE)}
        ]

        to_add, to_remove = compute_role_changes(member_role_ids={COLLIE}, rules=rules)

        assert to_add == {LOGI_COLLIE}
        assert to_remove == set()

    def test_empty_rules_is_noop(self) -> None:
        """No rules means no changes."""
        to_add, to_remove = compute_role_changes(member_role_ids={COLLIE}, rules=[])

        assert to_add == set()
        assert to_remove == set()

    def test_does_not_mutate_input(self) -> None:
        """The input role set is not mutated."""
        member_role_ids = {COLLIE}
        rules = [_rule(COLLIE, RuleType.IMPLIES, LOGI_COLLIE)]

        compute_role_changes(member_role_ids=member_role_ids, rules=rules)

        assert member_role_ids == {COLLIE}
