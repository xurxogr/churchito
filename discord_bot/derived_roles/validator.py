"""Static validation of derived role rule sets.

Detects configurations that are contradictory or that would cascade into
surprising results, so they can be rejected before saving. Roles are
referenced as ``<@&id>`` mentions in messages, which the settings UI
renders as role names.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from discord_bot.derived_roles.engine import RuleType, parse_rule


class RuleConflict(BaseModel):
    """A conflict detected in a rule set."""

    model_config = ConfigDict(extra="forbid")

    rows: list[int]  # 1-indexed row numbers involved in the conflict
    message: str


def _role(role_id: int) -> str:
    """Format a role ID as a mention for UI rendering.

    Args:
        role_id (int): Discord role ID

    Returns:
        str: Role mention string
    """
    return f"<@&{role_id}>"


def _find_row_conflicts(
    parsed: list[tuple[int, tuple[int, RuleType, int]]],
) -> list[RuleConflict]:
    """Find per-row and per-pair conflicts.

    Args:
        parsed (list[tuple[int, tuple[int, RuleType, int]]]): (row_number, rule) pairs

    Returns:
        list[RuleConflict]: Detected conflicts
    """
    conflicts: list[RuleConflict] = []
    seen: dict[tuple[int, RuleType, int], int] = {}
    by_pair: dict[tuple[int, int], dict[RuleType, int]] = {}

    for row_num, (trigger, rule_type, target) in parsed:
        if trigger == target:
            conflicts.append(
                RuleConflict(
                    rows=[row_num],
                    message=(f"Row {row_num}: {_role(trigger)} cannot derive from itself"),
                )
            )
            continue

        rule = (trigger, rule_type, target)
        if rule in seen:
            conflicts.append(
                RuleConflict(
                    rows=[seen[rule], row_num],
                    message=f"Rows {seen[rule]} and {row_num} are duplicated",
                )
            )
            continue
        seen[rule] = row_num

        pair_types = by_pair.setdefault((trigger, target), {})
        pair_types[rule_type] = row_num

    for (trigger, target), pair_types in by_pair.items():
        if RuleType.IMPLIES in pair_types and RuleType.INCOMPATIBLE in pair_types:
            rows = sorted([pair_types[RuleType.IMPLIES], pair_types[RuleType.INCOMPATIBLE]])
            conflicts.append(
                RuleConflict(
                    rows=rows,
                    message=(
                        f"Rows {rows[0]} and {rows[1]}: {_role(trigger)} both grants "
                        f"and forbids {_role(target)}"
                    ),
                )
            )
        if RuleType.REQUIRES in pair_types and RuleType.INCOMPATIBLE in pair_types:
            rows = sorted([pair_types[RuleType.REQUIRES], pair_types[RuleType.INCOMPATIBLE]])
            conflicts.append(
                RuleConflict(
                    rows=rows,
                    message=(
                        f"Rows {rows[0]} and {rows[1]}: {_role(target)} would be removed "
                        f"both with and without {_role(trigger)}, so it can never be held"
                    ),
                )
            )

    return conflicts


def _find_mutual_incompatibilities(
    parsed: list[tuple[int, tuple[int, RuleType, int]]],
) -> list[RuleConflict]:
    """Find pairs of roles that forbid each other.

    Args:
        parsed (list[tuple[int, tuple[int, RuleType, int]]]): (row_number, rule) pairs

    Returns:
        list[RuleConflict]: Detected conflicts
    """
    conflicts: list[RuleConflict] = []
    incompatible_rows = {
        (trigger, target): row_num
        for row_num, (trigger, rule_type, target) in parsed
        if rule_type == RuleType.INCOMPATIBLE
    }

    reported: set[frozenset[int]] = set()
    for (trigger, target), row_num in incompatible_rows.items():
        reverse_row = incompatible_rows.get((target, trigger))
        if reverse_row is None:
            continue
        pair_key = frozenset((trigger, target))
        if pair_key in reported:
            continue
        reported.add(pair_key)
        rows = sorted([row_num, reverse_row])
        conflicts.append(
            RuleConflict(
                rows=rows,
                message=(
                    f"Rows {rows[0]} and {rows[1]}: {_role(trigger)} and {_role(target)} "
                    f"forbid each other; a member holding both would lose both. "
                    f"Define the incompatibility in one direction only"
                ),
            )
        )

    return conflicts


def _find_cascade_conflicts(
    parsed: list[tuple[int, tuple[int, RuleType, int]]],
) -> list[RuleConflict]:
    """Find chains where gaining a role cascades into removing that same role.

    Builds a propagation graph over (role, present/absent) states and reports
    any path from (role, present) to (role, absent).

    Args:
        parsed (list[tuple[int, tuple[int, RuleType, int]]]): (row_number, rule) pairs

    Returns:
        list[RuleConflict]: Detected conflicts
    """
    # Edges: (from_state) -> list of (to_state, verb, row_number)
    # States are (role_id, is_present).
    edges: dict[tuple[int, bool], list[tuple[tuple[int, bool], str, int]]] = {}
    for row_num, (trigger, rule_type, target) in parsed:
        if rule_type == RuleType.IMPLIES:
            edges.setdefault((trigger, True), []).append(((target, True), "grants", row_num))
        elif rule_type == RuleType.INCOMPATIBLE:
            edges.setdefault((trigger, True), []).append(((target, False), "removes", row_num))
        elif rule_type == RuleType.REQUIRES:
            edges.setdefault((trigger, False), []).append(
                ((target, False), "cascades removal of", row_num)
            )

    conflicts: list[RuleConflict] = []
    reported_chains: set[frozenset[int]] = set()

    start_roles = {role for (role, present) in edges if present}
    for role in sorted(start_roles):
        start = (role, True)
        goal = (role, False)
        # BFS with parent tracking to reconstruct the chain
        parents: dict[tuple[int, bool], tuple[tuple[int, bool], str, int]] = {}
        visited = {start}
        queue = [start]
        found = False
        while queue and not found:
            state = queue.pop(0)
            for next_state, verb, row_num in edges.get(state, []):
                if next_state in visited:
                    continue
                visited.add(next_state)
                parents[next_state] = (state, verb, row_num)
                if next_state == goal:
                    found = True
                    break
                queue.append(next_state)

        if not found:
            continue

        # Reconstruct chain from goal back to start
        chain_parts: list[str] = []
        chain_rows: list[int] = []
        state = goal
        while state != start:
            prev_state, verb, row_num = parents[state]
            chain_parts.append(f"{verb} {_role(state[0])}")
            chain_rows.append(row_num)
            state = prev_state
        chain_parts.reverse()
        chain_rows.reverse()

        rows_key = frozenset(chain_rows)
        if rows_key in reported_chains:
            continue
        reported_chains.add(rows_key)

        chain_text = f"{_role(role)} " + " → ".join(chain_parts)
        conflicts.append(
            RuleConflict(
                rows=sorted(set(chain_rows)),
                message=(
                    f"Cascade conflict: gaining {_role(role)} ultimately removes it "
                    f"(chain: {chain_text})"
                ),
            )
        )

    return conflicts


def find_rule_conflicts(rules: list[dict[str, Any]]) -> list[RuleConflict]:
    """Find all conflicts in a rule set.

    Args:
        rules (list[dict[str, Any]]): Rule rows from configuration

    Returns:
        list[RuleConflict]: All detected conflicts, empty if the rule set is valid
    """
    conflicts: list[RuleConflict] = []
    parsed: list[tuple[int, tuple[int, RuleType, int]]] = []

    for index, rule in enumerate(rules):
        row_num = index + 1
        parsed_rule = parse_rule(rule)
        if parsed_rule is None:
            conflicts.append(
                RuleConflict(
                    rows=[row_num],
                    message=f"Row {row_num}: invalid rule (missing or malformed fields)",
                )
            )
            continue
        parsed.append((row_num, parsed_rule))

    conflicts.extend(_find_row_conflicts(parsed))
    conflicts.extend(_find_mutual_incompatibilities(parsed))
    conflicts.extend(_find_cascade_conflicts(parsed))
    return conflicts


def validate_rules(rules: list[dict[str, Any]]) -> str | None:
    """Validate a rule set for use as a config option validator.

    Args:
        rules (list[dict[str, Any]]): Rule rows from configuration

    Returns:
        str | None: Combined error message, or None if the rule set is valid
    """
    conflicts = find_rule_conflicts(rules)
    if not conflicts:
        return None
    return "; ".join(conflict.message for conflict in conflicts)
