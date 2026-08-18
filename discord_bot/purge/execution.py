"""Purge execution logic."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import MutableSequence
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.common.utils import delete_message
from discord_bot.purge.enums import ConfigKey, PurgeStatus, PurgeType
from discord_bot.purge.formatters import format_message
from discord_bot.purge.models import PurgeRecord
from discord_bot.purge.plan import PurgePlan, PurgeStats, build_finish_message
from discord_bot.purge.results import PurgeResultBuffer, UserResultSink
from discord_bot.purge.service import PurgeService

if TYPE_CHECKING:
    from discord_bot.purge.cog import PurgeCog

logger = logging.getLogger(__name__)

# Bound the in-memory execution log: the mod message can only ever show the
# newest lines, so older ones are dropped as new ones arrive
EXECUTION_LOG_MAX_LINES = 50


def make_execution_log() -> deque[str]:
    """Create the bounded container for purge execution log lines.

    Returns:
        deque[str]: Deque keeping only the newest EXECUTION_LOG_MAX_LINES lines.
    """
    return deque(maxlen=EXECUTION_LOG_MAX_LINES)


def _member_role_ids(guild: discord.Guild, member: discord.Member) -> list[int]:
    """Return the member's role IDs, excluding @everyone.

    Args:
        guild (discord.Guild): Discord guild.
        member (discord.Member): Member to inspect.

    Returns:
        list[int]: Role IDs in the order Discord reports them.
    """
    return [r.id for r in member.roles if r != guild.default_role]


def _replacement_roles(
    guild: discord.Guild,
    member: discord.Member,
    remove_ids: set[int] | None,
    add_ids: list[int],
) -> list[discord.Role]:
    """Compute the full role list a member should end up with.

    Args:
        guild (discord.Guild): Discord guild.
        member (discord.Member): Member whose roles are being changed.
        remove_ids (set[int] | None): Role IDs to drop; ``None`` drops every role.
        add_ids (list[int]): Role IDs to add (unknown IDs are ignored).

    Returns:
        list[discord.Role]: Kept roles followed by newly added ones.
    """
    if remove_ids is None:
        kept: list[discord.Role] = []
    else:
        kept = [r for r in member.roles if r != guild.default_role and r.id not in remove_ids]

    for rid in add_ids:
        role = guild.get_role(rid)
        if role and role not in kept:
            kept.append(role)
    return kept


async def _set_member_roles(
    guild: discord.Guild,
    member: discord.Member,
    roles: list[discord.Role],
    what: str,
) -> bool:
    """Replace a member's roles with a single API call, tolerating failures.

    Discord's ``add_roles``/``remove_roles`` each issue their own request, so
    a remove-then-add sequence costs two rate-limited calls per member and can
    leave the member half-changed if the second one fails. One ``edit`` applies
    the whole change atomically. The call is skipped when nothing would change.

    Args:
        guild (discord.Guild): Discord guild.
        member (discord.Member): Member to update.
        roles (list[discord.Role]): Complete role list to apply (without @everyone).
        what (str): Short description of the action for log messages.

    Returns:
        bool: True if the roles were applied (or already matched), False on API error.
    """
    if {r.id for r in roles} == set(_member_role_ids(guild=guild, member=member)):
        return True
    try:
        await member.edit(roles=roles)
    except discord.Forbidden:
        logger.warning(f"[{guild.name}] Could not {what} for {member.name}: missing permissions")
        return False
    except discord.HTTPException as e:
        logger.warning(f"[{guild.name}] Could not {what} for {member.name}: {e}")
        return False
    return True


async def _apply_cleaning_to_member(
    guild: discord.Guild,
    member: discord.Member,
    roles_to_remove: list[int],
    roles_to_add: list[int],
    purge_service: UserResultSink,
    purge_id: int,
) -> tuple[discord.Member, list[int], list[int]]:
    """Apply role cleaning to a member.

    Args:
        guild (discord.Guild): Discord guild.
        member (discord.Member): Member to clean.
        roles_to_remove (list[int]): Role IDs to remove; empty removes every role.
        roles_to_add (list[int]): Role IDs to add.
        purge_service (UserResultSink): Where to record the per-user result.
        purge_id (int): Purge ID.

    Returns:
        tuple[discord.Member, list[int], list[int]]: Member, roles before, roles after
    """
    roles_before = _member_role_ids(guild=guild, member=member)

    target_roles = _replacement_roles(
        guild=guild,
        member=member,
        remove_ids=set(roles_to_remove) if roles_to_remove else None,
        add_ids=roles_to_add,
    )
    await _set_member_roles(guild=guild, member=member, roles=target_roles, what="clean roles")

    # Refresh member
    refreshed = guild.get_member(member.id)
    if refreshed:
        member = refreshed
    roles_after = _member_role_ids(guild=guild, member=member)

    # Save result
    await purge_service.add_user_result(
        purge_id=purge_id,
        user_id=member.id,
        action_type="cleaned",
        roles_before=roles_before,
        roles_after=roles_after,
    )

    return member, roles_before, roles_after


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
        return await _execute_global_cleaning_phase(
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
    return await _execute_cleaning_phase(
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
    promoted_in_group, promoted_not_in_group, _promoted_users = await _execute_promotion_phase(
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
        global_removed_count = await _execute_global_removal_phase(
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


async def _execute_cleaning_phase(
    cog: PurgeCog,
    guild: discord.Guild,
    record: PurgeRecord,
    config: dict[str, Any],
    purge_service: UserResultSink,
    purge_id: int,
    affected_roles: list[int],
    roles_to_remove: list[int],
    roles_to_add: list[int],
    confirmed_users: set[int],
    audit_level: int,
    execution_logs: MutableSequence[str],
) -> tuple[int, set[int]]:
    """Execute cleaning phase for non-confirmed users.

    Args:
        cog (PurgeCog): Cog instance.
        guild (discord.Guild): Discord guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Cog configuration.
        purge_service (UserResultSink): Where to record per-user results.
        purge_id (int): Purge ID.
        affected_roles (list[int]): Affected role IDs.
        roles_to_remove (list[int]): Role IDs to remove.
        roles_to_add (list[int]): Role IDs to add.
        confirmed_users (set[int]): Confirmed user IDs.
        audit_level (int): Audit level.
        execution_logs (MutableSequence[str]): Execution log lines.

    Returns:
        tuple[int, set[int]]: (cleaned_count, processed_users)
    """
    cleaned_count = 0
    processed_users: set[int] = set()

    for role_id in affected_roles:
        role = guild.get_role(role_id)
        if not role:
            continue

        # Log level 2 message
        if audit_level >= 2:
            msg_template = config.get(
                ConfigKey.EXEC_MSG_CLEANING_ROLE,
                "🧹 Applying purge to role {role}...",
            )
            msg = format_message(msg_template, role=role.name)
            execution_logs.append(msg)

        # Find members with this role who did NOT confirm
        for member in role.members:
            if member.id in confirmed_users:
                continue
            if member.id in processed_users:
                continue

            member, _, _ = await _apply_cleaning_to_member(
                guild=guild,
                member=member,
                roles_to_remove=roles_to_remove,
                roles_to_add=roles_to_add,
                purge_service=purge_service,
                purge_id=purge_id,
            )

            # Audit level 2: log each user
            if audit_level >= 2:
                msg_template = config.get(
                    ConfigKey.EXEC_MSG_USER_CLEANED,
                    "  ↳ 🧹 Purged: {user}",
                )
                msg = format_message(msg_template, user=member.display_name)
                execution_logs.append(msg)

            processed_users.add(member.id)
            cleaned_count += 1

        # Update mod message after each role (to show progress)
        if audit_level >= 1:
            await cog._update_mod_message(
                guild=guild,
                record=record,
                config=config,
                execution_logs=execution_logs,
            )

    return cleaned_count, processed_users


async def _execute_global_cleaning_phase(
    cog: PurgeCog,
    guild: discord.Guild,
    record: PurgeRecord,
    config: dict[str, Any],
    purge_service: UserResultSink,
    purge_id: int,
    excluded_roles: list[int],
    roles_to_remove: list[int],
    roles_to_add: list[int],
    confirmed_users: set[int],
    audit_level: int,
    execution_logs: MutableSequence[str],
) -> tuple[int, set[int]]:
    """Execute global cleaning phase for non-confirmed users.

    Affects ALL members except those with excluded roles.

    Args:
        cog (PurgeCog): Cog instance.
        guild (discord.Guild): Discord guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Cog configuration.
        purge_service (UserResultSink): Where to record per-user results.
        purge_id (int): Purge ID.
        excluded_roles (list[int]): Excluded role IDs.
        roles_to_remove (list[int]): Role IDs to remove.
        roles_to_add (list[int]): Role IDs to add.
        confirmed_users (set[int]): Confirmed user IDs.
        audit_level (int): Audit level.
        execution_logs (MutableSequence[str]): Execution log lines.

    Returns:
        tuple[int, set[int]]: (cleaned_count, processed_users)
    """
    cleaned_count = 0
    processed_users: set[int] = set()

    # Get excluded role objects
    excluded_role_objs: set[discord.Role] = {
        role for rid in excluded_roles if (role := guild.get_role(rid))
    }

    # Log level 1 message
    if audit_level >= 1:
        msg_template = config.get(
            ConfigKey.EXEC_MSG_CLEANING_START,
            "🧹 **Applying global purge...**",
        )
        msg = format_message(msg_template)
        execution_logs.append(msg)

    # Iterate over all server members
    for member in guild.members:
        # Skip bots
        if member.bot:
            continue

        # Skip members who confirmed
        if member.id in confirmed_users:
            continue

        # Skip members with excluded roles
        if any(role in excluded_role_objs for role in member.roles):
            continue

        # Already processed
        if member.id in processed_users:
            continue

        member, _, _ = await _apply_cleaning_to_member(
            guild=guild,
            member=member,
            roles_to_remove=roles_to_remove,
            roles_to_add=roles_to_add,
            purge_service=purge_service,
            purge_id=purge_id,
        )

        # Audit level 2: log each user
        if audit_level >= 2:
            msg_template = config.get(
                ConfigKey.EXEC_MSG_USER_CLEANED,
                "  ↳ 🧹 Purged: {user}",
            )
            msg = format_message(msg_template, user=member.display_name)
            execution_logs.append(msg)

        processed_users.add(member.id)
        cleaned_count += 1

    # Update moderation message
    if audit_level >= 1:
        await cog._update_mod_message(
            guild=guild,
            record=record,
            config=config,
            execution_logs=execution_logs,
        )

    return cleaned_count, processed_users


async def _execute_promotion_phase(
    cog: PurgeCog,
    guild: discord.Guild,
    record: PurgeRecord,
    config: dict[str, Any],
    purge_service: UserResultSink,
    purge_id: int,
    affected_roles: list[int],
    promotions: list[dict[str, Any]],
    default_promotion: int | None,
    confirmed_users: set[int],
    processed_users: set[int],
    audit_level: int,
    execution_logs: MutableSequence[str],
) -> tuple[int, int, set[int]]:
    """Execute promotions phase.

    Args:
        cog (PurgeCog): Cog instance.
        guild (discord.Guild): Discord guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Cog configuration.
        purge_service (UserResultSink): Where to record per-user results.
        purge_id (int): Purge ID.
        affected_roles (list[int]): Affected role IDs.
        promotions (list[dict[str, Any]]): Promotions list.
        default_promotion (int | None): Default promotion role.
        confirmed_users (set[int]): Confirmed user IDs.
        processed_users (set[int]): Already processed user IDs.
        audit_level (int): Audit level.
        execution_logs (MutableSequence[str]): Execution log lines.

    Returns:
        tuple[int, int, set[int]]: (promoted_in_group, promoted_not_in_group, promoted_users)
    """
    promoted_in_group = 0
    promoted_not_in_group = 0
    promoted_users: set[int] = set()

    # Build promotion map: from_role_id -> to_role_id
    promotion_map: dict[int, int] = {}
    for promo in promotions:
        from_role = promo.get("from_role")
        to_role = promo.get("to_role")
        if from_role and to_role:
            # Handle both string and int IDs (legacy data may have strings)
            promotion_map[int(from_role)] = int(to_role)

    # Apply promotions based on roles
    for from_role_id, to_role_id in promotion_map.items():
        from_role = guild.get_role(from_role_id)
        to_role = guild.get_role(to_role_id)
        if not from_role or not to_role:
            continue

        # Log level 2 message
        if audit_level >= 2:
            msg_template = config.get(
                ConfigKey.EXEC_MSG_PROMOTION_ROLE,
                "📈 Promoting {from_role} → {to_role}...",
            )
            msg = format_message(msg_template, from_role=from_role.name, to_role=to_role.name)
            execution_logs.append(msg)

        # Find confirmed members with from_role
        for member in from_role.members:
            if member.id not in confirmed_users:
                continue
            if member.id in promoted_users:
                continue

            roles_before = _member_role_ids(guild=guild, member=member)
            in_affected = from_role_id in affected_roles

            # If from_role is in affected_roles, swap it for to_role; otherwise just add
            target_roles = _replacement_roles(
                guild=guild,
                member=member,
                remove_ids={from_role_id} if in_affected else set(),
                add_ids=[to_role_id],
            )
            await _set_member_roles(guild=guild, member=member, roles=target_roles, what="promote")

            # Refresh member and get roles_after
            refreshed = guild.get_member(member.id)
            if refreshed:
                member = refreshed
            roles_after = _member_role_ids(guild=guild, member=member)

            # Store result
            await purge_service.add_user_result(
                purge_id=purge_id,
                user_id=member.id,
                action_type="promoted",
                roles_before=roles_before,
                roles_after=roles_after,
                in_affected_group=in_affected,
            )

            # Audit level 2: log each user
            if audit_level >= 2:
                msg_template = config.get(
                    ConfigKey.EXEC_MSG_USER_PROMOTED,
                    "  ↳ ⬆️ Promoted: {user} ({from_role} → {to_role})",
                )
                msg = format_message(
                    msg_template,
                    user=member.display_name,
                    from_role=from_role.name,
                    to_role=to_role.name,
                )
                execution_logs.append(msg)

            promoted_users.add(member.id)
            if in_affected:
                promoted_in_group += 1
            else:
                promoted_not_in_group += 1

    # Apply default promotion to confirmed users without any promotion
    if default_promotion:
        default_role = guild.get_role(default_promotion)
        if default_role:
            # Log level 2 message
            if audit_level >= 2:
                msg_template = config.get(
                    ConfigKey.EXEC_MSG_PROMOTION_DEFAULT,
                    "📈 Applying default promotion ({role})...",
                )
                msg = format_message(msg_template, role=default_role.name)
                execution_logs.append(msg)

            for user_id in confirmed_users:
                if user_id in promoted_users:
                    continue
                if user_id in processed_users:
                    continue

                default_member = guild.get_member(user_id)
                if not default_member:
                    continue

                roles_before = _member_role_ids(guild=guild, member=default_member)

                try:
                    await default_member.add_roles(default_role)
                except discord.Forbidden:
                    logger.warning(
                        f"[{guild.name}] Could not apply role to non-affected user: "
                        f"{default_member.name}"
                    )
                except discord.HTTPException as e:
                    logger.warning(
                        f"[{guild.name}] Could not apply role to non-affected user "
                        f"{default_member.name}: {e}"
                    )

                # Refresh member and get roles_after
                refreshed = guild.get_member(default_member.id)
                if refreshed:
                    default_member = refreshed
                roles_after = _member_role_ids(guild=guild, member=default_member)

                # Store result
                await purge_service.add_user_result(
                    purge_id=purge_id,
                    user_id=default_member.id,
                    action_type="promoted",
                    roles_before=roles_before,
                    roles_after=roles_after,
                    in_affected_group=False,
                )

                # Audit level 2: log each user
                if audit_level >= 2:
                    msg_template = config.get(
                        ConfigKey.EXEC_MSG_USER_PROMOTED_DEFAULT,
                        "  ↳ ⬆️ Promoted: {user} (→ {role})",
                    )
                    msg = format_message(
                        msg_template,
                        user=default_member.display_name,
                        role=default_role.name,
                    )
                    execution_logs.append(msg)

                promoted_users.add(user_id)
                promoted_not_in_group += 1

            # Update mod message after default promotions
            if audit_level >= 1:
                await cog._update_mod_message(
                    guild=guild,
                    record=record,
                    config=config,
                    execution_logs=execution_logs,
                )

    return promoted_in_group, promoted_not_in_group, promoted_users


async def _execute_global_removal_phase(
    cog: PurgeCog,
    guild: discord.Guild,
    record: PurgeRecord,
    config: dict[str, Any],
    global_roles_to_remove: list[int],
    audit_level: int,
    execution_logs: MutableSequence[str],
) -> int:
    """Execute global role removal phase.

    Removes specified roles from ALL server members,
    regardless of whether they reacted or are in affected roles.

    Args:
        cog (PurgeCog): Cog instance.
        guild (discord.Guild): Discord guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Cog configuration.
        global_roles_to_remove (list[int]): Role IDs to remove globally.
        audit_level (int): Audit level.
        execution_logs (MutableSequence[str]): Execution log lines.

    Returns:
        int: Number of users whose roles were removed.
    """
    # Get role objects
    roles_to_remove: list[discord.Role] = [
        role for rid in global_roles_to_remove if (role := guild.get_role(rid))
    ]

    if not roles_to_remove:
        return 0

    # Level 1 message
    if audit_level >= 1:
        msg = config.get(
            ConfigKey.EXEC_MSG_GLOBAL_REMOVE_START,
            "🧹 **Removing global roles...**",
        )
        execution_logs.append(msg)

    removed_count = 0

    for member in guild.members:
        if member.bot:
            continue

        # Find which global roles this member has
        member_roles_to_remove = [r for r in roles_to_remove if r in member.roles]
        if not member_roles_to_remove:
            continue

        try:
            await member.remove_roles(*member_roles_to_remove)
            removed_count += 1

            # Audit level 2: log each user
            if audit_level >= 2:
                role_names = ", ".join(r.name for r in member_roles_to_remove)
                msg_template = config.get(
                    ConfigKey.EXEC_MSG_GLOBAL_REMOVE_USER,
                    "  ↳ 🧹 Roles removed: {user} ({roles})",
                )
                msg = format_message(
                    msg_template,
                    user=member.display_name,
                    roles=role_names,
                )
                execution_logs.append(msg)

        except discord.Forbidden:
            logger.warning(f"[{guild.name}] Could not remove global roles from {member.name}")
        except discord.HTTPException as e:
            logger.warning(f"[{guild.name}] Could not remove global roles from {member.name}: {e}")

    # Update moderation message after global removal
    if audit_level >= 1:
        await cog._update_mod_message(
            guild=guild,
            record=record,
            config=config,
            execution_logs=execution_logs,
        )

    return removed_count
