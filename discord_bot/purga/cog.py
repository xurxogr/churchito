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
    format_authorized_by,
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

    async def _get_config_value(self, guild_id: int, key: str) -> Any:
        """Obtener un valor de configuración específico.

        Args:
            guild_id (int): ID del guild.
            key (str): Clave de configuración.

        Returns:
            Any: Valor de configuración.
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.get_value(guild_id=guild_id, cog_name=COG_NAME, key=key)

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

    # =========================================================================
    # Message formatting helpers (delegated to formatters module)
    # =========================================================================

    def _format_message(self, template: str | None = None, **kwargs: str | None) -> str:
        """Reemplazar placeholders en un mensaje."""
        return format_message(template, **kwargs)

    def _get_button_style(self, color: str) -> discord.ButtonStyle:
        """Obtener el estilo de botón a partir del nombre de color."""
        return get_button_style(color)

    def _format_authorized_by(self, guild: discord.Guild, user_ids: list[int]) -> str:
        """Formatear la lista de usuarios que autorizaron."""
        return format_authorized_by(guild=guild, user_ids=user_ids)

    def _format_roles(self, guild: discord.Guild, role_ids: list[int]) -> str:
        """Formatear la lista de roles."""
        return format_roles(guild=guild, role_ids=role_ids)

    def _get_mod_message_content(
        self,
        guild: discord.Guild,
        record: PurgaRecord,
        config: dict[str, Any],
        execution_logs: list[str] | None = None,
    ) -> str:
        """Generar el contenido del mensaje de moderación."""
        return get_mod_message_content(
            guild=guild, record=record, config=config, execution_logs=execution_logs
        )

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
            logger.debug(f"Purga cog deshabilitado en {guild.name}, no se registran comandos")
            # Unregister if there were commands registered
            if guild.id in self._registered_commands:
                await self._unregister_guild_commands(guild)
            return

        config = await self._get_config(guild.id)

        # Check which purga types are available
        available_types = self._get_available_purga_types(config)

        if not any(available_types.values()):
            logger.debug(
                f"Ningún tipo de purga configurado en {guild.name}. No se registran comandos."
            )
            if guild.id in self._registered_commands:
                await self._unregister_guild_commands(guild)
            return

        # Initialize guild commands dict if not exists
        if guild.id not in self._registered_commands:
            self._registered_commands[guild.id] = {}

        # Register/update war purge command
        await self._register_war_command(
            guild=guild, config=config, available=available_types["war"]
        )

        # Register/update global purge command
        await self._register_global_command(
            guild=guild, config=config, available=available_types["global"]
        )

    async def _register_war_command(
        self, guild: discord.Guild, config: dict[str, Any], available: bool
    ) -> None:
        """Registrar o actualizar el comando de purga de guerra.

        Args:
            guild: Guild de Discord.
            config: Configuración del cog.
            available: Si la configuración está completa.
        """
        war_command_name = config.get(ConfigKey.WAR_COMMAND_NAME, "purga_guerra")
        old_command_name = self._registered_commands.get(guild.id, {}).get("war")

        # Si no está disponible, eliminar comando existente
        if not available:
            if old_command_name:
                self.bot.tree.remove_command(old_command_name, guild=guild)
                del self._registered_commands[guild.id]["war"]
                logger.info(f"Comando '{old_command_name}' eliminado de {guild.name}")
            return

        # Remove old command if name changed
        if old_command_name and old_command_name != war_command_name:
            self.bot.tree.remove_command(old_command_name, guild=guild)
            logger.info(f"Comando '{old_command_name}' eliminado de {guild.name}")

        # Check if command already registered with same name
        if old_command_name == war_command_name:
            return

        # Create and register the war purge command
        @app_commands.command(
            name=war_command_name,
            description="Inicia una purga de fin de guerra",
        )
        @app_commands.describe(dias="Número de días hasta la ejecución de la purga")
        async def war_purge_command(
            interaction: discord.Interaction,
            dias: app_commands.Range[int, 1, 30],
        ) -> None:
            await self._handle_war_purge(interaction=interaction, dias=dias)

        # Add command to guild
        self.bot.tree.add_command(war_purge_command, guild=guild)
        self._registered_commands[guild.id]["war"] = war_command_name
        logger.info(f"Comando '{war_command_name}' registrado en {guild.name}")

    async def _register_global_command(
        self, guild: discord.Guild, config: dict[str, Any], available: bool
    ) -> None:
        """Registrar o actualizar el comando de purga global.

        Args:
            guild: Guild de Discord.
            config: Configuración del cog.
            available: Si la configuración está completa.
        """
        global_command_name = config.get(ConfigKey.GLOBAL_COMMAND_NAME, "purga_global")
        old_command_name = self._registered_commands.get(guild.id, {}).get("global")

        # Si no está disponible, eliminar comando existente
        if not available:
            if old_command_name:
                self.bot.tree.remove_command(old_command_name, guild=guild)
                del self._registered_commands[guild.id]["global"]
                logger.info(f"Comando '{old_command_name}' eliminado de {guild.name}")
            return

        # Remove old command if name changed
        if old_command_name and old_command_name != global_command_name:
            self.bot.tree.remove_command(old_command_name, guild=guild)
            logger.info(f"Comando '{old_command_name}' eliminado de {guild.name}")

        # Check if command already registered with same name
        if old_command_name == global_command_name:
            return

        # Create and register the global purge command
        @app_commands.command(
            name=global_command_name,
            description="Inicia una purga global",
        )
        @app_commands.describe(dias="Número de días hasta la ejecución de la purga")
        async def global_purge_command(
            interaction: discord.Interaction,
            dias: app_commands.Range[int, 1, 30],
        ) -> None:
            await self._handle_global_purge(interaction=interaction, dias=dias)

        # Add command to guild
        self.bot.tree.add_command(global_purge_command, guild=guild)
        self._registered_commands[guild.id]["global"] = global_command_name
        logger.info(f"Comando '{global_command_name}' registrado en {guild.name}")

    async def _unregister_guild_commands(self, guild: discord.Guild) -> None:
        """Eliminar comandos registrados de un guild.

        Args:
            guild (discord.Guild): Guild de Discord.
        """
        commands = self._registered_commands.get(guild.id, {})
        for _purga_type, command_name in list(commands.items()):
            self.bot.tree.remove_command(command_name, guild=guild)
            logger.info(f"Comando '{command_name}' eliminado de {guild.name}")
        if guild.id in self._registered_commands:
            del self._registered_commands[guild.id]

    async def _sync_guild_commands(self, guild: discord.Guild) -> None:
        """Sincronizar comandos de un guild con Discord.

        Args:
            guild (discord.Guild): Guild de Discord.
        """
        try:
            await self.bot.tree.sync(guild=guild)
            logger.info(f"Comandos sincronizados en {guild.name}")
        except Exception as e:
            logger.error(f"Error sincronizando comandos en {guild.name}: {e}")

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

    async def _handle_war_purge(self, interaction: discord.Interaction, dias: int) -> None:
        """Manejar el comando de purga de fin de guerra.

        Args:
            interaction (discord.Interaction): Interacción de Discord.
            dias (int): Número de días hasta la ejecución.
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        await interaction.response.defer(ephemeral=True)

        config = await self._get_config(guild.id)

        # Verificar permisos
        admin_roles = config.get(ConfigKey.WAR_ADMIN_ROLES, [])
        if not has_any_role(member=user, role_ids=admin_roles):
            await interaction.followup.send(
                config.get(ConfigKey.MOD_NO_PERMISSION_TEXT, "Sin permisos."),
                ephemeral=True,
            )
            return

        async with self.bot.database.session() as session:
            purga_service = PurgaService(session)

            # Verificar si hay una purga activa
            active = await purga_service.get_active_purga(guild.id)
            if active:
                await interaction.followup.send(
                    config.get(
                        ConfigKey.MOD_ACTIVE_PURGE_TEXT,
                        "Ya hay una purga activa.",
                    ),
                    ephemeral=True,
                )
                return

            # Calcular fecha de ejecución
            purge_hour = config.get(ConfigKey.PURGE_HOUR, 18)
            now = datetime.now(UTC)
            scheduled_for = (now + timedelta(days=dias)).replace(
                hour=purge_hour, minute=0, second=0, microsecond=0
            )

            # Calcular fecha de expiración para autorizaciones
            timeout_minutes = config.get(ConfigKey.MOD_REACTION_TIMEOUT, 1)
            expires_at = None
            if timeout_minutes > 0:
                expires_at = now + timedelta(minutes=timeout_minutes)

            # Crear snapshot de config relevante
            config_snapshot = {
                "affected_roles": config.get(ConfigKey.WAR_AFFECTED_ROLES, []),
                "roles_to_remove": config.get(ConfigKey.WAR_ROLES_TO_REMOVE, []),
                "roles_to_add": config.get(ConfigKey.WAR_ROLES_TO_ADD, []),
                "global_roles_to_remove": config.get(ConfigKey.WAR_GLOBAL_ROLES_TO_REMOVE, []),
                "promotions": config.get(ConfigKey.WAR_PROMOTIONS, []),
                "default_promotion": config.get(ConfigKey.WAR_DEFAULT_PROMOTION),
                "reaction_role": config.get(ConfigKey.USER_REACTION_ROLE),
                "required_reactions": config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2),
                "test_mode": config.get(ConfigKey.TEST_MODE, False),
            }

            # Crear registro de purga
            record = await purga_service.create_purga(
                guild_id=guild.id,
                purga_type=PurgaType.WAR_END,
                initiated_by=user.id,
                config_snapshot=config_snapshot,
                scheduled_for=scheduled_for,
                expires_at=expires_at,
            )

            logger.info(f"[{guild.name}] Purga {record.id} creada por {user.display_name}")

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

            # Calcular autorizaciones requeridas (mínimo 2 si no es modo prueba)
            test_mode = config.get(ConfigKey.TEST_MODE, False)
            required = config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2)
            if not test_mode and required < 2:
                required = 2

            # Verificar si ya tenemos suficientes autorizaciones (el iniciador cuenta)
            authorized_count = len(record.authorized_by)
            if authorized_count >= required:
                # Auto-autorizar
                if test_mode:
                    exec_scheduled_for = datetime.now(UTC) + timedelta(minutes=2)
                else:
                    exec_scheduled_for = scheduled_for

                updated_record = await purga_service.update_status(
                    purga_id=record.id,
                    status=PurgaStatus.AUTHORIZED,
                    scheduled_for=exec_scheduled_for,
                )
                if updated_record:
                    record = updated_record
                    if exec_scheduled_for:
                        self._authorized_purgas[guild.id] = (record.id, exec_scheduled_for)
                    logger.info(
                        f"[{guild.name}] Purga {record.id} auto-autorizada, "
                        f"ejecución programada para {exec_scheduled_for}"
                    )

            # Crear mensaje de moderación
            content = self._get_mod_message_content(guild=guild, record=record, config=config)

            # Crear vista con botones según estado
            button_color = config.get(ConfigKey.MOD_BUTTON_COLOR, "green")
            authorize_label = config.get(ConfigKey.MOD_BUTTON_TEXT, "🔑 Autorizar purga")
            cancel_label = config.get(ConfigKey.MOD_STOP_BUTTON_TEXT, "🛑 Detener purga")

            view = ModAuthorizationView(
                purga_id=record.id,
                status=PurgaStatus(record.status),
                authorize_label=authorize_label,
                cancel_label=cancel_label,
                button_style=self._get_button_style(button_color),
            )

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

    async def _handle_global_purge(self, interaction: discord.Interaction, dias: int) -> None:
        """Manejar el comando de purga global.

        Args:
            interaction (discord.Interaction): Interacción de Discord.
            dias (int): Número de días hasta la ejecución.
        """
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        guild = interaction.guild
        user = interaction.user

        await interaction.response.defer(ephemeral=True)

        config = await self._get_config(guild.id)

        # Verificar permisos
        admin_roles = config.get(ConfigKey.GLOBAL_ADMIN_ROLES, [])
        if not has_any_role(member=user, role_ids=admin_roles):
            await interaction.followup.send(
                config.get(ConfigKey.MOD_NO_PERMISSION_TEXT, "Sin permisos."),
                ephemeral=True,
            )
            return

        async with self.bot.database.session() as session:
            purga_service = PurgaService(session)

            # Verificar si hay una purga activa
            active = await purga_service.get_active_purga(guild.id)
            if active:
                await interaction.followup.send(
                    config.get(
                        ConfigKey.MOD_ACTIVE_PURGE_TEXT,
                        "Ya hay una purga activa.",
                    ),
                    ephemeral=True,
                )
                return

            # Calcular fecha de ejecución
            purge_hour = config.get(ConfigKey.PURGE_HOUR, 18)
            now = datetime.now(UTC)
            scheduled_for = (now + timedelta(days=dias)).replace(
                hour=purge_hour, minute=0, second=0, microsecond=0
            )

            # Calcular fecha de expiración para autorizaciones
            timeout_minutes = config.get(ConfigKey.MOD_REACTION_TIMEOUT, 1)
            expires_at = None
            if timeout_minutes > 0:
                expires_at = now + timedelta(minutes=timeout_minutes)

            # Crear snapshot de config relevante para purga global
            config_snapshot = {
                "excluded_roles": config.get(ConfigKey.GLOBAL_EXCLUDED_ROLES, []),
                "roles_to_remove": config.get(ConfigKey.GLOBAL_ROLES_TO_REMOVE, []),
                "roles_to_add": config.get(ConfigKey.GLOBAL_ROLES_TO_ADD, []),
                "reaction_role": config.get(ConfigKey.USER_REACTION_ROLE),
                "required_reactions": config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2),
                "test_mode": config.get(ConfigKey.TEST_MODE, False),
            }

            # Crear registro de purga
            record = await purga_service.create_purga(
                guild_id=guild.id,
                purga_type=PurgaType.GLOBAL,
                initiated_by=user.id,
                config_snapshot=config_snapshot,
                scheduled_for=scheduled_for,
                expires_at=expires_at,
            )

            logger.info(f"[{guild.name}] Purga global {record.id} creada por {user.display_name}")

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

            # Calcular autorizaciones requeridas (mínimo 2 si no es modo prueba)
            test_mode = config.get(ConfigKey.TEST_MODE, False)
            required = config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2)
            if not test_mode and required < 2:
                required = 2

            # Verificar si ya tenemos suficientes autorizaciones (el iniciador cuenta)
            authorized_count = len(record.authorized_by)
            if authorized_count >= required:
                # Auto-autorizar
                if test_mode:
                    exec_scheduled_for = datetime.now(UTC) + timedelta(minutes=2)
                else:
                    exec_scheduled_for = scheduled_for

                updated_record = await purga_service.update_status(
                    purga_id=record.id,
                    status=PurgaStatus.AUTHORIZED,
                    scheduled_for=exec_scheduled_for,
                )
                if updated_record:
                    record = updated_record
                    if exec_scheduled_for:
                        self._authorized_purgas[guild.id] = (record.id, exec_scheduled_for)
                    logger.info(
                        f"[{guild.name}] Purga global {record.id} auto-autorizada, "
                        f"ejecución programada para {exec_scheduled_for}"
                    )

            # Crear mensaje de moderación
            content = self._get_mod_message_content(guild=guild, record=record, config=config)

            # Crear vista con botones según estado
            button_color = config.get(ConfigKey.MOD_BUTTON_COLOR, "green")
            authorize_label = config.get(ConfigKey.MOD_BUTTON_TEXT, "🔑 Autorizar purga")
            cancel_label = config.get(ConfigKey.MOD_STOP_BUTTON_TEXT, "🛑 Detener purga")

            view = ModAuthorizationView(
                purga_id=record.id,
                status=PurgaStatus(record.status),
                authorize_label=authorize_label,
                cancel_label=cancel_label,
                button_style=self._get_button_style(button_color),
            )

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
                f"Purga global iniciada. Mensaje enviado a {mod_channel.mention}.",
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
            config: Configuración del cog.
            purga_type: Tipo de purga.

        Returns:
            Lista de IDs de roles admin.
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
            if not record:
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

            # Calcular autorizaciones requeridas (mínimo 2 si no es modo prueba)
            test_mode = config.get(ConfigKey.TEST_MODE, False)
            required = config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2)
            if not test_mode and required < 2:
                required = 2
            authorized_count = len(record.authorized_by)

            if authorized_count >= required and record.status == PurgaStatus.PENDING:
                # Calcular tiempo de ejecución
                exec_scheduled_for: datetime | None
                if test_mode:
                    # En modo prueba, ejecutar en 2 minutos
                    exec_scheduled_for = datetime.now(UTC) + timedelta(minutes=2)
                else:
                    # Mantener el scheduled_for original
                    exec_scheduled_for = record.scheduled_for

                # Autorizar purga
                updated_record = await purga_service.update_status(
                    purga_id=purga_id,
                    status=PurgaStatus.AUTHORIZED,
                    scheduled_for=exec_scheduled_for,
                )
                if updated_record:
                    record = updated_record
                    logger.info(
                        f"[{guild.name}] Purga {purga_id} autorizada, "
                        f"ejecución programada para {exec_scheduled_for}"
                    )
                    # Quitar de tracking de expiración
                    self._active_purgas.pop(guild.id, None)
                    # Añadir a tracking de ejecución
                    if exec_scheduled_for:
                        self._authorized_purgas[guild.id] = (record.id, exec_scheduled_for)
                    # Enviar mensaje a canal de usuarios
                    await self._send_user_message(
                        guild=guild, record=record, config=config, session=session
                    )

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
            if not record:
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

            # Calcular autorizaciones requeridas (mínimo 2 si no es modo prueba)
            test_mode = config.get(ConfigKey.TEST_MODE, False)
            required = config.get(ConfigKey.MOD_REQUIRED_REACTIONS, 2)
            if not test_mode and required < 2:
                required = 2
            cancel_count = len(record.cancelled_by)

            if cancel_count >= required:
                # Cancelar la purga
                record = await purga_service.update_status(
                    purga_id=purga_id, status=PurgaStatus.CANCELLED
                )

                if not record:
                    return

                logger.info(f"[{guild.name}] Purga {purga_id} cancelada")

                # Quitar de tracking
                self._active_purgas.pop(guild.id, None)
                self._authorized_purgas.pop(guild.id, None)

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
                retention = config.get(ConfigKey.MOD_MESSAGE_RETENTION, 0)
                if retention > 0 and record.mod_channel_id and record.mod_message_id:
                    self._schedule_message_deletion(
                        channel_id=record.mod_channel_id,
                        message_id=record.mod_message_id,
                        retention_minutes=retention,
                    )

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
            if not record:
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
                            logger.warning(f"No se pudo quitar rol {role.name} a {user.name}")
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
                            logger.warning(f"No se pudo asignar rol {role.name} a {user.name}")

            await session.commit()

            await interaction.response.send_message(message, ephemeral=True)

    # =========================================================================
    # Message update helpers
    # =========================================================================

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
            logger.warning(f"Mensaje de mod no encontrado: {record.mod_message_id}")
            return

        content = self._get_mod_message_content(
            guild=guild, record=record, config=config, execution_logs=execution_logs
        )

        if remove_view or record.status in (
            PurgaStatus.CANCELLED,
            PurgaStatus.EXPIRED,
            PurgaStatus.EXECUTED,
            PurgaStatus.FAILED,
        ):
            await message.edit(content=content, view=None)
        elif record.status in (PurgaStatus.PENDING, PurgaStatus.AUTHORIZED):
            # Crear vista con el botón apropiado según el estado
            button_color = config.get(ConfigKey.MOD_BUTTON_COLOR, "green")
            authorize_label = config.get(ConfigKey.MOD_BUTTON_TEXT, "🔑 Autorizar purga")
            cancel_label = config.get(ConfigKey.MOD_STOP_BUTTON_TEXT, "🛑 Detener purga")

            view = ModAuthorizationView(
                purga_id=record.id,
                status=PurgaStatus(record.status),
                authorize_label=authorize_label,
                cancel_label=cancel_label,
                button_style=self._get_button_style(button_color),
            )
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
            session: Sesión de base de datos.
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
            roles_text = self._format_roles(guild=guild, role_ids=excluded_roles)
        else:
            template = config.get(ConfigKey.WAR_MESSAGE_TEMPLATE)
            affected_roles = config.get(ConfigKey.WAR_AFFECTED_ROLES, [])
            roles_text = self._format_roles(guild=guild, role_ids=affected_roles)

        reaction_role_id = config.get(ConfigKey.USER_REACTION_ROLE)
        reaction_role = guild.get_role(reaction_role_id) if reaction_role_id else None
        reaction_role_text = reaction_role.mention if reaction_role else ""

        # Calcular días restantes
        days_remaining = "?"
        scheduled_date = "No programada"
        scheduled_time = ""
        if record.scheduled_for:
            from datetime import UTC

            now = datetime.now(UTC)
            delta = record.scheduled_for - now
            days_remaining = str(max(0, delta.days))
            scheduled_date = record.scheduled_for.strftime("%Y-%m-%d")
            scheduled_time = record.scheduled_for.strftime("%H:%M UTC")

        content = self._format_message(
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
            button_style=self._get_button_style(button_color),
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
                logger.error(f"Error registrando comandos en {guild.name}: {e}")

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

                total = len(pending_purgas) + len(authorized_purgas)
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
            logger.debug(f"Mensaje {message_id} programado para eliminar a las {delete_at}")

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
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.delete()
                        logger.info(f"Mensaje {message_id} eliminado por retención")
                    except discord.NotFound:
                        pass  # Ya fue eliminado
            except Exception as e:
                logger.error(f"Error eliminando mensaje {message_id}: {e}")

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
                        retention = config.get(ConfigKey.MOD_MESSAGE_RETENTION, 0)
                        if retention > 0 and record.mod_channel_id and record.mod_message_id:
                            self._schedule_message_deletion(
                                channel_id=record.mod_channel_id,
                                message_id=record.mod_message_id,
                                retention_minutes=retention,
                            )

                    await session.commit()
            except Exception as e:
                logger.error(f"Error expirando purga {purga_id}: {e}")

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
        logger.info(f"PurgaCog: Bot unido a {guild.name}, registrando comandos...")
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
            logger.info(f"PurgaCog habilitado en {guild.name}, registrando comandos...")
            await self._register_guild_commands(guild)
            if guild.id in self._registered_commands:
                await self._sync_guild_commands(guild)
        else:
            logger.info(f"PurgaCog deshabilitado en {guild.name}, eliminando comandos...")
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
