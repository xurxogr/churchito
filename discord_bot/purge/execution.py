"""Purge execution logic."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.common.utils import delete_message
from discord_bot.purge.enums import ConfigKey, PurgeStatus, PurgeType
from discord_bot.purge.formatters import format_message
from discord_bot.purge.models import PurgeRecord
from discord_bot.purge.service import PurgeService

if TYPE_CHECKING:
    from discord_bot.purge.cog import PurgeCog

logger = logging.getLogger(__name__)


async def _apply_cleaning_to_member(
    guild: discord.Guild,
    member: discord.Member,
    roles_to_remove: list[int],
    roles_to_add: list[int],
    purge_service: PurgeService,
    purge_id: int,
) -> tuple[discord.Member, list[int], list[int]]:
    """Apply role cleaning to a member.

    Args:
        guild (discord.Guild): Discord guild.
        member (discord.Member): Member to clean.
        roles_to_remove (list[int]): Role IDs to remove.
        roles_to_add (list[int]): Role IDs to add.
        purge_service (PurgeService): Purge service.
        purge_id (int): Purge ID.

    Returns:
        tuple[discord.Member, list[int], list[int]]: Member, roles before, roles after
    """
    roles_before = [r.id for r in member.roles if r != guild.default_role]

    # Remove roles
    if roles_to_remove:
        roles_to_rm: list[discord.Role] = [
            rm_role
            for rid in roles_to_remove
            if (rm_role := guild.get_role(rid)) and rm_role in member.roles
        ]
        if roles_to_rm:
            try:
                await member.remove_roles(*roles_to_rm)
            except discord.Forbidden:
                logger.warning(f"[{guild.name}] Could not remove roles from {member.name}")
    else:
        # Remove all roles
        try:
            await member.edit(roles=[])
        except discord.Forbidden:
            logger.warning(f"[{guild.name}] Could not remove roles from {member.name}")

    # Add purge roles
    if roles_to_add:
        roles_to_give: list[discord.Role] = [
            add_role for rid in roles_to_add if (add_role := guild.get_role(rid))
        ]
        if roles_to_give:
            try:
                await member.add_roles(*roles_to_give)
            except discord.Forbidden:
                logger.warning(f"[{guild.name}] Could not add roles to {member.name}")

    # Refresh member
    refreshed = guild.get_member(member.id)
    if refreshed:
        member = refreshed
    roles_after = [r.id for r in member.roles if r != guild.default_role]

    # Save result
    await purge_service.add_user_result(
        purge_id=purge_id,
        user_id=member.id,
        action_type="cleaned",
        roles_before=roles_before,
        roles_after=roles_after,
    )

    return member, roles_before, roles_after


async def execute_purge(
    cog: PurgeCog,
    guild_id: int,
    purge_id: int,
) -> None:
    """Execute a purge.

    Args:
        cog (PurgeCog): Cog instance.
        guild_id (int): Guild ID.
        purge_id (int): Purge ID.
    """
    guild = cog.bot.get_guild(guild_id)
    if not guild:
        logger.error(f"[Guild ID: {guild_id}] Guild not found to execute purge {purge_id}")
        return

    async with cog.bot.database.session() as session:
        purge_service = PurgeService(session)
        record = await purge_service.get_purge(purge_id)

        if not record or record.status != PurgeStatus.AUTHORIZED:
            logger.warning(f"[{guild.name}] Purge (ID: {purge_id}) is not in authorized status")
            return

        config = await cog._get_config(guild_id)
        test_mode = record.config_snapshot.get("test_mode", False)
        audit_level = config.get(ConfigKey.AUDIT_LEVEL, 1)

        logger.info(
            f"[{guild.name}] {'[TEST MODE] ' if test_mode else ''}Executing purge {purge_id}"
        )

        # Detect purge type
        purge_type = PurgeType(record.purge_type)

        # Config from snapshot (common)
        roles_to_remove = record.config_snapshot.get("roles_to_remove", [])
        roles_to_add = record.config_snapshot.get("roles_to_add", [])
        confirmed_users = set(record.confirmed_by)

        # Type-specific config
        if purge_type == PurgeType.GLOBAL:
            excluded_roles: list[int] = record.config_snapshot.get("excluded_roles", [])
            affected_roles: list[int] = []
            promotions: list[dict[str, int]] = []
            default_promotion = None
        else:
            excluded_roles = []
            affected_roles = record.config_snapshot.get("affected_roles", [])
            promotions = record.config_snapshot.get("promotions", [])
            default_promotion = record.config_snapshot.get("default_promotion")

        # Stats
        cleaned_count = 0
        promoted_in_group = 0
        promoted_not_in_group = 0
        processed_users: set[int] = set()

        # Execution logs (will be added to mod message)
        execution_logs: list[str] = []

        # Add simulation indicator once at the start
        if test_mode:
            simulation_msg = config.get(ConfigKey.EXEC_MSG_SIMULATION, "🧪 **[TEST MODE]**")
            execution_logs.append(simulation_msg)

        # === LOG INIT MESSAGE (level 1) ===
        if audit_level >= 1:
            msg = config.get(ConfigKey.EXEC_MSG_INIT, "🔥 **Starting purge...**")
            execution_logs.append(msg)

            # Send start log to logs channel
            await cog._send_log(
                guild=guild,
                config=config,
                public_id=record.public_id,
                message=msg,
                audit_level_required=1,
            )

        # === PHASE 1: CLEAN NON-CONFIRMED USERS ===
        if purge_type == PurgeType.GLOBAL:
            # Global purge: affects everyone except excluded roles
            cleaned_count, processed_users = await _execute_global_cleaning_phase(
                cog=cog,
                guild=guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                excluded_roles=excluded_roles,
                roles_to_remove=roles_to_remove,
                roles_to_add=roles_to_add,
                confirmed_users=confirmed_users,
                audit_level=audit_level,
                execution_logs=execution_logs,
            )
        else:
            # War purge: affects only specific roles
            cleaned_count, processed_users = await _execute_cleaning_phase(
                cog=cog,
                guild=guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                affected_roles=affected_roles,
                roles_to_remove=roles_to_remove,
                roles_to_add=roles_to_add,
                confirmed_users=confirmed_users,
                audit_level=audit_level,
                execution_logs=execution_logs,
            )

        # === PHASE 2: APPLY PROMOTIONS (war purge only) ===
        promoted_users: set[int] = set()
        if purge_type != PurgeType.GLOBAL:
            if audit_level >= 1:
                msg = config.get(
                    ConfigKey.EXEC_MSG_PROMOTIONS_START, "⬆️ **Applying promotions...**"
                )
                execution_logs.append(msg)

            (
                promoted_in_group,
                promoted_not_in_group,
                promoted_users,
            ) = await _execute_promotion_phase(
                cog=cog,
                guild=guild,
                record=record,
                config=config,
                purge_service=purge_service,
                purge_id=purge_id,
                affected_roles=affected_roles,
                promotions=promotions,
                default_promotion=default_promotion,
                confirmed_users=confirmed_users,
                processed_users=processed_users,
                audit_level=audit_level,
                execution_logs=execution_logs,
            )

        # === PHASE 3: REMOVE GLOBAL ROLES FROM EVERYONE (war purge only) ===
        global_roles_to_remove = record.config_snapshot.get("global_roles_to_remove", [])
        if global_roles_to_remove:
            global_removed_count = await _execute_global_removal_phase(
                cog=cog,
                guild=guild,
                record=record,
                config=config,
                global_roles_to_remove=global_roles_to_remove,
                audit_level=audit_level,
                execution_logs=execution_logs,
            )
        else:
            global_removed_count = 0

        # === REMOVE REACTION ROLE FROM ALL CONFIRMED ===
        reaction_role_id = record.config_snapshot.get("reaction_role")
        if reaction_role_id:
            reaction_role = guild.get_role(reaction_role_id)
            if reaction_role:
                for user_id in confirmed_users:
                    reaction_member = guild.get_member(user_id)
                    if reaction_member and reaction_role in reaction_member.roles:
                        try:
                            await reaction_member.remove_roles(reaction_role)
                        except discord.Forbidden:
                            logger.warning(
                                f"[{guild.name}] Could not remove reaction role "
                                f"from {reaction_member.name}"
                            )

        # === GENERATE FINISH MESSAGE ===
        if purge_type == PurgeType.GLOBAL:
            finish_msg_template = config.get(
                ConfigKey.GLOBAL_EXEC_MSG_FINISH,
                "✅ **Global purge completed.**\n\n🧹 Users purged: {cleaned}",
            )
            finish_msg = format_message(finish_msg_template, cleaned=str(cleaned_count))
        else:
            finish_msg_template = config.get(
                ConfigKey.WAR_EXEC_MSG_FINISH,
                "✅ **Purge completed.**\n\n"
                "🧹 Purged: {cleaned}\n"
                "⬆️ Promoted (group): {promoted_in_group}\n"
                "⬆️ Promoted (others): {promoted_not_in_group}\n"
                "🗑️ Global roles removed: {global_removed}",
            )
            finish_msg = format_message(
                finish_msg_template,
                cleaned=str(cleaned_count),
                promoted_in_group=str(promoted_in_group),
                promoted_not_in_group=str(promoted_not_in_group),
                global_removed=str(global_removed_count),
            )

        # === LOG FINISH MESSAGE (level 1) ===
        if audit_level >= 1:
            execution_logs.append(finish_msg)

        # Update execution result
        execution_result = {
            "test_mode": test_mode,
            "confirmed_count": len(confirmed_users),
            "cleaned_count": cleaned_count,
            "promoted_in_group": promoted_in_group,
            "promoted_not_in_group": promoted_not_in_group,
            "global_removed_count": global_removed_count,
        }

        record = await purge_service.update_status(
            purge_id=purge_id,
            status=PurgeStatus.EXECUTED,
            execution_result=execution_result,
        )

        if record:
            # Delete user message
            if record.user_message_id and record.user_channel_id:
                await delete_message(
                    guild=guild,
                    channel_id=record.user_channel_id,
                    message_id=record.user_message_id,
                )

            # Update moderation message with final logs
            await cog._update_mod_message(
                guild=guild,
                record=record,
                config=config,
                remove_view=True,
                execution_logs=execution_logs if audit_level >= 1 else None,
            )

            # Schedule deletion if retention is configured
            cog._maybe_schedule_mod_message_deletion(record=record, config=config)

            logger.info(
                f"[{guild.name}] {'[TEST MODE] ' if test_mode else ''}"
                f"Purge {purge_id} executed: cleaned={cleaned_count}, "
                f"promoted_in={promoted_in_group}, promoted_out={promoted_not_in_group}, "
                f"global_removed={global_removed_count}"
            )

            # Send completion log to logs channel
            await cog._send_log(
                guild=guild,
                config=config,
                public_id=record.public_id,
                message=finish_msg,
            )

        await session.commit()


async def _execute_cleaning_phase(
    cog: PurgeCog,
    guild: discord.Guild,
    record: PurgeRecord,
    config: dict[str, Any],
    purge_service: PurgeService,
    purge_id: int,
    affected_roles: list[int],
    roles_to_remove: list[int],
    roles_to_add: list[int],
    confirmed_users: set[int],
    audit_level: int,
    execution_logs: list[str],
) -> tuple[int, set[int]]:
    """Execute cleaning phase for non-confirmed users.

    Args:
        cog (PurgeCog): Cog instance.
        guild (discord.Guild): Discord guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Cog configuration.
        purge_service (PurgeService): Purge service.
        purge_id (int): Purge ID.
        affected_roles (list[int]): Affected role IDs.
        roles_to_remove (list[int]): Role IDs to remove.
        roles_to_add (list[int]): Role IDs to add.
        confirmed_users (set[int]): Confirmed user IDs.
        audit_level (int): Audit level.
        execution_logs (list[str]): Execution logs list.

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
    purge_service: PurgeService,
    purge_id: int,
    excluded_roles: list[int],
    roles_to_remove: list[int],
    roles_to_add: list[int],
    confirmed_users: set[int],
    audit_level: int,
    execution_logs: list[str],
) -> tuple[int, set[int]]:
    """Execute global cleaning phase for non-confirmed users.

    Affects ALL members except those with excluded roles.

    Args:
        cog (PurgeCog): Cog instance.
        guild (discord.Guild): Discord guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Cog configuration.
        purge_service (PurgeService): Purge service.
        purge_id (int): Purge ID.
        excluded_roles (list[int]): Excluded role IDs.
        roles_to_remove (list[int]): Role IDs to remove.
        roles_to_add (list[int]): Role IDs to add.
        confirmed_users (set[int]): Confirmed user IDs.
        audit_level (int): Audit level.
        execution_logs (list[str]): Execution logs list.

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
    purge_service: PurgeService,
    purge_id: int,
    affected_roles: list[int],
    promotions: list[dict[str, Any]],
    default_promotion: int | None,
    confirmed_users: set[int],
    processed_users: set[int],
    audit_level: int,
    execution_logs: list[str],
) -> tuple[int, int, set[int]]:
    """Execute promotions phase.

    Args:
        cog (PurgeCog): Cog instance.
        guild (discord.Guild): Discord guild.
        record (PurgeRecord): Purge record.
        config (dict[str, Any]): Cog configuration.
        purge_service (PurgeService): Purge service.
        purge_id (int): Purge ID.
        affected_roles (list[int]): Affected role IDs.
        promotions (list[dict[str, Any]]): Promotions list.
        default_promotion (int | None): Default promotion role.
        confirmed_users (set[int]): Confirmed user IDs.
        processed_users (set[int]): Already processed user IDs.
        audit_level (int): Audit level.
        execution_logs (list[str]): Execution logs list.

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

            roles_before = [r.id for r in member.roles if r != guild.default_role]
            in_affected = from_role_id in affected_roles

            try:
                # If from_role is in affected_roles, remove it
                if in_affected:
                    await member.remove_roles(from_role)
                await member.add_roles(to_role)
            except discord.Forbidden:
                logger.warning(f"[{guild.name}] Could not promote {member.name}")

            # Refresh member and get roles_after
            refreshed = guild.get_member(member.id)
            if refreshed:
                member = refreshed
            roles_after = [r.id for r in member.roles if r != guild.default_role]

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

                roles_before = [r.id for r in default_member.roles if r != guild.default_role]

                try:
                    await default_member.add_roles(default_role)
                except discord.Forbidden:
                    logger.warning(
                        f"[{guild.name}] Could not apply role to non-affected user: "
                        f"{default_member.name}"
                    )

                # Refresh member and get roles_after
                refreshed = guild.get_member(default_member.id)
                if refreshed:
                    default_member = refreshed
                roles_after = [r.id for r in default_member.roles if r != guild.default_role]

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
    execution_logs: list[str],
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
        execution_logs (list[str]): Execution logs list.

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

    # Update moderation message after global removal
    if audit_level >= 1:
        await cog._update_mod_message(
            guild=guild,
            record=record,
            config=config,
            execution_logs=execution_logs,
        )

    return removed_count
