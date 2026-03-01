"""Cog de purga para gestión de actividad de miembros."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import delete_message, has_any_role
from discord_bot.purga.config import COG_NAME, PURGA_CONFIG_SCHEMA
from discord_bot.purga.enums import ConfigKey, PurgaStatus, PurgaType
from discord_bot.purga.execution import execute_purga
from discord_bot.purga.formatters import (
    format_message,
    format_roles,
    get_button_style,
    get_mod_message_content,
)
from discord_bot.purga.models import PurgaRecord
from discord_bot.purga.service import PurgaService
from discord_bot.purga.views import ModAuthorizationView, UserConfirmationView

logger = logging.getLogger(__name__)


class PurgaCog(commands.Cog):
    """Cog para gestión de purgas de miembros."""

    def __init__(self, bot: DiscordBot) -> None:
        """Inicializar el cog.

        Args:
            bot (DiscordBot): Instancia del bot de Discord.
        """
        self.bot = bot
        # Track registered commands per guild and type: {guild_id: {"war": name, "global": name}}
        self._registered_commands: dict[int, dict[str, str]] = {}
        # Debounce pending syncs: {guild_id: asyncio.Task}
        self._pending_syncs: dict[int, asyncio.Task[None]] = {}
        # Debounce delay in seconds
        self._sync_debounce_delay = 2.0
        # Track active purgas in memory: {guild_id: (purga_id, expires_at)}
        self._active_purgas: dict[int, tuple[int, datetime | None]] = {}
        # Track authorized purgas for execution: {guild_id: (purga_id, scheduled_for)}
        self._authorized_purgas: dict[int, tuple[int, datetime]] = {}
        # Track cancel_pending purgas: {guild_id: (purga_id, expires_at)}
        self._cancel_pending_purgas: dict[int, tuple[int, datetime]] = {}
        # Track messages scheduled for deletion: {(channel_id, message_id): delete_at}
        self._pending_deletions: dict[tuple[int, int], datetime] = {}
        logger.info("PurgaCog inicializado")

    @staticmethod
    def get_config_schema() -> Any:
        """Obtener el esquema de configuración del cog.

        Returns:
            CogConfigSchema: Esquema de configuración.
        """
        return PURGA_CONFIG_SCHEMA

    # =========================================================================
    # Config helpers
    # =========================================================================

    async def _is_cog_enabled(self, guild_id: int) -> bool:
        """Verificar si el cog está habilitado en un guild.

        Args:
            guild_id (int): ID del guild.

        Returns:
            bool: True si está habilitado.
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.is_cog_enabled(guild_id=guild_id, cog_name=COG_NAME)

    async def _get_config(self, guild_id: int) -> dict[str, Any]:
        """Obtener toda la configuración del cog para un guild.

        Args:
            guild_id (int): ID del guild.

        Returns:
            dict[str, Any]: Configuración del cog.
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.get_all_config(guild_id=guild_id, cog_name=COG_NAME)

    def _get_available_purga_types(self, config: dict[str, Any]) -> dict[str, bool]:
        """Verificar qué tipos de purga tienen configuración completa.

        Args:
            config (dict[str, Any]): Diccionario de configuración.

        Returns:
            dict[str, bool]: Diccionario con los tipos disponibles.
        """
        result: dict[str, bool] = {"war": False, "global": False}

        # Canales requeridos (comunes a todos los tipos)
        has_channels = bool(
            config.get(ConfigKey.MOD_CHANNEL) and config.get(ConfigKey.USER_CHANNEL)
        )

        if not has_channels:
            return result

        # Verificar configuración de purga de guerra
        if config.get(ConfigKey.WAR_ADMIN_ROLES) and config.get(ConfigKey.WAR_AFFECTED_ROLES):
            result["war"] = True

        # Verificar configuración de purga global
        if config.get(ConfigKey.GLOBAL_ADMIN_ROLES):
            result["global"] = True

        return result

    def _get_required_reactions(self, config: dict[str, Any]) -> int:
        """Obtener el número de reacciones requeridas.

        En modo prueba, se respeta el valor configurado.
        En modo normal, el mínimo es 2.

        Args:
            config (dict[str, Any]): Configuración del cog.

        Returns:
            int: Número de reacciones requeridas.
        """
        test_mode = config.get(ConfigKey.TEST_MODE, False)
        required: int = config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2)
        if not test_mode and required < 2:
            required = 2
        return required

    def _get_purga_display_name(self, config: dict[str, Any], purga_type: PurgaType) -> str:
        """Obtener el nombre para mostrar de un tipo de purga.

        Args:
            config: Configuración del cog.
            purga_type: Tipo de purga.

        Returns:
            str: Nombre para mostrar.
        """
        if purga_type == PurgaType.GLOBAL:
            name: str = config.get(ConfigKey.GLOBAL_DISPLAY_NAME, "Purga global")
            return name
        name = config.get(ConfigKey.WAR_DISPLAY_NAME, "Purga de fin de guerra")
        return name

    # =========================================================================
    # Logging helpers
    # =========================================================================

    async def _send_log(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
        purga_id: int,
        message: str,
        audit_level_required: int = 0,
    ) -> None:
        """Enviar mensaje al canal de logs si está configurado.

        Args:
            guild: Guild donde enviar el log
            config: Configuración del cog
            purga_id: ID de la purga para prefijo
            message: Mensaje a enviar (ya formateado)
            audit_level_required: Nivel mínimo de audit para enviar
        """
        # Verificar audit level
        current_audit = config.get(ConfigKey.AUDIT_LEVEL, 0)
        if current_audit < audit_level_required:
            return

        channel_id = config.get(ConfigKey.LOG_CHANNEL)
        if not channel_id:
            return

        try:
            channel = guild.get_channel(int(channel_id))
            if channel and isinstance(channel, discord.TextChannel):
                log_message = f"[#{purga_id}] {message}"
                await channel.send(log_message)
        except (ValueError, TypeError) as e:
            logger.warning(f"[{guild.name}] Error con canal de log de purga: {e}")
        except discord.HTTPException as e:
            logger.warning(f"[{guild.name}] Error enviando log de purga: {e}")

    # =========================================================================
    # Dynamic command registration
    # =========================================================================

    async def _register_guild_commands(self, guild: discord.Guild) -> None:
        """Registrar comandos para un guild basándose en su configuración.

        Solo registra comandos si el cog está habilitado Y la configuración
        esencial está completa para cada tipo.

        Args:
            guild (discord.Guild): Guild de Discord.
        """
        # Check if cog is enabled
        if not await self._is_cog_enabled(guild.id):
            logger.debug(f"[{guild.name}] Purga cog deshabilitado, no se registran comandos")
            # Unregister if there were commands registered
            if guild.id in self._registered_commands:
                await self._unregister_guild_commands(guild)
            return

        config = await self._get_config(guild.id)

        # Check which purga types are available
        available_types = self._get_available_purga_types(config)

        if not any(available_types.values()):
            logger.debug(
                f"[{guild.name}] Ningún tipo de purga configurado, no se registran comandos"
            )
            if guild.id in self._registered_commands:
                await self._unregister_guild_commands(guild)
            return

        # Initialize guild commands dict if not exists
        if guild.id not in self._registered_commands:
            self._registered_commands[guild.id] = {}

        # Register/update purge commands
        await self._register_purga_command(
            guild=guild,
            config=config,
            purga_type=PurgaType.WAR_END,
            available=available_types["war"],
        )
        await self._register_purga_command(
            guild=guild,
            config=config,
            purga_type=PurgaType.GLOBAL,
            available=available_types["global"],
        )

    async def _register_purga_command(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
        purga_type: PurgaType,
        available: bool,
    ) -> None:
        """Registrar o actualizar un comando de purga.

        Args:
            guild (discord.Guild): Guild de Discord.
            config (dict[str, Any]): Configuración del cog.
            purga_type (PurgaType): Tipo de purga (WAR_END o GLOBAL).
            available (bool): Si la configuración está completa.
        """
        # Configuración según tipo de purga
        type_config = {
            PurgaType.WAR_END: {
                "key": "war",
                "name_config": ConfigKey.WAR_COMMAND_NAME,
                "default_name": "purga_guerra",
                "description": "Inicia una purga de fin de guerra",
            },
            PurgaType.GLOBAL: {
                "key": "global",
                "name_config": ConfigKey.GLOBAL_COMMAND_NAME,
                "default_name": "purga_global",
                "description": "Inicia una purga global",
            },
        }

        cfg = type_config[purga_type]
        command_key = cfg["key"]
        command_name = config.get(cfg["name_config"], cfg["default_name"])
        old_command_name = self._registered_commands.get(guild.id, {}).get(command_key)

        # Si no está disponible, eliminar comando existente
        if not available:
            if old_command_name:
                self.bot.tree.remove_command(old_command_name, guild=guild)
                del self._registered_commands[guild.id][command_key]
                logger.info(f"[{guild.name}] Comando '/{old_command_name}' eliminado")
            return

        # Remove old command if name changed
        if old_command_name and old_command_name != command_name:
            self.bot.tree.remove_command(old_command_name, guild=guild)
            logger.info(f"[{guild.name}] Comando '/{old_command_name}' eliminado")

        # Check if command already registered with same name
        if old_command_name == command_name:
            return

        # Create and register the purge command
        @app_commands.command(
            name=command_name,
            description=cfg["description"],
        )
        @app_commands.describe(horas="Número de horas hasta la ejecución de la purga")
        async def purge_command(
            interaction: discord.Interaction,
            horas: app_commands.Range[int, 1, 720],
            _purga_type: PurgaType = purga_type,
        ) -> None:
            await self._handle_purge(interaction=interaction, horas=horas, purga_type=_purga_type)

        # Add command to guild
        self.bot.tree.add_command(purge_command, guild=guild)
        self._registered_commands[guild.id][command_key] = command_name
        logger.info(f"[{guild.name}] Comando '/{command_name}' registrado")

    async def _unregister_guild_commands(self, guild: discord.Guild) -> None:
        """Eliminar comandos registrados de un guild.

        Args:
            guild (discord.Guild): Guild de Discord.
        """
        commands = self._registered_commands.get(guild.id, {})
        for _purga_type, command_name in list(commands.items()):
            self.bot.tree.remove_command(command_name, guild=guild)
            logger.info(f"[{guild.name}] Comando '/{command_name}' eliminado")
        if guild.id in self._registered_commands:
            del self._registered_commands[guild.id]

    async def _sync_guild_commands(self, guild: discord.Guild) -> None:
        """Sincronizar comandos de un guild con Discord.

        Args:
            guild (discord.Guild): Guild de Discord.
        """
        try:
            await self.bot.tree.sync(guild=guild)
            logger.info(f"[{guild.name}] Comandos sincronizados")
        except Exception as e:
            logger.error(f"[{guild.name}] Error sincronizando comandos: {e}")

    async def _debounced_register_and_sync(self, guild: discord.Guild) -> None:
        """Registrar y sincronizar comandos con debounce.

        Espera un breve periodo antes de ejecutar para agrupar múltiples
        cambios de configuración en una sola sincronización.

        Args:
            guild (discord.Guild): Guild de Discord.
        """
        # Cancel any pending sync for this guild
        if guild.id in self._pending_syncs:
            self._pending_syncs[guild.id].cancel()

        async def _delayed_sync() -> None:
            try:
                await asyncio.sleep(self._sync_debounce_delay)
                await self._register_guild_commands(guild)
                await self._sync_guild_commands(guild)
            except asyncio.CancelledError:
                pass  # Task was cancelled, a new one will run
            finally:
                self._pending_syncs.pop(guild.id, None)

        self._pending_syncs[guild.id] = asyncio.create_task(_delayed_sync())

    # =========================================================================
    # Command handlers
    # =========================================================================

    def _build_config_snapshot(
        self, config: dict[str, Any], purga_type: PurgaType
    ) -> dict[str, Any]:
        """Construir el snapshot de configuración según el tipo de purga.

        Args:
            config (dict[str, Any]): Configuración del cog.
            purga_type (PurgaType): Tipo de purga.

        Returns:
            dict[str, Any]: Snapshot de configuración.
        """
        # Campos comunes
        snapshot: dict[str, Any] = {
            "reaction_role": config.get(ConfigKey.USER_REACTION_ROLE),
            "required_reactions": config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2),
            "test_mode": config.get(ConfigKey.TEST_MODE, False),
        }

        if purga_type == PurgaType.GLOBAL:
            snapshot.update(
                {
                    "excluded_roles": config.get(ConfigKey.GLOBAL_EXCLUDED_ROLES, []),
                    "roles_to_remove": config.get(ConfigKey.GLOBAL_ROLES_TO_REMOVE, []),
                    "roles_to_add": config.get(ConfigKey.GLOBAL_ROLES_TO_ADD, []),
                }
            )
        else:
            # WAR_END
            snapshot.update(
                {
                    "affected_roles": config.get(ConfigKey.WAR_AFFECTED_ROLES, []),
                    "roles_to_remove": config.get(ConfigKey.WAR_ROLES_TO_REMOVE, []),
                    "roles_to_add": config.get(ConfigKey.WAR_ROLES_TO_ADD, []),
                    "global_roles_to_remove": config.get(ConfigKey.WAR_GLOBAL_ROLES_TO_REMOVE, []),
                    "promotions": config.get(ConfigKey.WAR_PROMOTIONS, []),
                    "default_promotion": config.get(ConfigKey.WAR_DEFAULT_PROMOTION),
                }
            )

        return snapshot

    async def _handle_purge(
        self,
        interaction: discord.Interaction,
        horas: int,
        purga_type: PurgaType,
    ) -> None:
        """Manejar el comando de purga (unificado para todos los tipos).

        Args:
            interaction (discord.Interaction): Interacción de Discord.
            horas (int): Número de horas hasta la ejecución.
            purga_type (PurgaType): Tipo de purga a iniciar.
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        await interaction.response.defer(ephemeral=True)

        config = await self._get_config(guild.id)

        # Verificar permisos según tipo de purga
        admin_roles = self._get_admin_roles_for_purga(config=config, purga_type=purga_type)
        if not has_any_role(member=user, role_ids=admin_roles):
            await interaction.followup.send(
                config.get(ConfigKey.MOD_NO_PERMISSION_TEXT, "Sin permisos."),
                ephemeral=True,
            )
            return

        async with self.bot.database.session() as session:
            purga_service = PurgaService(session)

            # Verificar si hay una purga activa (con bloqueo para prevenir race condition)
            active = await purga_service.get_active_purga_for_update(guild.id)
            if active:
                await interaction.followup.send(
                    config.get(
                        ConfigKey.MOD_ACTIVE_PURGE_TEXT,
                        "Ya hay una purga activa.",
                    ),
                    ephemeral=True,
                )
                return

            # Calcular fecha de ejecución (redondeada a la hora en punto siguiente)
            now = datetime.now(UTC)
            scheduled_for = now + timedelta(hours=horas)
            # Redondear hacia arriba a la hora en punto
            if scheduled_for.minute > 0 or scheduled_for.second > 0:
                scheduled_for = (scheduled_for + timedelta(hours=1)).replace(
                    minute=0, second=0, microsecond=0
                )
            else:
                scheduled_for = scheduled_for.replace(second=0, microsecond=0)

            # Calcular fecha de expiración para autorizaciones
            timeout_minutes = config.get(ConfigKey.MOD_REACTION_TIMEOUT, 1)
            expires_at = None
            if timeout_minutes > 0:
                expires_at = now + timedelta(minutes=timeout_minutes)

            # Crear snapshot de config relevante
            config_snapshot = self._build_config_snapshot(config=config, purga_type=purga_type)

            # Crear registro de purga
            record = await purga_service.create_purga(
                guild_id=guild.id,
                purga_type=purga_type,
                initiated_by=user.id,
                config_snapshot=config_snapshot,
                scheduled_for=scheduled_for,
                expires_at=expires_at,
            )

            logger.info(f"[{guild.name}] Purga {record.id} creada por {user.display_name}")

            # Enviar log de creación
            display_name = self._get_purga_display_name(config=config, purga_type=purga_type)
            log_template = config.get(
                ConfigKey.LOG_CREATED,
                "Purga **{purga_type}** creada por **{user}** - "
                "Ejecución: {scheduled_for} ({horas}h)",
            )
            log_message = log_template.format(
                user=user.display_name,
                purga_type=display_name,
                horas=str(horas),
                scheduled_for=scheduled_for.strftime("%Y-%m-%d %H:%M UTC"),
            )
            await self._send_log(
                guild=guild,
                config=config,
                purga_id=record.id,
                message=log_message,
            )

            # Obtener canal de moderación
            mod_channel_id = config.get(ConfigKey.MOD_CHANNEL)
            if not mod_channel_id:
                await interaction.followup.send(
                    "Error: Canal de moderación no configurado.",
                    ephemeral=True,
                )
                return
            mod_channel = guild.get_channel(mod_channel_id)
            if not mod_channel or not isinstance(mod_channel, discord.TextChannel):
                await interaction.followup.send(
                    "Error: Canal de moderación no encontrado.",
                    ephemeral=True,
                )
                return

            # Calcular autorizaciones requeridas
            required = self._get_required_reactions(config)

            # Verificar si ya tenemos suficientes autorizaciones (el iniciador cuenta)
            authorized_count = len(record.authorized_by)
            if authorized_count >= required:
                # Auto-autorizar
                updated_record = await self._authorize_purga(
                    guild=guild,
                    record=record,
                    config=config,
                    purga_service=purga_service,
                    session=session,
                )
                if updated_record:
                    record = updated_record

            # Crear mensaje de moderación
            content = get_mod_message_content(guild=guild, record=record, config=config)
            view = self._create_mod_view(record=record, config=config)

            mod_message = await mod_channel.send(content=content, view=view)

            # Actualizar registro con ID del mensaje
            await purga_service.update_mod_message(
                purga_id=record.id,
                channel_id=mod_channel.id,
                message_id=mod_message.id,
            )

            # Enviar mensaje a usuarios si ya está autorizada
            if record.status == PurgaStatus.AUTHORIZED:
                await self._send_user_message(
                    guild=guild, record=record, config=config, session=session
                )
            else:
                # Registrar en memoria para control de expiración
                self._active_purgas[guild.id] = (record.id, expires_at)

            await session.commit()

            await interaction.followup.send(
                f"Purga iniciada. Mensaje enviado a {mod_channel.mention}.",
                ephemeral=True,
            )

    # =========================================================================
    # Authorization handlers
    # =========================================================================

    def _get_admin_roles_for_purga(
        self, config: dict[str, Any], purga_type: PurgaType
    ) -> list[int]:
        """Obtener los roles de admin según el tipo de purga.

        Args:
            config (dict[str, Any]): Configuración del cog.
            purga_type (PurgaType): Tipo de purga.

        Returns:
            list[int]: Lista de IDs de roles admin.
        """
        if purga_type == PurgaType.GLOBAL:
            roles: list[int] = config.get(ConfigKey.GLOBAL_ADMIN_ROLES, [])
            return roles
        # WAR_END y otros tipos usan WAR_ADMIN_ROLES
        roles = config.get(ConfigKey.WAR_ADMIN_ROLES, [])
        return roles

    async def _handle_authorize(self, interaction: discord.Interaction, purga_id: int) -> None:
        """Manejar autorización de una purga.

        Args:
            interaction (discord.Interaction): Interacción del botón.
            purga_id (int): ID del registro de purga.
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        await interaction.response.defer()

        config = await self._get_config(guild.id)

        async with self.bot.database.session() as session:
            purga_service = PurgaService(session)

            record = await purga_service.get_purga(purga_id)
            if not record or record.guild_id != guild.id:
                await interaction.followup.send(
                    "Purga no encontrada.",
                    ephemeral=True,
                )
                return

            # Verificar permisos según tipo de purga
            admin_roles = self._get_admin_roles_for_purga(
                config=config, purga_type=PurgaType(record.purga_type)
            )
            if not has_any_role(member=user, role_ids=admin_roles):
                await interaction.followup.send(
                    config.get(ConfigKey.MOD_NO_PERMISSION_TEXT, "Sin permisos."),
                    ephemeral=True,
                )
                return

            if record.status not in (PurgaStatus.PENDING, PurgaStatus.AUTHORIZED):
                await interaction.followup.send(
                    "Esta purga ya no está activa.",
                    ephemeral=True,
                )
                return

            # Añadir autorización (no toggle)
            if user.id in record.authorized_by:
                await interaction.followup.send(
                    "Ya has autorizado esta purga.",
                    ephemeral=True,
                )
                return

            record = await purga_service.add_authorization(purga_id=purga_id, user_id=user.id)
            if not record:
                return

            logger.info(
                f"[{guild.name}] Autorización añadida a purga {purga_id} por {user.display_name}"
            )

            # Calcular autorizaciones requeridas
            required = self._get_required_reactions(config)
            authorized_count = len(record.authorized_by)

            # Enviar log de autorización
            log_template = config.get(
                ConfigKey.LOG_AUTHORIZED,
                "**{user}** autorizó ({auth_count}/{required})",
            )
            log_message = log_template.format(
                user=user.display_name,
                auth_count=str(authorized_count),
                required=str(required),
            )
            await self._send_log(
                guild=guild,
                config=config,
                purga_id=purga_id,
                message=log_message,
            )

            if authorized_count >= required and record.status == PurgaStatus.PENDING:
                # Autorizar purga
                updated_record = await self._authorize_purga(
                    guild=guild,
                    record=record,
                    config=config,
                    purga_service=purga_service,
                    session=session,
                )
                if updated_record:
                    record = updated_record

            # Actualizar mensaje de moderación
            await self._update_mod_message(guild=guild, record=record, config=config)

            await session.commit()

            await interaction.followup.send(
                f"Autorización añadida. ({authorized_count}/{required})",
                ephemeral=True,
            )

    async def _handle_cancel(self, interaction: discord.Interaction, purga_id: int) -> None:
        """Manejar voto de cancelación de una purga.

        La cancelación requiere el mismo número de votos que la autorización.

        Args:
            interaction (discord.Interaction): Interacción del botón.
            purga_id (int): ID del registro de purga.
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        await interaction.response.defer()

        config = await self._get_config(guild.id)

        async with self.bot.database.session() as session:
            purga_service = PurgaService(session)

            record = await purga_service.get_purga(purga_id)
            if not record or record.guild_id != guild.id:
                await interaction.followup.send(
                    "Purga no encontrada.",
                    ephemeral=True,
                )
                return

            # Verificar permisos según tipo de purga
            admin_roles = self._get_admin_roles_for_purga(
                config=config, purga_type=PurgaType(record.purga_type)
            )
            if not has_any_role(member=user, role_ids=admin_roles):
                await interaction.followup.send(
                    config.get(ConfigKey.MOD_NO_PERMISSION_TEXT, "Sin permisos."),
                    ephemeral=True,
                )
                return

            if record.status not in (
                PurgaStatus.PENDING,
                PurgaStatus.AUTHORIZED,
                PurgaStatus.CANCEL_PENDING,
            ):
                await interaction.followup.send(
                    "Esta purga no puede ser cancelada.",
                    ephemeral=True,
                )
                return

            # Verificar si ya votó por cancelar
            if user.id in record.cancelled_by:
                await interaction.followup.send(
                    "Ya has votado por cancelar esta purga.",
                    ephemeral=True,
                )
                return

            # Añadir voto de cancelación
            record = await purga_service.add_cancellation(purga_id=purga_id, user_id=user.id)
            if not record:
                return

            logger.info(
                f"[{guild.name}] Voto de cancelación añadido a purga {purga_id} "
                f"por {user.display_name}"
            )

            # Calcular votos requeridos
            required = self._get_required_reactions(config)
            cancel_count = len(record.cancelled_by)

            # Si está AUTHORIZED y es el primer voto, transicionar a CANCEL_PENDING
            # (excepto en modo prueba con required=1, que va directo a CANCELLED)
            if record.status == PurgaStatus.AUTHORIZED and cancel_count < required:
                record = await purga_service.update_status(
                    purga_id=purga_id, status=PurgaStatus.CANCEL_PENDING
                )
                if not record:
                    return

                # Calcular expiración para CANCEL_PENDING
                timeout_minutes = config.get(ConfigKey.MOD_REACTION_TIMEOUT, 1)
                if timeout_minutes > 0:
                    cancel_expires_at = datetime.now(UTC) + timedelta(minutes=timeout_minutes)
                    self._cancel_pending_purgas[guild.id] = (purga_id, cancel_expires_at)

                logger.info(f"[{guild.name}] Purga {purga_id} en estado CANCEL_PENDING")

            if cancel_count >= required:
                # Cancelar la purga
                record = await purga_service.update_status(
                    purga_id=purga_id, status=PurgaStatus.CANCELLED
                )

                if not record:
                    return

                logger.info(f"[{guild.name}] Purga {purga_id} cancelada")

                # Enviar log de cancelación
                log_template = config.get(
                    ConfigKey.LOG_CANCELLED,
                    "Cancelada por **{user}**",
                )
                log_message = log_template.format(user=user.display_name)
                await self._send_log(
                    guild=guild,
                    config=config,
                    purga_id=purga_id,
                    message=log_message,
                )

                # Quitar de tracking
                self._active_purgas.pop(guild.id, None)
                self._authorized_purgas.pop(guild.id, None)
                self._cancel_pending_purgas.pop(guild.id, None)

                # Quitar rol de reacción a todos los que confirmaron
                reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
                if reaction_role_id and record.confirmed_by:
                    role = guild.get_role(reaction_role_id)
                    if role:
                        for confirmed_user_id in record.confirmed_by:
                            member = guild.get_member(confirmed_user_id)
                            if member and role in member.roles:
                                try:
                                    await member.remove_roles(role)
                                except discord.Forbidden:
                                    logger.warning(
                                        f"No se pudo quitar rol {role.name} a {member.name}"
                                    )

                # Eliminar mensaje de usuarios si existe
                if record.user_message_id and record.user_channel_id:
                    await delete_message(
                        guild=guild,
                        channel_id=record.user_channel_id,
                        message_id=record.user_message_id,
                    )

                # Actualizar mensaje de moderación (quitar botones, mostrar cancelado)
                await self._update_mod_message(
                    guild=guild, record=record, config=config, remove_view=True
                )

                # Programar eliminación del mensaje si hay retención configurada
                self._maybe_schedule_mod_message_deletion(record=record, config=config)

                await session.commit()

                await interaction.followup.send(
                    "Purga cancelada.",
                    ephemeral=True,
                )
            else:
                # Aún no hay suficientes votos
                # Actualizar mensaje de moderación con votos actuales
                await self._update_mod_message(guild=guild, record=record, config=config)

                await session.commit()

                await interaction.followup.send(
                    f"Voto de cancelación añadido. ({cancel_count}/{required})",
                    ephemeral=True,
                )

    # =========================================================================
    # User confirmation handlers
    # =========================================================================

    async def _handle_confirm(self, interaction: discord.Interaction, purga_id: int) -> None:
        """Manejar confirmación de permanencia de un usuario.

        Args:
            interaction (discord.Interaction): Interacción del botón.
            purga_id (int): ID del registro de purga.
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        config = await self._get_config(guild.id)

        async with self.bot.database.session() as session:
            purga_service = PurgaService(session)

            record = await purga_service.get_purga(purga_id)
            if not record or record.guild_id != guild.id:
                await interaction.response.send_message(
                    "Purga no encontrada.",
                    ephemeral=True,
                )
                return

            if record.status != PurgaStatus.AUTHORIZED:
                await interaction.response.send_message(
                    "Esta purga ya no está activa.",
                    ephemeral=True,
                )
                return

            # Toggle confirmación
            was_confirmed = user.id in record.confirmed_by
            if was_confirmed:
                record = await purga_service.remove_confirmation(purga_id=purga_id, user_id=user.id)
                message = config.get(
                    ConfigKey.USER_REMOVED_REACTION_TEXT,
                    "Has retirado tu confirmación.",
                )
                # Quitar rol si está configurado
                reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
                if reaction_role_id:
                    role = guild.get_role(reaction_role_id)
                    if role:
                        try:
                            await user.remove_roles(role)
                        except discord.Forbidden:
                            logger.warning(
                                f"[{guild.name}] No se pudo quitar rol @{role.name} a {user.name}"
                            )
            else:
                record = await purga_service.add_confirmation(purga_id=purga_id, user_id=user.id)
                message = config.get(
                    ConfigKey.USER_FIRST_REACTION_TEXT,
                    "Has confirmado tu permanencia.",
                )
                # Asignar rol si está configurado
                reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
                if reaction_role_id:
                    role = guild.get_role(reaction_role_id)
                    if role:
                        try:
                            await user.add_roles(role)
                        except discord.Forbidden:
                            logger.warning(
                                f"[{guild.name}] No se pudo asignar rol @{role.name} a {user.name}"
                            )

            await session.commit()

            await interaction.response.send_message(message, ephemeral=True)

    # =========================================================================
    # Message update helpers
    # =========================================================================

    def _create_mod_view(
        self,
        record: PurgaRecord,
        config: dict[str, Any],
    ) -> ModAuthorizationView:
        """Crear vista de moderación con botones según el estado.

        Args:
            record (PurgaRecord): Registro de purga.
            config (dict[str, Any]): Configuración del cog.

        Returns:
            ModAuthorizationView: Vista con los botones apropiados.
        """
        button_color = config.get(ConfigKey.MOD_BUTTON_COLOR, "green")
        authorize_label = config.get(ConfigKey.MOD_BUTTON_TEXT, "🔑 Autorizar purga")
        cancel_label = config.get(ConfigKey.MOD_STOP_BUTTON_TEXT, "🛑 Detener purga")

        return ModAuthorizationView(
            purga_id=record.id,
            status=PurgaStatus(record.status),
            authorize_label=authorize_label,
            cancel_label=cancel_label,
            button_style=get_button_style(button_color),
        )

    def _maybe_schedule_mod_message_deletion(
        self,
        record: PurgaRecord,
        config: dict[str, Any],
    ) -> None:
        """Programar eliminación del mensaje de moderación si hay retención configurada.

        Args:
            record (PurgaRecord): Registro de purga.
            config (dict[str, Any]): Configuración del cog.
        """
        retention = config.get(ConfigKey.MOD_MESSAGE_RETENTION, 0)
        if retention > 0 and record.mod_channel_id and record.mod_message_id:
            self._schedule_message_deletion(
                channel_id=record.mod_channel_id,
                message_id=record.mod_message_id,
                retention_minutes=retention,
            )

    async def _authorize_purga(
        self,
        guild: discord.Guild,
        record: PurgaRecord,
        config: dict[str, Any],
        purga_service: PurgaService,
        session: Any,
    ) -> PurgaRecord | None:
        """Transicionar una purga a estado AUTHORIZED.

        Args:
            guild (discord.Guild): Guild de Discord.
            record (PurgaRecord): Registro de purga.
            config (dict[str, Any]): Configuración del cog.
            purga_service (PurgaService): Servicio de purga.
            session (AsyncSession): Sesión de base de datos.

        Returns:
            PurgaRecord | None: Registro actualizado o None si falló.
        """
        test_mode = config.get(ConfigKey.TEST_MODE, False)

        # Calcular tiempo de ejecución
        exec_scheduled_for: datetime | None
        if test_mode:
            exec_scheduled_for = datetime.now(UTC) + timedelta(minutes=2)
        else:
            exec_scheduled_for = record.scheduled_for

        # Actualizar estado
        updated_record = await purga_service.update_status(
            purga_id=record.id,
            status=PurgaStatus.AUTHORIZED,
            scheduled_for=exec_scheduled_for,
        )

        if not updated_record:
            return None

        logger.info(
            f"[{guild.name}] Purga {record.id} autorizada, "
            f"ejecución programada para {exec_scheduled_for}"
        )

        # Quitar de tracking de expiración
        self._active_purgas.pop(guild.id, None)

        # Añadir a tracking de ejecución
        if exec_scheduled_for:
            self._authorized_purgas[guild.id] = (updated_record.id, exec_scheduled_for)

        # Enviar mensaje a canal de usuarios
        await self._send_user_message(
            guild=guild, record=updated_record, config=config, session=session
        )

        return updated_record

    async def _update_mod_message(
        self,
        guild: discord.Guild,
        record: PurgaRecord,
        config: dict[str, Any],
        remove_view: bool = False,
        execution_logs: list[str] | None = None,
    ) -> None:
        """Actualizar el mensaje de moderación.

        Args:
            guild (discord.Guild): Guild.
            record (PurgaRecord): Registro de purga.
            config (dict[str, Any]): Configuración.
            remove_view (bool): Si True, elimina los botones.
            execution_logs (list[str] | None): Logs de ejecución para añadir.
        """
        if not record.mod_message_id or not record.mod_channel_id:
            return

        channel = guild.get_channel(record.mod_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(record.mod_message_id)
        except discord.NotFound:
            logger.warning(f"[{guild.name}] Mensaje de moderación de purga no encontrado")
            return

        content = get_mod_message_content(
            guild=guild, record=record, config=config, execution_logs=execution_logs
        )

        if remove_view or record.status in (
            PurgaStatus.CANCELLED,
            PurgaStatus.EXPIRED,
            PurgaStatus.EXECUTED,
            PurgaStatus.FAILED,
        ):
            await message.edit(content=content, view=None)
        elif record.status in (
            PurgaStatus.PENDING,
            PurgaStatus.AUTHORIZED,
            PurgaStatus.CANCEL_PENDING,
        ):
            view = self._create_mod_view(record=record, config=config)
            await message.edit(content=content, view=view)
        else:
            await message.edit(content=content)

    async def _send_user_message(
        self,
        guild: discord.Guild,
        record: PurgaRecord,
        config: dict[str, Any],
        session: Any,
    ) -> None:
        """Enviar mensaje al canal de usuarios.

        Args:
            guild (discord.Guild): Guild.
            record (PurgaRecord): Registro de purga.
            config (dict[str, Any]): Configuración.
            session (AsyncSession): Sesión de base de datos.
        """
        user_channel_id = config.get(ConfigKey.USER_CHANNEL)
        if not user_channel_id:
            return

        channel = guild.get_channel(user_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        # Obtener plantilla y roles según tipo de purga
        purga_type = PurgaType(record.purga_type)
        if purga_type == PurgaType.GLOBAL:
            template = config.get(ConfigKey.GLOBAL_MESSAGE_TEMPLATE)
            excluded_roles = config.get(ConfigKey.GLOBAL_EXCLUDED_ROLES, [])
            roles_text = format_roles(guild=guild, role_ids=excluded_roles)
        else:
            template = config.get(ConfigKey.WAR_MESSAGE_TEMPLATE)
            affected_roles = config.get(ConfigKey.WAR_AFFECTED_ROLES, [])
            roles_text = format_roles(guild=guild, role_ids=affected_roles)

        reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
        reaction_role = guild.get_role(reaction_role_id) if reaction_role_id else None
        reaction_role_text = reaction_role.mention if reaction_role else ""

        # Calcular días restantes
        days_remaining = "?"
        scheduled_date = "No programada"
        scheduled_time = ""
        if record.scheduled_for:
            now = datetime.now(UTC)
            delta = record.scheduled_for - now
            days_remaining = str(max(0, delta.days))
            scheduled_date = record.scheduled_for.strftime("%Y-%m-%d")
            scheduled_time = record.scheduled_for.strftime("%H:%M UTC")

        content = format_message(
            template=template,
            roles=roles_text,
            days=days_remaining,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            reaction_role=reaction_role_text,
            # Mantener compatibilidad con placeholders antiguos
            dia=f"{scheduled_date} {scheduled_time}",
            reaction_rol=reaction_role_text,
        )

        # Crear vista con botón
        button_color = config.get(ConfigKey.USER_BUTTON_COLOR, "green")
        confirm_label = config.get(ConfigKey.USER_BUTTON_TEXT, "🛡️ Confirmar permanencia")

        view = UserConfirmationView(
            purga_id=record.id,
            confirm_label=confirm_label,
            button_style=get_button_style(button_color),
        )

        user_message = await channel.send(content=content, view=view)

        # Actualizar registro
        purga_service = PurgaService(session)
        await purga_service.update_user_message(
            purga_id=record.id,
            channel_id=channel.id,
            message_id=user_message.id,
        )

    # =========================================================================
    # Event listeners
    # =========================================================================

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Registrar comandos cuando el bot está listo."""
        logger.info("PurgaCog: Registrando comandos en todos los guilds...")
        for guild in self.bot.guilds:
            try:
                await self._register_guild_commands(guild)
            except Exception as e:
                logger.error(f"[{guild.name}] Error registrando comandos: {e}")

        # Sync commands for all guilds
        for guild in self.bot.guilds:
            if guild.id in self._registered_commands:
                await self._sync_guild_commands(guild)

        logger.info("PurgaCog: Registro de comandos completado")

        # Restaurar purgas activas desde la base de datos
        await self._restore_active_purgas()

        # Verificar expiración inmediatamente
        await self._check_expired_purgas()

        # Iniciar tarea de verificación de expiración
        if not self.expiration_check_loop.is_running():
            self.expiration_check_loop.start()

    async def _restore_active_purgas(self) -> None:
        """Restaurar purgas pendientes y autorizadas desde la base de datos al iniciar.

        Esto permite que las purgas activas sigan siendo monitoreadas
        después de un reinicio del bot.
        """
        try:
            async with self.bot.database.session() as session:
                purga_service = PurgaService(session)

                # Restaurar purgas pendientes de autorización
                pending_purgas = await purga_service.get_pending_purgas()
                for record in pending_purgas:
                    self._active_purgas[record.guild_id] = (record.id, record.expires_at)
                    logger.info(
                        f"Purga pendiente {record.id} restaurada para guild {record.guild_id}"
                    )

                # Restaurar purgas autorizadas pendientes de ejecución
                authorized_purgas = await purga_service.get_authorized_purgas()
                for record in authorized_purgas:
                    if record.scheduled_for:
                        self._authorized_purgas[record.guild_id] = (record.id, record.scheduled_for)
                        logger.info(
                            f"Purga autorizada {record.id} restaurada para guild {record.guild_id}"
                        )

                # Restaurar purgas con cancelación pendiente
                cancel_pending_purgas = await purga_service.get_cancel_pending_purgas()
                for record in cancel_pending_purgas:
                    # Usar timeout fresco desde la config al restaurar
                    config = await self._get_config(record.guild_id)
                    timeout_minutes = config.get(ConfigKey.MOD_REACTION_TIMEOUT, 1)
                    if timeout_minutes > 0:
                        cancel_expires_at = datetime.now(UTC) + timedelta(minutes=timeout_minutes)
                        self._cancel_pending_purgas[record.guild_id] = (
                            record.id,
                            cancel_expires_at,
                        )
                        logger.info(
                            f"Purga CANCEL_PENDING {record.id} restaurada para "
                            f"guild {record.guild_id}"
                        )

                total = len(pending_purgas) + len(authorized_purgas) + len(cancel_pending_purgas)
                if total:
                    logger.info(f"PurgaCog: {total} purgas restauradas")
        except Exception as e:
            logger.error(f"Error restaurando purgas activas: {e}")

    async def cog_unload(self) -> None:
        """Limpiar recursos al descargar el cog."""
        self.expiration_check_loop.cancel()

    def _schedule_message_deletion(
        self, channel_id: int, message_id: int, retention_minutes: int
    ) -> None:
        """Programar eliminación de un mensaje.

        Args:
            channel_id (int): ID del canal.
            message_id (int): ID del mensaje.
            retention_minutes (int): Minutos hasta eliminar. 0 = no eliminar.
        """
        if retention_minutes > 0:
            delete_at = datetime.now(UTC) + timedelta(minutes=retention_minutes)
            self._pending_deletions[(channel_id, message_id)] = delete_at
            logger.debug(f"Mensaje de mod (ID: {message_id}) programado para eliminar: {delete_at}")

    async def _check_pending_deletions(self) -> None:
        """Verificar y eliminar mensajes que han pasado su tiempo de retención."""
        now = datetime.now(UTC)
        to_delete: list[tuple[int, int]] = []

        for (channel_id, message_id), delete_at in self._pending_deletions.items():
            if delete_at <= now:
                to_delete.append((channel_id, message_id))

        for channel_id, message_id in to_delete:
            self._pending_deletions.pop((channel_id, message_id), None)
            try:
                channel = self.bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    guild = channel.guild
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.delete()
                        logger.info(
                            f"[{guild.name}] Mensaje de moderación eliminado "
                            f"por retención en #{channel.name}"
                        )
                    except discord.NotFound:
                        pass  # Ya fue eliminado
            except Exception as e:
                logger.error(f"Error eliminando mensaje de moderación (ID: {message_id}): {e}")

    async def _check_expired_purgas(self) -> None:
        """Verificar y expirar purgas pendientes que han pasado su tiempo límite."""
        now = datetime.now(UTC)
        expired_guilds: list[int] = []

        # Identificar purgas expiradas
        for guild_id, (_purga_id, expires_at) in self._active_purgas.items():
            if expires_at and expires_at <= now:
                expired_guilds.append(guild_id)

        # Procesar purgas expiradas
        for guild_id in expired_guilds:
            purga_id, _ = self._active_purgas.pop(guild_id)
            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else str(guild_id)
            logger.info(f"[{guild_name}] Purga {purga_id} ha expirado")

            try:
                async with self.bot.database.session() as session:
                    purga_service = PurgaService(session)

                    # Actualizar estado a expirado
                    record = await purga_service.update_status(
                        purga_id=purga_id, status=PurgaStatus.EXPIRED
                    )

                    if record and guild:
                        config = await self._get_config(guild_id)
                        await self._update_mod_message(
                            guild=guild,
                            record=record,
                            config=config,
                            remove_view=True,
                        )
                        # Programar eliminación si hay retención configurada
                        self._maybe_schedule_mod_message_deletion(record=record, config=config)

                    await session.commit()
            except Exception as e:
                logger.error(f"Error expirando purga {purga_id}: {e}")

    async def _check_cancel_pending_expired(self) -> None:
        """Verificar y revertir purgas CANCEL_PENDING que han expirado a AUTHORIZED."""
        now = datetime.now(UTC)
        expired_guilds: list[int] = []

        # Identificar purgas CANCEL_PENDING expiradas
        for guild_id, (_purga_id, expires_at) in self._cancel_pending_purgas.items():
            if expires_at <= now:
                expired_guilds.append(guild_id)

        # Procesar purgas expiradas
        for guild_id in expired_guilds:
            purga_id, _ = self._cancel_pending_purgas.pop(guild_id)
            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else str(guild_id)
            logger.info(
                f"[{guild_name}] Cancelación de purga {purga_id} expirada, revirtiendo a AUTHORIZED"
            )

            try:
                async with self.bot.database.session() as session:
                    purga_service = PurgaService(session)

                    # Limpiar votos de cancelación
                    await purga_service.clear_cancellations(purga_id)

                    # Revertir estado a AUTHORIZED
                    record = await purga_service.update_status(
                        purga_id=purga_id, status=PurgaStatus.AUTHORIZED
                    )

                    if record and guild:
                        config = await self._get_config(guild_id)
                        await self._update_mod_message(
                            guild=guild,
                            record=record,
                            config=config,
                        )

                    await session.commit()
            except Exception as e:
                logger.error(f"Error revirtiendo cancelación de purga {purga_id}: {e}")

    async def _check_ready_purgas(self) -> None:
        """Verificar y ejecutar purgas autorizadas que han alcanzado su tiempo de ejecución."""
        now = datetime.now(UTC)
        ready_guilds: list[int] = []

        # Identificar purgas listas para ejecutar
        for guild_id, (_purga_id, scheduled_for) in self._authorized_purgas.items():
            if scheduled_for <= now:
                ready_guilds.append(guild_id)

        # Procesar purgas listas
        for guild_id in ready_guilds:
            purga_id, _ = self._authorized_purgas.pop(guild_id)
            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else str(guild_id)
            logger.info(f"[{guild_name}] Purga {purga_id} lista para ejecutar")

            try:
                await self._execute_purga(guild_id=guild_id, purga_id=purga_id)
            except Exception as e:
                logger.error(f"Error ejecutando purga {purga_id}: {e}")

    async def _execute_purga(self, guild_id: int, purga_id: int) -> None:
        """Ejecutar una purga.

        Args:
            guild_id (int): ID del guild.
            purga_id (int): ID de la purga.
        """
        await execute_purga(cog=self, guild_id=guild_id, purga_id=purga_id)

    @tasks.loop(minutes=1)
    async def expiration_check_loop(self) -> None:
        """Loop que verifica purgas expiradas, ejecuciones y mensajes pendientes."""
        await self._check_expired_purgas()
        await self._check_cancel_pending_expired()
        await self._check_ready_purgas()
        await self._check_pending_deletions()

    @expiration_check_loop.before_loop
    async def before_expiration_check(self) -> None:
        """Esperar a que el bot esté listo antes de iniciar el loop."""
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Registrar comandos cuando el bot se une a un guild.

        Args:
            guild (discord.Guild): Guild al que se unió el bot.
        """
        logger.info(f"[{guild.name}] PurgaCog: Bot unido, registrando comandos...")
        await self._register_guild_commands(guild)
        if guild.id in self._registered_commands:
            await self._sync_guild_commands(guild)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Manejar interacciones de botones con IDs dinámicos.

        Los botones tienen custom_ids como 'purga:authorize:123' que incluyen
        el purga_id. Este listener maneja estos botones para que funcionen
        incluso después de reiniciar el bot.

        Args:
            interaction (discord.Interaction): Interacción recibida.
        """
        if interaction.type != discord.InteractionType.component:
            return

        custom_id: str = str(interaction.data.get("custom_id", "") if interaction.data else "")

        # Manejar botón de autorizar: purga:authorize:{purga_id}
        if custom_id.startswith("purga:authorize:"):
            try:
                purga_id = int(custom_id.split(":")[2])
                await self._handle_authorize(interaction=interaction, purga_id=purga_id)
            except (ValueError, IndexError):
                logger.error(f"Custom ID inválido para authorize: {custom_id}")
            return

        # Manejar botón de cancelar: purga:cancel:{purga_id}
        if custom_id.startswith("purga:cancel:"):
            try:
                purga_id = int(custom_id.split(":")[2])
                await self._handle_cancel(interaction=interaction, purga_id=purga_id)
            except (ValueError, IndexError):
                logger.error(f"Custom ID inválido para cancel: {custom_id}")
            return

        # Manejar botón de confirmar: purga:confirm:{purga_id}
        if custom_id.startswith("purga:confirm:"):
            try:
                purga_id = int(custom_id.split(":")[2])
                await self._handle_confirm(interaction=interaction, purga_id=purga_id)
            except (ValueError, IndexError):
                logger.error(f"Custom ID inválido para confirm: {custom_id}")
            return

    # =========================================================================
    # Config change callbacks
    # =========================================================================

    async def on_cog_toggled(self, guild: discord.Guild, enabled: bool) -> None:
        """Callback cuando el cog es habilitado o deshabilitado.

        Args:
            guild (discord.Guild): Guild donde cambió el estado.
            enabled (bool): True si fue habilitado.
        """
        if enabled:
            logger.info(f"[{guild.name}] PurgaCog habilitado, registrando comandos...")
            await self._register_guild_commands(guild)
            if guild.id in self._registered_commands:
                await self._sync_guild_commands(guild)
        else:
            logger.info(f"[{guild.name}] PurgaCog deshabilitado, eliminando comandos...")
            await self._unregister_guild_commands(guild)
            await self._sync_guild_commands(guild)

    async def on_config_changed(self, guild: discord.Guild, key: str) -> None:
        """Callback cuando cambia la configuración del cog.

        Args:
            guild (discord.Guild): Guild donde cambió la configuración.
            key (str): Clave de configuración que cambió.
        """
        # Keys that affect command registration
        essential_keys = {
            # Common keys
            ConfigKey.MOD_CHANNEL,
            ConfigKey.USER_CHANNEL,
            # War purga keys
            ConfigKey.WAR_COMMAND_NAME,
            ConfigKey.WAR_ADMIN_ROLES,
            ConfigKey.WAR_AFFECTED_ROLES,
            # Global purga keys
            ConfigKey.GLOBAL_COMMAND_NAME,
            ConfigKey.GLOBAL_ADMIN_ROLES,
        }

        if key in essential_keys:
            logger.debug(
                f"Configuración esencial '{key}' cambiada en {guild.name}, "
                "programando re-evaluación de comandos..."
            )
            # Use debounced sync to batch multiple config changes
            await self._debounced_register_and_sync(guild)


async def setup(bot: DiscordBot) -> None:
    """Configurar el cog.

    Args:
        bot (DiscordBot): Instancia del bot de Discord.
    """
    get_config_schema_service().register_schema(PURGA_CONFIG_SCHEMA)
    await bot.add_cog(PurgaCog(bot))
    logger.info("PurgaCog cargado")


async def teardown(bot: DiscordBot) -> None:
    """Limpiar el cog.

    Args:
        bot (DiscordBot): Instancia del bot de Discord.
    """
    cog = bot.get_cog("PurgaCog")
    if cog and isinstance(cog, PurgaCog):
        # Unregister all commands
        for guild_id in list(cog._registered_commands.keys()):
            guild = bot.get_guild(guild_id)
            if guild:
                await cog._unregister_guild_commands(guild)
    get_config_schema_service().unregister_schema(COG_NAME)
    logger.info("PurgaCog descargado")
