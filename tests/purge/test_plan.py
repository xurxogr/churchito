"""Tests for the purge execution plan and outcome models."""

from unittest.mock import MagicMock

from discord_bot.purge.enums import ConfigKey, PurgeType
from discord_bot.purge.plan import PurgePlan, PurgeStats, build_finish_message


def _record(purge_type: PurgeType, snapshot: dict, confirmed_by: list[int]) -> MagicMock:
    """Build a purge record mock.

    Args:
        purge_type (PurgeType): Purge type.
        snapshot (dict): Configuration snapshot.
        confirmed_by (list[int]): Confirmed user IDs.

    Returns:
        MagicMock: Record mock.
    """
    record = MagicMock()
    record.purge_type = purge_type.value
    record.config_snapshot = snapshot
    record.confirmed_by = confirmed_by
    return record


class TestPurgePlan:
    """Plan derived from the record snapshot."""

    def test_war_end_plan_reads_type_specific_fields(self) -> None:
        """War-end purges take affected roles and promotions, no exclusions."""
        record = _record(
            PurgeType.WAR_END,
            {
                "test_mode": True,
                "affected_roles": [1, 2],
                "excluded_roles": [9],
                "roles_to_remove": [3],
                "roles_to_add": [4],
                "promotions": [{"from": 1, "to": 5}],
                "default_promotion": 6,
                "global_roles_to_remove": [7],
                "reaction_role": 8,
            },
            confirmed_by=[10, 10, 11],
        )

        plan = PurgePlan.from_record(record)

        assert plan.purge_type == PurgeType.WAR_END
        assert plan.test_mode is True
        assert plan.affected_roles == [1, 2]
        assert plan.excluded_roles == []
        assert plan.roles_to_remove == [3]
        assert plan.roles_to_add == [4]
        assert plan.promotions == [{"from": 1, "to": 5}]
        assert plan.default_promotion == 6
        assert plan.global_roles_to_remove == [7]
        assert plan.reaction_role == 8
        assert plan.confirmed_users == {10, 11}

    def test_global_plan_ignores_war_fields(self) -> None:
        """Global purges keep exclusions and drop affected roles/promotions."""
        record = _record(
            PurgeType.GLOBAL,
            {
                "excluded_roles": [9],
                "affected_roles": [1],
                "promotions": [{"from": 1, "to": 5}],
                "default_promotion": 6,
            },
            confirmed_by=[],
        )

        plan = PurgePlan.from_record(record)

        assert plan.purge_type == PurgeType.GLOBAL
        assert plan.excluded_roles == [9]
        assert plan.affected_roles == []
        assert plan.promotions == []
        assert plan.default_promotion is None
        assert plan.test_mode is False
        assert plan.reaction_role is None
        assert plan.confirmed_users == set()

    def test_empty_snapshot_uses_defaults(self) -> None:
        """A missing snapshot yields empty lists and no reaction role."""
        plan = PurgePlan.from_record(_record(PurgeType.WAR_END, {}, confirmed_by=[]))

        assert plan.roles_to_remove == []
        assert plan.global_roles_to_remove == []
        assert plan.reaction_role is None


class TestPurgeStats:
    """Execution counters and their persisted form."""

    def test_execution_result_shape(self) -> None:
        """The stored summary carries the counters plus test mode and confirmations."""
        stats = PurgeStats(
            cleaned_count=3, promoted_in_group=1, promoted_not_in_group=2, global_removed_count=4
        )

        assert stats.to_execution_result(test_mode=True, confirmed_count=5) == {
            "test_mode": True,
            "confirmed_count": 5,
            "cleaned_count": 3,
            "promoted_in_group": 1,
            "promoted_not_in_group": 2,
            "global_removed_count": 4,
        }


class TestBuildFinishMessage:
    """Finish message per purge type."""

    def test_global_message_uses_cleaned_only(self) -> None:
        """Global purges format the configured global template."""
        plan = PurgePlan.from_record(_record(PurgeType.GLOBAL, {}, confirmed_by=[]))
        config = {ConfigKey.GLOBAL_EXEC_MSG_FINISH: "Done {cleaned}"}

        assert (
            build_finish_message(config=config, plan=plan, stats=PurgeStats(cleaned_count=7))
            == "Done 7"
        )

    def test_war_message_uses_all_counters(self) -> None:
        """War-end purges format the war template with every counter."""
        plan = PurgePlan.from_record(_record(PurgeType.WAR_END, {}, confirmed_by=[]))
        config = {
            ConfigKey.WAR_EXEC_MSG_FINISH: (
                "{cleaned}/{promoted_in_group}/{promoted_not_in_group}/{global_removed}"
            )
        }
        stats = PurgeStats(
            cleaned_count=1, promoted_in_group=2, promoted_not_in_group=3, global_removed_count=4
        )

        assert build_finish_message(config=config, plan=plan, stats=stats) == "1/2/3/4"

    def test_defaults_when_not_configured(self) -> None:
        """Without configured templates the built-in defaults are used."""
        plan = PurgePlan.from_record(_record(PurgeType.WAR_END, {}, confirmed_by=[]))

        message = build_finish_message(config={}, plan=plan, stats=PurgeStats())

        assert "Purge completed" in message
