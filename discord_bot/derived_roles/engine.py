"""Pure rule engine for the derived roles cog.

The engine evaluates state-based invariants over a member's role set:

- ``implies``: has trigger -> must have target (target is auto-added)
- ``requires``: lacks trigger -> must lack target (target is auto-removed)
- ``incompatible``: has trigger -> must lack target (target is auto-removed)

Rules are applied in passes until the role set is stable, so one rule's
effect can trigger another (cascade). ``MAX_PASSES`` bounds pathological
configurations that would otherwise oscillate.
"""

import logging
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

# Upper bound on cascade evaluation passes. Valid configurations converge in
# a handful of passes; this only guards against oscillating rule sets.
MAX_PASSES = 10


class RuleType(StrEnum):
    """Types of derived role rules."""

    IMPLIES = "implies"  # Has trigger -> must have target
    REQUIRES = "requires"  # Lacks trigger -> must lack target
    INCOMPATIBLE = "incompatible"  # Has trigger -> must lack target


def parse_rule(rule: dict[str, Any]) -> tuple[int, RuleType, int] | None:
    """Parse a rule row from the config table.

    Args:
        rule (dict[str, Any]): Raw rule row with trigger_role, rule_type, target_role

    Returns:
        tuple[int, RuleType, int] | None: (trigger_id, rule_type, target_id),
            or None if the row is malformed
    """
    try:
        trigger = int(rule["trigger_role"])
        target = int(rule["target_role"])
        rule_type = RuleType(rule["rule_type"])
    except (KeyError, TypeError, ValueError):
        return None
    return (trigger, rule_type, target)


def compute_role_changes(
    *,
    member_role_ids: set[int],
    rules: list[dict[str, Any]],
) -> tuple[set[int], set[int]]:
    """Compute the role changes needed to satisfy all rule invariants.

    Evaluates rules in passes until the simulated role set is stable or the
    pass limit is reached. When one rule adds a role and another removes it
    in the same pass, removal wins.

    Args:
        member_role_ids (set[int]): Current role IDs of the member
        rules (list[dict[str, Any]]): Rule rows from configuration

    Returns:
        tuple[set[int], set[int]]: (roles_to_add, roles_to_remove) as new sets;
            the input set is never mutated
    """
    parsed = [p for p in (parse_rule(rule) for rule in rules) if p is not None]
    current = set(member_role_ids)

    for _ in range(MAX_PASSES):
        adds: set[int] = set()
        removes: set[int] = set()

        for trigger, rule_type, target in parsed:
            if rule_type == RuleType.IMPLIES:
                if trigger in current and target not in current:
                    adds.add(target)
            elif rule_type == RuleType.REQUIRES:
                if target in current and trigger not in current:
                    removes.add(target)
            elif rule_type == RuleType.INCOMPATIBLE:
                if trigger in current and target in current:
                    removes.add(target)

        # Conflict resolution: removal wins over addition in the same pass
        adds = adds - removes

        if not adds and not removes:
            break

        current = (current | adds) - removes

    to_add = current - member_role_ids
    to_remove = member_role_ids - current
    return to_add, to_remove
