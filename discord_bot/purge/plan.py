"""Purge execution plan and outcome models.

``PurgePlan`` is the typed view of a purge record's configuration snapshot;
``PurgeStats`` holds the counters produced by the execution phases.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from discord_bot.purge.enums import ConfigKey, PurgeType
from discord_bot.purge.formatters import format_message
from discord_bot.purge.models import PurgeRecord

DEFAULT_GLOBAL_FINISH_MESSAGE = "✅ **Global purge completed.**\n\n🧹 Users purged: {cleaned}"
DEFAULT_WAR_FINISH_MESSAGE = (
    "✅ **Purge completed.**\n\n"
    "🧹 Purged: {cleaned}\n"
    "⬆️ Promoted (group): {promoted_in_group}\n"
    "⬆️ Promoted (others): {promoted_not_in_group}\n"
    "🗑️ Global roles removed: {global_removed}"
)


class PurgePlan(BaseModel):
    """What a purge will do, resolved from the record's configuration snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    purge_type: PurgeType
    test_mode: bool = False
    roles_to_remove: list[int] = []
    roles_to_add: list[int] = []
    confirmed_users: set[int] = set()
    excluded_roles: list[int] = []
    affected_roles: list[int] = []
    promotions: list[dict[str, Any]] = []
    default_promotion: int | None = None
    global_roles_to_remove: list[int] = []
    reaction_role: int | None = None

    @classmethod
    def from_record(cls, record: PurgeRecord) -> PurgePlan:
        """Build the plan from a purge record.

        Global purges only use exclusions; war-end purges use affected roles,
        promotions and the default promotion.

        Args:
            record (PurgeRecord): Purge record with its configuration snapshot.

        Returns:
            PurgePlan: Resolved plan.
        """
        snapshot = record.config_snapshot
        purge_type = PurgeType(record.purge_type)
        is_global = purge_type == PurgeType.GLOBAL
        return cls(
            purge_type=purge_type,
            test_mode=snapshot.get("test_mode", False),
            roles_to_remove=snapshot.get("roles_to_remove", []),
            roles_to_add=snapshot.get("roles_to_add", []),
            confirmed_users=set(record.confirmed_by),
            excluded_roles=snapshot.get("excluded_roles", []) if is_global else [],
            affected_roles=[] if is_global else snapshot.get("affected_roles", []),
            promotions=[] if is_global else snapshot.get("promotions", []),
            default_promotion=None if is_global else snapshot.get("default_promotion"),
            global_roles_to_remove=snapshot.get("global_roles_to_remove", []),
            reaction_role=snapshot.get("reaction_role"),
        )


class PurgeStats(BaseModel):
    """Counters produced by the execution phases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cleaned_count: int = 0
    promoted_in_group: int = 0
    promoted_not_in_group: int = 0
    global_removed_count: int = 0

    def to_execution_result(self, test_mode: bool, confirmed_count: int) -> dict[str, Any]:
        """Serialize the outcome as stored on the purge record.

        Args:
            test_mode (bool): Whether the purge ran in test mode.
            confirmed_count (int): Number of confirmed users.

        Returns:
            dict[str, Any]: Summary counters.
        """
        return {
            "test_mode": test_mode,
            "confirmed_count": confirmed_count,
            "cleaned_count": self.cleaned_count,
            "promoted_in_group": self.promoted_in_group,
            "promoted_not_in_group": self.promoted_not_in_group,
            "global_removed_count": self.global_removed_count,
        }


def build_finish_message(config: dict[str, Any], plan: PurgePlan, stats: PurgeStats) -> str:
    """Format the completion message for the purge type.

    Args:
        config (dict[str, Any]): Cog configuration.
        plan (PurgePlan): Execution plan.
        stats (PurgeStats): Execution counters.

    Returns:
        str: Formatted finish message.
    """
    if plan.purge_type == PurgeType.GLOBAL:
        return format_message(
            config.get(ConfigKey.GLOBAL_EXEC_MSG_FINISH, DEFAULT_GLOBAL_FINISH_MESSAGE),
            cleaned=str(stats.cleaned_count),
        )
    return format_message(
        config.get(ConfigKey.WAR_EXEC_MSG_FINISH, DEFAULT_WAR_FINISH_MESSAGE),
        cleaned=str(stats.cleaned_count),
        promoted_in_group=str(stats.promoted_in_group),
        promoted_not_in_group=str(stats.promoted_not_in_group),
        global_removed=str(stats.global_removed_count),
    )
