"""Purge execution orchestration.

Loads the authorized record, runs the phases from ``purge.phases`` and
publishes the outcome. Database access is split into short sessions.
"""

from __future__ import annotations

import logging
from collections.abc import MutableSequence
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.common.utils import delete_message
from discord_bot.purge.enums import ConfigKey, PurgeStatus, PurgeType
from discord_bot.purge.models import PurgeRecord
from discord_bot.purge.phases import (
    execute_cleaning_phase,
    execute_global_cleaning_phase,
    execute_global_removal_phase,
    execute_promotion_phase,
    make_execution_log,
)
from discord_bot.purge.plan import PurgePlan, PurgeStats, build_finish_message
from discord_bot.purge.results import PurgeResultBuffer, UserResultSink
from discord_bot.purge.service import PurgeService

if TYPE_CHECKING:
    from discord_bot.purge.cog import PurgeCog

logger = logging.getLogger(__name__)


async def _load_authorized_record(cog: PurgeCog, purge_id: int) -> PurgeRecord | None:
    """Load a purge record in a short session, only if it is authorized.

    Args:
        cog (PurgeCog): Cog instance.
        purge_id (int): Purge ID.

    Returns:
        PurgeRecord | None: The detached record, or None if missing / not authorized.
    """
    async with cog.bot.database.session() as session:
        record = await PurgeService(session).get_purge(purge_id)
    if not record or record.status != PurgeStatus.AUTHORIZED:
        return None
    return record


async def _finalize_purge_record(
    cog: PurgeCog, purge_id: int, execution_result: dict[str, Any]
) -> PurgeRecord | None:
    """Mark the purge as executed and commit, in its own short session.

    Args:
        cog (PurgeCog): Cog instance.
        purge_id (int): Purge ID.
        execution_result (dict[str, Any]): Summary counters to store.

    Returns:
        PurgeRecord | None: Updated record, or None if it disappeared.
    """
    async with cog.bot.database.session() as session:
        record = await PurgeService(session).update_status(
            purge_id=purge_id,
            status=PurgeStatus.EXECUTED,
            execution_result=execution_result,
        )
        await session.commit()
    return record


async def _log_start(
    cog: PurgeCog,
    guild: discord.Guild,
    record: PurgeRecord,
    config: dict[str, Any],
    plan: PurgePlan,
    audit_level: int,
    execution_logs: MutableSequence[str],
) -> None:
    """Append the simulation/start lines and send the start log.

    Args:
        cog (PurgeCog): Cog instance.
        guild (discord.Guild): Discord guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Cog configuration.
        plan (PurgePlan): Execution plan.
        audit_level (int): Audit level.
        execution_logs (MutableSequence[str]): Execution log lines.
    """
    if plan.test_mode:
        execution_logs.append(config.get(ConfigKey.EXEC_MSG_SIMULATION, "🧪 **[TEST MODE]**"))
    if audit_level < 1:
        return
    msg = config.get(ConfigKey.EXEC_MSG_INIT, "🔥 **Starting purge...**")
    execution_logs.append(msg)
    await cog._send_log(
        guild=guild,
        config=config,
        public_id=record.public_id,
        message=msg,
        audit_level_required=1,
    )


async def _run_cleaning_phase(
    cog: PurgeCog,
    guild: discord.Guild,
    record: PurgeRecord,
    config: dict[str, Any],
    plan: PurgePlan,
    results: UserResultSink,
    audit_level: int,
    execution_logs: MutableSequence[str],
) -> tuple[int, set[int]]:
    """Phase 1: clean non-confirmed users (global or war-end variant).

    Args:
        cog (PurgeCog): Cog instance.
        guild (discord.Guild): Discord guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Cog configuration.
        plan (PurgePlan): Execution plan.
        results (UserResultSink): Where to record per-user results.
        audit_level (int): Audit level.
        execution_logs (MutableSequence[str]): Execution log lines.

    Returns:
        tuple[int, set[int]]: (cleaned_count, processed_users)
    """
    if plan.purge_type == PurgeType.GLOBAL:
        return await execute_global_cleaning_phase(
            cog=cog,
            guild=guild,
            record=record,
            config=config,
            purge_service=results,
            purge_id=record.id,
            excluded_roles=plan.excluded_roles,
            roles_to_remove=plan.roles_to_remove,
            roles_to_add=plan.roles_to_add,
            confirmed_users=plan.confirmed_users,
            audit_level=audit_level,
            execution_logs=execution_logs,
        )
    return await execute_cleaning_phase(
        cog=cog,
        guild=guild,
        record=record,
        config=config,
        purge_service=results,
        purge_id=record.id,
        affected_roles=plan.affected_roles,
        roles_to_remove=plan.roles_to_remove,
        roles_to_add=plan.roles_to_add,
        confirmed_users=plan.confirmed_users,
        audit_level=audit_level,
        execution_logs=execution_logs,
    )


async def _run_promotion_phase(
    cog: PurgeCog,
    guild: discord.Guild,
    record: PurgeRecord,
    config: dict[str, Any],
    plan: PurgePlan,
    results: UserResultSink,
    processed_users: set[int],
    audit_level: int,
    execution_logs: MutableSequence[str],
) -> tuple[int, int]:
    """Phase 2: apply promotions (war-end purges only).

    Args:
        cog (PurgeCog): Cog instance.
        guild (discord.Guild): Discord guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Cog configuration.
        plan (PurgePlan): Execution plan.
        results (UserResultSink): Where to record per-user results.
        processed_users (set[int]): Users already handled by the cleaning phase.
        audit_level (int): Audit level.
        execution_logs (MutableSequence[str]): Execution log lines.

    Returns:
        tuple[int, int]: (promoted_in_group, promoted_not_in_group)
    """
    if plan.purge_type == PurgeType.GLOBAL:
        return 0, 0
    if audit_level >= 1:
        execution_logs.append(
            config.get(ConfigKey.EXEC_MSG_PROMOTIONS_START, "⬆️ **Applying promotions...**")
        )
    promoted_in_group, promoted_not_in_group, _promoted_users = await execute_promotion_phase(
        cog=cog,
        guild=guild,
        record=record,
        config=config,
        purge_service=results,
        purge_id=record.id,
        affected_roles=plan.affected_roles,
        promotions=plan.promotions,
        default_promotion=plan.default_promotion,
        confirmed_users=plan.confirmed_users,
        processed_users=processed_users,
        audit_level=audit_level,
        execution_logs=execution_logs,
    )
    return promoted_in_group, promoted_not_in_group


async def _remove_reaction_role(guild: discord.Guild, plan: PurgePlan) -> None:
    """Remove the reaction role from every confirmed user.

    Args:
        guild (discord.Guild): Discord guild.
        plan (PurgePlan): Execution plan (reaction role and confirmed users).
    """
    reaction_role = guild.get_role(plan.reaction_role) if plan.reaction_role else None
    if not reaction_role:
        return
    for user_id in plan.confirmed_users:
        member = guild.get_member(user_id)
        if not member or reaction_role not in member.roles:
            continue
        try:
            await member.remove_roles(reaction_role)
        except discord.Forbidden:
            logger.warning(f"[{guild.name}] Could not remove reaction role from {member.name}")
        except discord.HTTPException as e:
            logger.warning(f"[{guild.name}] Could not remove reaction role from {member.name}: {e}")


async def _run_phases(
    cog: PurgeCog,
    guild: discord.Guild,
    record: PurgeRecord,
    config: dict[str, Any],
    plan: PurgePlan,
    results: UserResultSink,
    audit_level: int,
    execution_logs: MutableSequence[str],
) -> PurgeStats:
    """Run cleaning, promotions, global removal and reaction-role cleanup in order.

    Args:
        cog (PurgeCog): Cog instance.
        guild (discord.Guild): Discord guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Cog configuration.
        plan (PurgePlan): Execution plan.
        results (UserResultSink): Where to record per-user results.
        audit_level (int): Audit level.
        execution_logs (MutableSequence[str]): Execution log lines.

    Returns:
        PurgeStats: Counters for the finish message and the stored result.
    """
    cleaned_count, processed_users = await _run_cleaning_phase(
        cog=cog,
        guild=guild,
        record=record,
        config=config,
        plan=plan,
        results=results,
        audit_level=audit_level,
        execution_logs=execution_logs,
    )
    promoted_in_group, promoted_not_in_group = await _run_promotion_phase(
        cog=cog,
        guild=guild,
        record=record,
        config=config,
        plan=plan,
        results=results,
        processed_users=processed_users,
        audit_level=audit_level,
        execution_logs=execution_logs,
    )
    global_removed_count = 0
    if plan.global_roles_to_remove:
        global_removed_count = await execute_global_removal_phase(
            cog=cog,
            guild=guild,
            record=record,
            config=config,
            global_roles_to_remove=plan.global_roles_to_remove,
            audit_level=audit_level,
            execution_logs=execution_logs,
        )
    await _remove_reaction_role(guild=guild, plan=plan)
    return PurgeStats(
        cleaned_count=cleaned_count,
        promoted_in_group=promoted_in_group,
        promoted_not_in_group=promoted_not_in_group,
        global_removed_count=global_removed_count,
    )


async def _publish_outcome(
    cog: PurgeCog,
    guild: discord.Guild,
    record: PurgeRecord,
    config: dict[str, Any],
    plan: PurgePlan,
    stats: PurgeStats,
    finish_msg: str,
    audit_level: int,
    execution_logs: MutableSequence[str],
) -> None:
    """Update Discord after the record is finalized: messages, retention and logs.

    Args:
        cog (PurgeCog): Cog instance.
        guild (discord.Guild): Discord guild.
        record (PurgeRecord): Finalized purge record.
        config (dict[str, Any]): Cog configuration.
        plan (PurgePlan): Execution plan.
        stats (PurgeStats): Execution counters.
        finish_msg (str): Completion message.
        audit_level (int): Audit level.
        execution_logs (MutableSequence[str]): Execution log lines.
    """
    if record.user_message_id and record.user_channel_id:
        await delete_message(
            guild=guild,
            channel_id=record.user_channel_id,
            message_id=record.user_message_id,
        )
    await cog._update_mod_message(
        guild=guild,
        record=record,
        config=config,
        remove_view=True,
        execution_logs=execution_logs if audit_level >= 1 else None,
    )
    cog._maybe_schedule_mod_message_deletion(record=record, config=config)
    logger.info(
        f"[{guild.name}] {'[TEST MODE] ' if plan.test_mode else ''}"
        f"Purge {record.id} executed: cleaned={stats.cleaned_count}, "
        f"promoted_in={stats.promoted_in_group}, promoted_out={stats.promoted_not_in_group}, "
        f"global_removed={stats.global_removed_count}"
    )
    await cog._send_log(
        guild=guild,
        config=config,
        public_id=record.public_id,
        message=finish_msg,
    )


async def execute_purge(
    cog: PurgeCog,
    guild_id: int,
    purge_id: int,
) -> None:
    """Execute a purge.

    Database access is split into short sessions (load, batched per-user
    results, finalize) so no transaction stays open while the potentially
    long, rate-limited Discord role edits run.

    Args:
        cog (PurgeCog): Cog instance.
        guild_id (int): Guild ID.
        purge_id (int): Purge ID.
    """
    guild = cog.bot.get_guild(guild_id)
    if not guild:
        logger.error(f"[Guild ID: {guild_id}] Guild not found to execute purge {purge_id}")
        return

    record = await _load_authorized_record(cog=cog, purge_id=purge_id)
    if not record:
        logger.warning(f"[{guild.name}] Purge (ID: {purge_id}) is not in authorized status")
        return

    config = await cog._get_config(guild_id)
    plan = PurgePlan.from_record(record)
    audit_level = config.get(ConfigKey.AUDIT_LEVEL, 1)
    test_prefix = "[TEST MODE] " if plan.test_mode else ""
    logger.info(f"[{guild.name}] {test_prefix}Executing purge {purge_id}")

    # Per-user results are buffered and written in short sessions; the
    # execution log is bounded to the newest lines for the mod message
    results = PurgeResultBuffer(database=cog.bot.database, purge_id=purge_id)
    execution_logs = make_execution_log()
    await _log_start(
        cog=cog,
        guild=guild,
        record=record,
        config=config,
        plan=plan,
        audit_level=audit_level,
        execution_logs=execution_logs,
    )

    try:
        stats = await _run_phases(
            cog=cog,
            guild=guild,
            record=record,
            config=config,
            plan=plan,
            results=results,
            audit_level=audit_level,
            execution_logs=execution_logs,
        )
    finally:
        # Keep whatever was already applied even if a phase raised; the cog
        # marks the purge FAILED in that case
        await results.flush()

    finish_msg = build_finish_message(config=config, plan=plan, stats=stats)
    if audit_level >= 1:
        execution_logs.append(finish_msg)

    # Persist the outcome before touching Discord messages
    finalized = await _finalize_purge_record(
        cog=cog,
        purge_id=purge_id,
        execution_result=stats.to_execution_result(
            test_mode=plan.test_mode, confirmed_count=len(plan.confirmed_users)
        ),
    )
    if not finalized:
        return
    await _publish_outcome(
        cog=cog,
        guild=guild,
        record=finalized,
        config=config,
        plan=plan,
        stats=stats,
        finish_msg=finish_msg,
        audit_level=audit_level,
        execution_logs=execution_logs,
    )
