"""Purge execution phases: cleaning, promotions and global role removal.

Each phase walks the guild members, applies role changes through a single
``member.edit`` call where possible, records per-user results through a
``UserResultSink`` and appends audit lines to the bounded execution log.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import MutableSequence
from typing import TYPE_CHECKING, Any, NamedTuple

import discord

from discord_bot.purge.enums import ConfigKey
from discord_bot.purge.formatters import format_message
from discord_bot.purge.models import PurgeRecord
from discord_bot.purge.results import UserResultSink

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


class PhaseContext(NamedTuple):
    """Live objects shared by every step of a phase."""

    cog: PurgeCog
    guild: discord.Guild
    record: PurgeRecord
    config: dict[str, Any]
    audit_level: int
    execution_logs: MutableSequence[str]


def _append_log(
    ctx: PhaseContext, min_level: int, key: ConfigKey, default: str, **values: str
) -> None:
    """Append a formatted audit line if the audit level allows it.

    Args:
        ctx (PhaseContext): Phase context.
        min_level (int): Minimum audit level required to log the line.
        key (ConfigKey): Config key holding the message template.
        default (str): Template used when the key is not configured.
        **values (str): Placeholder values for the template.
    """
    if ctx.audit_level < min_level:
        return
    ctx.execution_logs.append(format_message(ctx.config.get(key, default), **values))


async def _update_progress(ctx: PhaseContext) -> None:
    """Refresh the moderation message with the current log (audit level >= 1).

    Args:
        ctx (PhaseContext): Phase context.
    """
    if ctx.audit_level < 1:
        return
    await ctx.cog._update_mod_message(
        guild=ctx.guild,
        record=ctx.record,
        config=ctx.config,
        execution_logs=ctx.execution_logs,
    )


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

    Roles the bot cannot manage (at or above its top role, or managed by an
    integration/boost) are never removed or added: ``member.edit`` would reject
    the whole change otherwise, leaving the member untouched. They are kept as
    they are and logged.

    Args:
        guild (discord.Guild): Discord guild.
        member (discord.Member): Member whose roles are being changed.
        remove_ids (set[int] | None): Role IDs to drop; ``None`` drops every role.
        add_ids (list[int]): Role IDs to add (unknown IDs are ignored).

    Returns:
        list[discord.Role]: Kept roles followed by newly added ones.
    """
    kept: list[discord.Role] = []
    unmanageable: list[str] = []
    for role in member.roles:
        if role == guild.default_role:
            continue
        drop = remove_ids is None or role.id in remove_ids
        if drop and not role.is_assignable():
            unmanageable.append(role.name)
            drop = False
        if not drop:
            kept.append(role)

    for rid in add_ids:
        added = guild.get_role(rid)
        if added is None or added in kept:
            continue
        if not added.is_assignable():
            unmanageable.append(added.name)
            continue
        kept.append(added)

    if unmanageable:
        logger.warning(
            f"[{guild.name}] Skipping roles the bot cannot manage for {member.name}: "
            f"{', '.join(unmanageable)}"
        )
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


def _refreshed_member(guild: discord.Guild, member: discord.Member) -> discord.Member:
    """Return the cached member after a role edit, falling back to the given one.

    Args:
        guild (discord.Guild): Discord guild.
        member (discord.Member): Member just edited.

    Returns:
        discord.Member: Up-to-date member object.
    """
    return guild.get_member(member.id) or member


async def apply_cleaning_to_member(
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

    member = _refreshed_member(guild=guild, member=member)
    roles_after = _member_role_ids(guild=guild, member=member)

    await purge_service.add_user_result(
        purge_id=purge_id,
        user_id=member.id,
        action_type="cleaned",
        roles_before=roles_before,
        roles_after=roles_after,
    )

    return member, roles_before, roles_after


async def _clean_member(
    ctx: PhaseContext,
    member: discord.Member,
    roles_to_remove: list[int],
    roles_to_add: list[int],
    purge_service: UserResultSink,
    purge_id: int,
) -> discord.Member:
    """Clean one member and log it at audit level 2.

    Args:
        ctx (PhaseContext): Phase context.
        member (discord.Member): Member to clean.
        roles_to_remove (list[int]): Role IDs to remove; empty removes every role.
        roles_to_add (list[int]): Role IDs to add.
        purge_service (UserResultSink): Where to record the per-user result.
        purge_id (int): Purge ID.

    Returns:
        discord.Member: The refreshed member.
    """
    member, _, _ = await apply_cleaning_to_member(
        guild=ctx.guild,
        member=member,
        roles_to_remove=roles_to_remove,
        roles_to_add=roles_to_add,
        purge_service=purge_service,
        purge_id=purge_id,
    )
    _append_log(
        ctx=ctx,
        min_level=2,
        key=ConfigKey.EXEC_MSG_USER_CLEANED,
        default="  ↳ 🧹 Purged: {user}",
        user=member.display_name,
    )
    return member


async def execute_cleaning_phase(
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
    ctx = PhaseContext(
        cog=cog,
        guild=guild,
        record=record,
        config=config,
        audit_level=audit_level,
        execution_logs=execution_logs,
    )
    processed_users: set[int] = set()

    for role_id in affected_roles:
        role = guild.get_role(role_id)
        if not role:
            continue
        _append_log(
            ctx=ctx,
            min_level=2,
            key=ConfigKey.EXEC_MSG_CLEANING_ROLE,
            default="🧹 Applying purge to role {role}...",
            role=role.name,
        )
        for member in role.members:
            if member.id in confirmed_users or member.id in processed_users:
                continue
            member = await _clean_member(
                ctx=ctx,
                member=member,
                roles_to_remove=roles_to_remove,
                roles_to_add=roles_to_add,
                purge_service=purge_service,
                purge_id=purge_id,
            )
            processed_users.add(member.id)
        # Show progress after each role
        await _update_progress(ctx)

    return len(processed_users), processed_users


async def execute_global_cleaning_phase(
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

    Affects ALL members except bots, confirmed users and those with excluded roles.

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
    ctx = PhaseContext(
        cog=cog,
        guild=guild,
        record=record,
        config=config,
        audit_level=audit_level,
        execution_logs=execution_logs,
    )
    excluded_role_objs: set[discord.Role] = {
        role for rid in excluded_roles if (role := guild.get_role(rid))
    }
    _append_log(
        ctx=ctx,
        min_level=1,
        key=ConfigKey.EXEC_MSG_CLEANING_START,
        default="🧹 **Applying global purge...**",
    )

    processed_users: set[int] = set()
    for member in guild.members:
        if member.bot or member.id in confirmed_users or member.id in processed_users:
            continue
        if any(role in excluded_role_objs for role in member.roles):
            continue
        member = await _clean_member(
            ctx=ctx,
            member=member,
            roles_to_remove=roles_to_remove,
            roles_to_add=roles_to_add,
            purge_service=purge_service,
            purge_id=purge_id,
        )
        processed_users.add(member.id)

    await _update_progress(ctx)
    return len(processed_users), processed_users


def build_promotion_map(promotions: list[dict[str, Any]]) -> dict[int, int]:
    """Build the from_role_id → to_role_id map from the configured promotions.

    Args:
        promotions (list[dict[str, Any]]): Promotion entries with ``from_role``/``to_role``.

    Returns:
        dict[int, int]: Promotion map (legacy string IDs are coerced to int).
    """
    promotion_map: dict[int, int] = {}
    for promo in promotions:
        from_role = promo.get("from_role")
        to_role = promo.get("to_role")
        if from_role and to_role:
            promotion_map[int(from_role)] = int(to_role)
    return promotion_map


async def _promote_member(
    ctx: PhaseContext,
    member: discord.Member,
    from_role: discord.Role,
    to_role: discord.Role,
    in_affected: bool,
    purge_service: UserResultSink,
    purge_id: int,
) -> discord.Member:
    """Promote one member from ``from_role`` to ``to_role`` and record it.

    If ``from_role`` is an affected role it is swapped for ``to_role``;
    otherwise ``to_role`` is simply added.

    Args:
        ctx (PhaseContext): Phase context.
        member (discord.Member): Member to promote.
        from_role (discord.Role): Source role.
        to_role (discord.Role): Target role.
        in_affected (bool): Whether the source role is an affected role.
        purge_service (UserResultSink): Where to record the per-user result.
        purge_id (int): Purge ID.

    Returns:
        discord.Member: The refreshed member.
    """
    roles_before = _member_role_ids(guild=ctx.guild, member=member)
    target_roles = _replacement_roles(
        guild=ctx.guild,
        member=member,
        remove_ids={from_role.id} if in_affected else set(),
        add_ids=[to_role.id],
    )
    await _set_member_roles(guild=ctx.guild, member=member, roles=target_roles, what="promote")

    member = _refreshed_member(guild=ctx.guild, member=member)
    await purge_service.add_user_result(
        purge_id=purge_id,
        user_id=member.id,
        action_type="promoted",
        roles_before=roles_before,
        roles_after=_member_role_ids(guild=ctx.guild, member=member),
        in_affected_group=in_affected,
    )
    _append_log(
        ctx=ctx,
        min_level=2,
        key=ConfigKey.EXEC_MSG_USER_PROMOTED,
        default="  ↳ ⬆️ Promoted: {user} ({from_role} → {to_role})",
        user=member.display_name,
        from_role=from_role.name,
        to_role=to_role.name,
    )
    return member


async def _apply_role_promotions(
    ctx: PhaseContext,
    promotion_map: dict[int, int],
    affected_roles: list[int],
    confirmed_users: set[int],
    purge_service: UserResultSink,
    purge_id: int,
) -> tuple[int, int, set[int]]:
    """Promote confirmed members holding a mapped source role.

    Args:
        ctx (PhaseContext): Phase context.
        promotion_map (dict[int, int]): from_role_id → to_role_id.
        affected_roles (list[int]): Affected role IDs.
        confirmed_users (set[int]): Confirmed user IDs.
        purge_service (UserResultSink): Where to record per-user results.
        purge_id (int): Purge ID.

    Returns:
        tuple[int, int, set[int]]: (promoted_in_group, promoted_not_in_group, promoted_users)
    """
    promoted_in_group = 0
    promoted_not_in_group = 0
    promoted_users: set[int] = set()

    for from_role_id, to_role_id in promotion_map.items():
        from_role = ctx.guild.get_role(from_role_id)
        to_role = ctx.guild.get_role(to_role_id)
        if not from_role or not to_role:
            continue
        _append_log(
            ctx=ctx,
            min_level=2,
            key=ConfigKey.EXEC_MSG_PROMOTION_ROLE,
            default="📈 Promoting {from_role} → {to_role}...",
            from_role=from_role.name,
            to_role=to_role.name,
        )
        in_affected = from_role_id in affected_roles
        for member in from_role.members:
            if member.id not in confirmed_users or member.id in promoted_users:
                continue
            member = await _promote_member(
                ctx=ctx,
                member=member,
                from_role=from_role,
                to_role=to_role,
                in_affected=in_affected,
                purge_service=purge_service,
                purge_id=purge_id,
            )
            promoted_users.add(member.id)
            if in_affected:
                promoted_in_group += 1
            else:
                promoted_not_in_group += 1

    return promoted_in_group, promoted_not_in_group, promoted_users


async def _promote_member_default(
    ctx: PhaseContext,
    member: discord.Member,
    default_role: discord.Role,
    purge_service: UserResultSink,
    purge_id: int,
) -> None:
    """Add the default promotion role to a member and record it.

    Args:
        ctx (PhaseContext): Phase context.
        member (discord.Member): Member to promote.
        default_role (discord.Role): Default promotion role.
        purge_service (UserResultSink): Where to record the per-user result.
        purge_id (int): Purge ID.
    """
    guild = ctx.guild
    roles_before = _member_role_ids(guild=guild, member=member)
    try:
        await member.add_roles(default_role)
    except discord.Forbidden:
        logger.warning(f"[{guild.name}] Could not apply role to non-affected user: {member.name}")
    except discord.HTTPException as e:
        logger.warning(
            f"[{guild.name}] Could not apply role to non-affected user {member.name}: {e}"
        )

    member = _refreshed_member(guild=guild, member=member)
    await purge_service.add_user_result(
        purge_id=purge_id,
        user_id=member.id,
        action_type="promoted",
        roles_before=roles_before,
        roles_after=_member_role_ids(guild=guild, member=member),
        in_affected_group=False,
    )
    _append_log(
        ctx=ctx,
        min_level=2,
        key=ConfigKey.EXEC_MSG_USER_PROMOTED_DEFAULT,
        default="  ↳ ⬆️ Promoted: {user} (→ {role})",
        user=member.display_name,
        role=default_role.name,
    )


async def _apply_default_promotion(
    ctx: PhaseContext,
    default_role: discord.Role,
    confirmed_users: set[int],
    skip_users: set[int],
    purge_service: UserResultSink,
    purge_id: int,
) -> set[int]:
    """Give the default promotion to confirmed users that got no other promotion.

    Args:
        ctx (PhaseContext): Phase context.
        default_role (discord.Role): Default promotion role.
        confirmed_users (set[int]): Confirmed user IDs.
        skip_users (set[int]): Users already promoted or cleaned.
        purge_service (UserResultSink): Where to record per-user results.
        purge_id (int): Purge ID.

    Returns:
        set[int]: IDs of the users that received the default promotion.
    """
    _append_log(
        ctx=ctx,
        min_level=2,
        key=ConfigKey.EXEC_MSG_PROMOTION_DEFAULT,
        default="📈 Applying default promotion ({role})...",
        role=default_role.name,
    )
    promoted: set[int] = set()
    for user_id in confirmed_users:
        if user_id in skip_users:
            continue
        member = ctx.guild.get_member(user_id)
        if not member:
            continue
        await _promote_member_default(
            ctx=ctx,
            member=member,
            default_role=default_role,
            purge_service=purge_service,
            purge_id=purge_id,
        )
        promoted.add(user_id)

    await _update_progress(ctx)
    return promoted


async def execute_promotion_phase(
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
    ctx = PhaseContext(
        cog=cog,
        guild=guild,
        record=record,
        config=config,
        audit_level=audit_level,
        execution_logs=execution_logs,
    )
    promoted_in_group, promoted_not_in_group, promoted_users = await _apply_role_promotions(
        ctx=ctx,
        promotion_map=build_promotion_map(promotions),
        affected_roles=affected_roles,
        confirmed_users=confirmed_users,
        purge_service=purge_service,
        purge_id=purge_id,
    )

    default_role = guild.get_role(default_promotion) if default_promotion else None
    if default_role:
        default_promoted = await _apply_default_promotion(
            ctx=ctx,
            default_role=default_role,
            confirmed_users=confirmed_users,
            skip_users=promoted_users | processed_users,
            purge_service=purge_service,
            purge_id=purge_id,
        )
        promoted_users = promoted_users | default_promoted
        promoted_not_in_group += len(default_promoted)

    return promoted_in_group, promoted_not_in_group, promoted_users


async def _remove_global_roles(
    ctx: PhaseContext, member: discord.Member, roles: list[discord.Role]
) -> bool:
    """Remove the given global roles from a member and log it.

    Args:
        ctx (PhaseContext): Phase context.
        member (discord.Member): Member to update.
        roles (list[discord.Role]): Roles the member currently holds to remove.

    Returns:
        bool: True if the roles were removed.
    """
    try:
        await member.remove_roles(*roles)
    except discord.Forbidden:
        logger.warning(f"[{ctx.guild.name}] Could not remove global roles from {member.name}")
        return False
    except discord.HTTPException as e:
        logger.warning(f"[{ctx.guild.name}] Could not remove global roles from {member.name}: {e}")
        return False
    _append_log(
        ctx=ctx,
        min_level=2,
        key=ConfigKey.EXEC_MSG_GLOBAL_REMOVE_USER,
        default="  ↳ 🧹 Roles removed: {user} ({roles})",
        user=member.display_name,
        roles=", ".join(r.name for r in roles),
    )
    return True


async def execute_global_removal_phase(
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
    roles_to_remove: list[discord.Role] = [
        role for rid in global_roles_to_remove if (role := guild.get_role(rid))
    ]
    if not roles_to_remove:
        return 0

    ctx = PhaseContext(
        cog=cog,
        guild=guild,
        record=record,
        config=config,
        audit_level=audit_level,
        execution_logs=execution_logs,
    )
    _append_log(
        ctx=ctx,
        min_level=1,
        key=ConfigKey.EXEC_MSG_GLOBAL_REMOVE_START,
        default="🧹 **Removing global roles...**",
    )

    removed_count = 0
    for member in guild.members:
        if member.bot:
            continue
        member_roles = [r for r in roles_to_remove if r in member.roles]
        if not member_roles:
            continue
        if await _remove_global_roles(ctx=ctx, member=member, roles=member_roles):
            removed_count += 1

    await _update_progress(ctx)
    return removed_count
