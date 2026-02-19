"""Lógica de ejecución de purgas."""

import logging
from typing import TYPE_CHECKING, Any

import discord

from discord_bot.common.utils import delete_message
from discord_bot.purga.enums import ConfigKey, PurgaStatus, PurgaType
from discord_bot.purga.formatters import format_message
from discord_bot.purga.models import PurgaRecord
from discord_bot.purga.service import PurgaService

if TYPE_CHECKING:
    from discord_bot.purga.cog import PurgaCog

logger = logging.getLogger(__name__)


async def _apply_cleaning_to_member(
    guild: discord.Guild,
    member: discord.Member,
    roles_to_remove: list[int],
    roles_to_add: list[int],
    purga_service: PurgaService,
    purga_id: int,
) -> tuple[discord.Member, list[int], list[int]]:
    """Aplicar limpieza de roles a un miembro.

    Args:
        guild: Guild de Discord.
        member: Miembro a limpiar.
        roles_to_remove: IDs de roles a quitar.
        roles_to_add: IDs de roles a añadir.
        purga_service: Servicio de purga.
        purga_id: ID de la purga.

    Returns:
        tuple: (member_actualizado, roles_before, roles_after)
    """
    roles_before = [r.id for r in member.roles if r != guild.default_role]

    # Quitar roles
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
                logger.warning(f"No se pudo quitar roles a {member.name}")
    else:
        # Quitar todos los roles
        try:
            await member.edit(roles=[])
        except discord.Forbidden:
            logger.warning(f"No se pudo quitar roles a {member.name}")

    # Añadir roles de purga
    if roles_to_add:
        roles_to_give: list[discord.Role] = [
            add_role for rid in roles_to_add if (add_role := guild.get_role(rid))
        ]
        if roles_to_give:
            try:
                await member.add_roles(*roles_to_give)
            except discord.Forbidden:
                logger.warning(f"No se pudo añadir roles a {member.name}")

    # Refrescar miembro
    refreshed = guild.get_member(member.id)
    if refreshed:
        member = refreshed
    roles_after = [r.id for r in member.roles if r != guild.default_role]

    # Guardar resultado
    await purga_service.add_user_result(
        purga_id=purga_id,
        user_id=member.id,
        action_type="cleaned",
        roles_before=roles_before,
        roles_after=roles_after,
    )

    return member, roles_before, roles_after


async def execute_purga(
    cog: "PurgaCog",
    guild_id: int,
    purga_id: int,
) -> None:
    """Ejecutar una purga.

    Args:
        cog (PurgaCog): Instancia del cog.
        guild_id (int): ID del guild.
        purga_id (int): ID de la purga.
    """
    guild = cog.bot.get_guild(guild_id)
    if not guild:
        logger.error(f"Guild {guild_id} no encontrado para ejecutar purga {purga_id}")
        return

    async with cog.bot.database.session() as session:
        purga_service = PurgaService(session)
        record = await purga_service.get_purga(purga_id)

        if not record or record.status != PurgaStatus.AUTHORIZED:
            logger.warning(f"Purga {purga_id} no está en estado autorizado")
            return

        config = await cog._get_config(guild_id)
        test_mode = record.config_snapshot.get("test_mode", False)
        audit_level = config.get(ConfigKey.AUDIT_LEVEL, 1)

        logger.info(
            f"[{guild.name}] {'[MODO PRUEBA] ' if test_mode else ''}Ejecutando purga {purga_id}"
        )

        # Detectar tipo de purga
        purga_type = PurgaType(record.purga_type)

        # Config from snapshot (común)
        roles_to_remove = record.config_snapshot.get("roles_to_remove", [])
        roles_to_add = record.config_snapshot.get("roles_to_add", [])
        confirmed_users = set(record.confirmed_by)

        # Config específica según tipo
        if purga_type == PurgaType.GLOBAL:
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
            simulation_msg = config.get(ConfigKey.EXEC_MSG_SIMULATION, "🧪 **[MODO PRUEBA]**")
            execution_logs.append(simulation_msg)

        # === LOG INIT MESSAGE (level 1) ===
        if audit_level >= 1:
            msg = config.get(ConfigKey.EXEC_MSG_INIT, "🔥 **Iniciando purga...**")
            execution_logs.append(msg)

        # === PHASE 1: CLEAN NON-CONFIRMED USERS ===
        if purga_type == PurgaType.GLOBAL:
            # Purga global: afecta a todos excepto roles excluidos
            cleaned_count, processed_users = await _execute_global_cleaning_phase(
                cog=cog,
                guild=guild,
                record=record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
                excluded_roles=excluded_roles,
                roles_to_remove=roles_to_remove,
                roles_to_add=roles_to_add,
                confirmed_users=confirmed_users,
                audit_level=audit_level,
                execution_logs=execution_logs,
            )
        else:
            # Purga de guerra: afecta solo a roles específicos
            cleaned_count, processed_users = await _execute_cleaning_phase(
                cog=cog,
                guild=guild,
                record=record,
                config=config,
                purga_service=purga_service,
                purga_id=purga_id,
                affected_roles=affected_roles,
                roles_to_remove=roles_to_remove,
                roles_to_add=roles_to_add,
                confirmed_users=confirmed_users,
                audit_level=audit_level,
                execution_logs=execution_logs,
            )

        # === PHASE 2: APPLY PROMOTIONS (solo para purga de guerra) ===
        promoted_users: set[int] = set()
        if purga_type != PurgaType.GLOBAL:
            if audit_level >= 1:
                msg = config.get(
                    ConfigKey.EXEC_MSG_PROMOTIONS_START, "⬆️ **Aplicando promociones...**"
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
                purga_service=purga_service,
                purga_id=purga_id,
                affected_roles=affected_roles,
                promotions=promotions,
                default_promotion=default_promotion,
                confirmed_users=confirmed_users,
                processed_users=processed_users,
                audit_level=audit_level,
                execution_logs=execution_logs,
            )

        # === FASE 3: ELIMINAR ROLES GLOBALES DE TODOS (solo para purga de guerra) ===
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
                                f"No se pudo quitar rol de reacción a {reaction_member.name}"
                            )

        # === LOG FINISH MESSAGE (level 1) ===
        if audit_level >= 1:
            if purga_type == PurgaType.GLOBAL:
                msg_template = config.get(
                    ConfigKey.GLOBAL_EXEC_MSG_FINISH,
                    "✅ **Purga global finalizada.**\n\n🧹 Usuarios purgados: {cleaned}",
                )
                msg = format_message(msg_template, cleaned=str(cleaned_count))
            else:
                msg_template = config.get(
                    ConfigKey.WAR_EXEC_MSG_FINISH,
                    "✅ **Purga finalizada.**\n\n"
                    "🧹 Purgados: {cleaned}\n"
                    "⬆️ Promocionados (grupo): {promoted_in_group}\n"
                    "⬆️ Promocionados (otros): {promoted_not_in_group}\n"
                    "🗑️ Roles globales eliminados: {global_removed}",
                )
                msg = format_message(
                    msg_template,
                    cleaned=str(cleaned_count),
                    promoted_in_group=str(promoted_in_group),
                    promoted_not_in_group=str(promoted_not_in_group),
                    global_removed=str(global_removed_count),
                )
            execution_logs.append(msg)

        # Update execution result
        execution_result = {
            "test_mode": test_mode,
            "confirmed_count": len(confirmed_users),
            "cleaned_count": cleaned_count,
            "promoted_in_group": promoted_in_group,
            "promoted_not_in_group": promoted_not_in_group,
            "global_removed_count": global_removed_count,
        }

        record = await purga_service.update_status(
            purga_id=purga_id,
            status=PurgaStatus.EXECUTED,
            execution_result=execution_result,
        )

        if record:
            # Eliminar mensaje de usuarios
            if record.user_message_id and record.user_channel_id:
                await delete_message(
                    guild=guild,
                    channel_id=record.user_channel_id,
                    message_id=record.user_message_id,
                )

            # Actualizar mensaje de moderación con logs finales
            await cog._update_mod_message(
                guild=guild,
                record=record,
                config=config,
                remove_view=True,
                execution_logs=execution_logs if audit_level >= 1 else None,
            )

            # Programar eliminación si hay retención configurada
            cog._maybe_schedule_mod_message_deletion(record=record, config=config)

            logger.info(
                f"[{guild.name}] {'[MODO PRUEBA] ' if test_mode else ''}"
                f"Purga {purga_id} ejecutada: cleaned={cleaned_count}, "
                f"promoted_in={promoted_in_group}, promoted_out={promoted_not_in_group}, "
                f"global_removed={global_removed_count}"
            )

        await session.commit()


async def _execute_cleaning_phase(
    cog: "PurgaCog",
    guild: discord.Guild,
    record: PurgaRecord,
    config: dict[str, Any],
    purga_service: PurgaService,
    purga_id: int,
    affected_roles: list[int],
    roles_to_remove: list[int],
    roles_to_add: list[int],
    confirmed_users: set[int],
    audit_level: int,
    execution_logs: list[str],
) -> tuple[int, set[int]]:
    """Ejecutar fase de limpieza de usuarios no confirmados.

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
                "🧹 Aplicando purga al rol {role}...",
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
                purga_service=purga_service,
                purga_id=purga_id,
            )

            # Nivel de auditoría 2: registrar cada usuario
            if audit_level >= 2:
                msg_template = config.get(
                    ConfigKey.EXEC_MSG_USER_CLEANED,
                    "  ↳ 🧹 Purgado: {user}",
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
    cog: "PurgaCog",
    guild: discord.Guild,
    record: PurgaRecord,
    config: dict[str, Any],
    purga_service: PurgaService,
    purga_id: int,
    excluded_roles: list[int],
    roles_to_remove: list[int],
    roles_to_add: list[int],
    confirmed_users: set[int],
    audit_level: int,
    execution_logs: list[str],
) -> tuple[int, set[int]]:
    """Ejecutar fase de limpieza global para usuarios no confirmados.

    Afecta a TODOS los miembros excepto aquellos con roles excluidos.

    Returns:
        tuple[int, set[int]]: (cleaned_count, processed_users)
    """
    cleaned_count = 0
    processed_users: set[int] = set()

    # Obtener objetos de roles excluidos
    excluded_role_objs: set[discord.Role] = {
        role for rid in excluded_roles if (role := guild.get_role(rid))
    }

    # Log level 1 message
    if audit_level >= 1:
        msg_template = config.get(
            ConfigKey.EXEC_MSG_CLEANING_START,
            "🧹 **Aplicando purga global...**",
        )
        msg = format_message(msg_template)
        execution_logs.append(msg)

    # Iterar sobre todos los miembros del servidor
    for member in guild.members:
        # Saltar bots
        if member.bot:
            continue

        # Saltar miembros que confirmaron
        if member.id in confirmed_users:
            continue

        # Saltar miembros con roles excluidos
        if any(role in excluded_role_objs for role in member.roles):
            continue

        # Ya procesado
        if member.id in processed_users:
            continue

        member, _, _ = await _apply_cleaning_to_member(
            guild=guild,
            member=member,
            roles_to_remove=roles_to_remove,
            roles_to_add=roles_to_add,
            purga_service=purga_service,
            purga_id=purga_id,
        )

        # Nivel de auditoría 2: registrar cada usuario
        if audit_level >= 2:
            msg_template = config.get(
                ConfigKey.EXEC_MSG_USER_CLEANED,
                "  ↳ 🧹 Purgado: {user}",
            )
            msg = format_message(msg_template, user=member.display_name)
            execution_logs.append(msg)

        processed_users.add(member.id)
        cleaned_count += 1

    # Actualizar mensaje de moderación
    if audit_level >= 1:
        await cog._update_mod_message(
            guild=guild,
            record=record,
            config=config,
            execution_logs=execution_logs,
        )

    return cleaned_count, processed_users


async def _execute_promotion_phase(
    cog: "PurgaCog",
    guild: discord.Guild,
    record: PurgaRecord,
    config: dict[str, Any],
    purga_service: PurgaService,
    purga_id: int,
    affected_roles: list[int],
    promotions: list[dict[str, Any]],
    default_promotion: int | None,
    confirmed_users: set[int],
    processed_users: set[int],
    audit_level: int,
    execution_logs: list[str],
) -> tuple[int, int, set[int]]:
    """Ejecutar fase de promociones.

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
                "📈 Promocionando {from_role} → {to_role}...",
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
                logger.warning(f"No se pudo promocionar a {member.name}")

            # Refresh member and get roles_after
            refreshed = guild.get_member(member.id)
            if refreshed:
                member = refreshed
            roles_after = [r.id for r in member.roles if r != guild.default_role]

            # Store result
            await purga_service.add_user_result(
                purga_id=purga_id,
                user_id=member.id,
                action_type="promoted",
                roles_before=roles_before,
                roles_after=roles_after,
                in_affected_group=in_affected,
            )

            # Nivel de auditoría 2: registrar cada usuario
            if audit_level >= 2:
                msg_template = config.get(
                    ConfigKey.EXEC_MSG_USER_PROMOTED,
                    "  ↳ ⬆️ Promocionado: {user} ({from_role} → {to_role})",
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
                    "📈 Aplicando promoción por defecto ({role})...",
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
                        f"No se pudo aplicar rol a usuario no afectado: {default_member.name}"
                    )

                # Refresh member and get roles_after
                refreshed = guild.get_member(default_member.id)
                if refreshed:
                    default_member = refreshed
                roles_after = [r.id for r in default_member.roles if r != guild.default_role]

                # Store result
                await purga_service.add_user_result(
                    purga_id=purga_id,
                    user_id=default_member.id,
                    action_type="promoted",
                    roles_before=roles_before,
                    roles_after=roles_after,
                    in_affected_group=False,
                )

                # Nivel de auditoría 2: registrar cada usuario
                if audit_level >= 2:
                    msg_template = config.get(
                        ConfigKey.EXEC_MSG_USER_PROMOTED_DEFAULT,
                        "  ↳ ⬆️ Promocionado: {user} (→ {role})",
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
    cog: "PurgaCog",
    guild: discord.Guild,
    record: PurgaRecord,
    config: dict[str, Any],
    global_roles_to_remove: list[int],
    audit_level: int,
    execution_logs: list[str],
) -> int:
    """Ejecutar fase de eliminación de roles globales.

    Elimina los roles especificados de TODOS los miembros del servidor,
    independientemente de si reaccionaron o están en roles afectados.

    Returns:
        int: Número de usuarios a los que se les quitaron roles.
    """
    # Obtener objetos de rol
    roles_to_remove: list[discord.Role] = [
        role for rid in global_roles_to_remove if (role := guild.get_role(rid))
    ]

    if not roles_to_remove:
        return 0

    # Mensaje de nivel 1
    if audit_level >= 1:
        msg = config.get(
            ConfigKey.EXEC_MSG_GLOBAL_REMOVE_START,
            "🧹 **Eliminando roles globales...**",
        )
        execution_logs.append(msg)

    removed_count = 0

    for member in guild.members:
        if member.bot:
            continue

        # Buscar qué roles globales tiene este miembro
        member_roles_to_remove = [r for r in roles_to_remove if r in member.roles]
        if not member_roles_to_remove:
            continue

        try:
            await member.remove_roles(*member_roles_to_remove)
            removed_count += 1

            # Nivel de auditoría 2: registrar cada usuario
            if audit_level >= 2:
                role_names = ", ".join(r.name for r in member_roles_to_remove)
                msg_template = config.get(
                    ConfigKey.EXEC_MSG_GLOBAL_REMOVE_USER,
                    "  ↳ 🧹 Roles eliminados: {user} ({roles})",
                )
                msg = format_message(
                    msg_template,
                    user=member.display_name,
                    roles=role_names,
                )
                execution_logs.append(msg)

        except discord.Forbidden:
            logger.warning(f"No se pudo quitar roles globales a {member.name}")

    # Actualizar mensaje de moderación después de la eliminación global
    if audit_level >= 1:
        await cog._update_mod_message(
            guild=guild,
            record=record,
            config=config,
            execution_logs=execution_logs,
        )

    return removed_count
