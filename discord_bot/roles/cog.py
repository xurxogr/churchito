"""Reaction roles cog for self-assignable roles."""

import asyncio
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.roles.config import COG_NAME, ROLES_CONFIG_SCHEMA
from discord_bot.roles.enums import ConfigKey
from discord_bot.roles.formatters import (
    build_panel_embed,
    build_panel_placeholder_data,
    build_role_change_placeholder_data,
    format_emoji_display,
    format_mappings_display,
    format_message,
)
from discord_bot.roles.models import PanelType, ReactionPanel
from discord_bot.roles.service import ReactionRolesService

logger = logging.getLogger(__name__)


class RolesCog(commands.Cog):
    """Cog for reaction role management."""

    def __init__(self, bot: DiscordBot) -> None:
        """Initialize the roles cog.

        Args:
            bot: Bot instance
        """
        self.bot = bot
        # Track registered commands per guild: {guild_id: {"prefix": name, ...}}
        self._registered_commands: dict[int, dict[str, str]] = {}
        # User locks to prevent race conditions
        self._user_locks: dict[int, asyncio.Lock] = {}

    def get_locked_options(self) -> dict[str, dict[str, Any]]:
        """Get options locked by deployment configuration.

        Returns:
            dict[str, dict[str, Any]]: Map of key -> {locked, reason}
        """
        return {}

    async def _get_user_lock(self, user_id: int) -> asyncio.Lock:
        """Get or create a lock for a user to prevent race conditions.

        Args:
            user_id: Discord user ID

        Returns:
            asyncio.Lock: Lock for this user
        """
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    # ===== DYNAMIC COMMAND REGISTRATION =====

    async def _register_guild_commands(self, guild: discord.Guild) -> None:
        """Register roles commands for a guild.

        Args:
            guild: Discord guild
        """
        if not await self._is_cog_enabled(guild.id):
            logger.debug(f"[{guild.name}] Roles cog disabled, not registering commands")
            if guild.id in self._registered_commands:
                await self._unregister_guild_commands(guild)
            return

        config = await self._get_config(guild.id)
        prefix = config.get(ConfigKey.COMMAND_PREFIX, "roles")

        if guild.id not in self._registered_commands:
            self._registered_commands[guild.id] = {}

        old_prefix = self._registered_commands.get(guild.id, {}).get("prefix")
        if old_prefix == prefix:
            return  # Already registered with same prefix

        # Unregister old commands if prefix changed
        if old_prefix and old_prefix != prefix:
            await self._unregister_guild_commands(guild)

        # Create command group
        group = app_commands.Group(
            name=prefix,
            description="Manage reaction role panels",
            guild_ids=[guild.id],
        )

        # Add subcommands
        self._add_create_command(group)
        self._add_add_role_command(group)
        self._add_remove_role_command(group)
        self._add_post_command(group)
        self._add_refresh_command(group)
        self._add_delete_command(group)
        self._add_list_command(group)
        self._add_info_command(group)

        self.bot.tree.add_command(group, guild=guild)
        self._registered_commands[guild.id] = {"prefix": prefix}
        logger.info(f"[{guild.name}] Roles commands registered with prefix: /{prefix}")

    def _add_create_command(self, group: app_commands.Group) -> None:
        """Add create subcommand to group."""

        @group.command(name="create", description="Create a new reaction role panel")
        @app_commands.describe(
            name="Name for the panel (unique within guild)",
            channel="Channel where the panel will be posted",
            panel_type="Type of panel behavior",
        )
        @app_commands.choices(
            panel_type=[
                app_commands.Choice(name="Toggle (add/remove on react)", value="toggle"),
                app_commands.Choice(name="Exclusive (only one role)", value="exclusive"),
                app_commands.Choice(name="Verify (one-time selection)", value="verify"),
            ]
        )
        async def create_cmd(
            interaction: discord.Interaction,
            name: str,
            channel: discord.TextChannel,
            panel_type: str = "toggle",
        ) -> None:
            await self._handle_create(interaction, name, channel, panel_type)

    def _add_add_role_command(self, group: app_commands.Group) -> None:
        """Add add_role subcommand to group."""

        @group.command(name="add_role", description="Add an emoji-role mapping to a panel")
        @app_commands.describe(
            panel="Panel name",
            emoji="Emoji to use for the reaction",
            role="Role to assign when reacted",
            display_name="Optional display name for the role option",
        )
        @app_commands.autocomplete(panel=self.panel_autocomplete)
        async def add_role_cmd(
            interaction: discord.Interaction,
            panel: str,
            emoji: str,
            role: discord.Role,
            display_name: str | None = None,
        ) -> None:
            await self._handle_add_role(interaction, panel, emoji, role, display_name)

    def _add_remove_role_command(self, group: app_commands.Group) -> None:
        """Add remove_role subcommand to group."""

        @group.command(name="remove_role", description="Remove an emoji-role mapping from a panel")
        @app_commands.describe(
            panel="Panel name",
            emoji="Emoji to remove",
        )
        @app_commands.autocomplete(panel=self.panel_autocomplete)
        async def remove_role_cmd(
            interaction: discord.Interaction,
            panel: str,
            emoji: str,
        ) -> None:
            await self._handle_remove_role(interaction, panel, emoji)

    def _add_post_command(self, group: app_commands.Group) -> None:
        """Add post subcommand to group."""

        @group.command(name="post", description="Post a panel to its configured channel")
        @app_commands.describe(panel="Panel name to post")
        @app_commands.autocomplete(panel=self.panel_autocomplete)
        async def post_cmd(
            interaction: discord.Interaction,
            panel: str,
        ) -> None:
            await self._handle_post(interaction, panel)

    def _add_refresh_command(self, group: app_commands.Group) -> None:
        """Add refresh subcommand to group."""

        @group.command(name="refresh", description="Update a posted panel's embed and reactions")
        @app_commands.describe(panel="Panel name to refresh")
        @app_commands.autocomplete(panel=self.panel_autocomplete)
        async def refresh_cmd(
            interaction: discord.Interaction,
            panel: str,
        ) -> None:
            await self._handle_refresh(interaction, panel)

    def _add_delete_command(self, group: app_commands.Group) -> None:
        """Add delete subcommand to group."""

        @group.command(name="delete", description="Delete a reaction role panel")
        @app_commands.describe(panel="Panel name to delete")
        @app_commands.autocomplete(panel=self.panel_autocomplete)
        async def delete_cmd(
            interaction: discord.Interaction,
            panel: str,
        ) -> None:
            await self._handle_delete(interaction, panel)

    def _add_list_command(self, group: app_commands.Group) -> None:
        """Add list subcommand to group."""

        @group.command(name="list", description="List all reaction role panels")
        async def list_cmd(interaction: discord.Interaction) -> None:
            await self._handle_list(interaction)

    def _add_info_command(self, group: app_commands.Group) -> None:
        """Add info subcommand to group."""

        @group.command(name="info", description="Show details of a reaction role panel")
        @app_commands.describe(panel="Panel name")
        @app_commands.autocomplete(panel=self.panel_autocomplete)
        async def info_cmd(
            interaction: discord.Interaction,
            panel: str,
        ) -> None:
            await self._handle_info(interaction, panel)

    async def _unregister_guild_commands(self, guild: discord.Guild) -> None:
        """Remove registered commands from a guild.

        Args:
            guild: Discord guild
        """
        commands_data = self._registered_commands.get(guild.id, {})
        prefix = commands_data.get("prefix")
        if prefix:
            self.bot.tree.remove_command(prefix, guild=guild)
            logger.info(f"[{guild.name}] Roles command group '/{prefix}' removed")
        if guild.id in self._registered_commands:
            del self._registered_commands[guild.id]

    async def _sync_guild_commands(self, guild: discord.Guild) -> None:
        """Sync commands of a guild with Discord.

        Args:
            guild: Discord guild
        """
        try:
            await self.bot.tree.sync(guild=guild)
            logger.info(f"[{guild.name}] Roles commands synced")
        except Exception as e:
            logger.error(f"[{guild.name}] Error syncing roles commands: {e}")

    # ===== EVENT LISTENERS =====

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Register commands when the bot is ready."""
        logger.info("RolesCog: Registering commands in all guilds...")
        for guild in self.bot.guilds:
            try:
                await self._register_guild_commands(guild)
            except Exception as e:
                logger.error(f"[{guild.name}] Error registering roles commands: {e}")

        # Sync commands for all guilds
        for guild in self.bot.guilds:
            if guild.id in self._registered_commands:
                await self._sync_guild_commands(guild)

        logger.info("RolesCog: Command registration completed")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Register commands when the bot joins a guild.

        Args:
            guild: Guild the bot joined
        """
        logger.info(f"[{guild.name}] RolesCog: Bot joined, registering commands...")
        await self._register_guild_commands(guild)
        if guild.id in self._registered_commands:
            await self._sync_guild_commands(guild)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle reaction add events.

        Args:
            payload: Raw reaction event payload
        """
        # Skip bot reactions
        if self.bot.user and payload.user_id == self.bot.user.id:
            return

        # Skip DMs
        if not payload.guild_id:
            return

        await self._handle_reaction(payload, is_add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle reaction remove events.

        Args:
            payload: Raw reaction event payload
        """
        # Skip bot reactions
        if self.bot.user and payload.user_id == self.bot.user.id:
            return

        # Skip DMs
        if not payload.guild_id:
            return

        await self._handle_reaction(payload, is_add=False)

    async def _handle_reaction(self, payload: discord.RawReactionActionEvent, is_add: bool) -> None:
        """Process a reaction event.

        Args:
            payload: Raw reaction event payload
            is_add: True if reaction added, False if removed
        """
        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        # Check if cog is enabled
        if not await self._is_cog_enabled(guild.id):
            return

        # Acquire user lock to prevent race conditions
        lock = await self._get_user_lock(payload.user_id)
        async with lock:
            await self._process_reaction(payload, guild, is_add)

    async def _process_reaction(
        self,
        payload: discord.RawReactionActionEvent,
        guild: discord.Guild,
        is_add: bool,
    ) -> None:
        """Process a reaction after acquiring lock.

        Args:
            payload: Raw reaction event payload
            guild: Discord guild
            is_add: True if reaction added, False if removed
        """
        # Lookup panel by message
        async with self.bot.database.session() as session:
            service = ReactionRolesService(session)
            panel = await service.get_by_message_id(
                guild_id=guild.id,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
            )

            if not panel:
                return

            # Get member
            member = guild.get_member(payload.user_id)
            if not member:
                try:
                    member = await guild.fetch_member(payload.user_id)
                except discord.NotFound:
                    return

            # Check required roles
            member_role_ids = [r.id for r in member.roles]
            if not panel.has_required_role(member_role_ids):
                # Remove the reaction if added
                if is_add:
                    await self._remove_user_reaction(
                        guild,
                        payload.channel_id,
                        payload.message_id,
                        payload.emoji,
                        payload.user_id,
                    )
                    # Send DM if configured
                    if panel.dm_on_missing_role:
                        await self._send_missing_role_dm(panel, guild, member)
                return

            # Parse emoji
            emoji_str = str(payload.emoji.name)
            emoji_id = payload.emoji.id if payload.emoji.is_custom_emoji() else None

            # Find mapping
            mapping = panel.find_mapping_by_emoji(emoji_str, emoji_id)
            if not mapping:
                # Invalid reaction - remove it
                if is_add:
                    await self._remove_user_reaction(
                        guild,
                        payload.channel_id,
                        payload.message_id,
                        payload.emoji,
                        payload.user_id,
                    )
                return

            role_id_raw = mapping.get("role_id")
            if not role_id_raw:
                logger.warning(f"[{guild.name}] No role_id in mapping for panel {panel.name}")
                return

            # Ensure role_id is an integer (may come as string from JSON)
            role_id = int(role_id_raw)
            role = guild.get_role(role_id)
            if not role:
                logger.warning(f"[{guild.name}] Role {role_id} not found for panel {panel.name}")
                return

            config = await self._get_config(guild.id)

            # Handle based on panel type
            if panel.panel_type == PanelType.TOGGLE:
                await self._handle_toggle(panel, guild, member, role, is_add, config)
            elif panel.panel_type == PanelType.EXCLUSIVE:
                await self._handle_exclusive(
                    panel,
                    guild,
                    member,
                    role,
                    is_add,
                    config,
                    payload.channel_id,
                    payload.message_id,
                )
            elif panel.panel_type == PanelType.VERIFY:
                await self._handle_verify(
                    panel,
                    guild,
                    member,
                    role,
                    is_add,
                    config,
                    payload.channel_id,
                    payload.message_id,
                    payload.emoji,
                    payload.user_id,
                )

    async def _handle_toggle(
        self,
        panel: ReactionPanel,
        guild: discord.Guild,
        member: discord.Member,
        role: discord.Role,
        is_add: bool,
        config: dict[str, Any],
    ) -> None:
        """Handle toggle panel type - add on react, remove on unreact.

        Args:
            panel: Reaction panel
            guild: Discord guild
            member: Member who reacted
            role: Role to add/remove
            is_add: True if reaction added
            config: Cog config
        """
        try:
            if is_add:
                if role not in member.roles:
                    await member.add_roles(role, reason=f"Reaction role panel: {panel.name}")
                    await self._on_role_added(panel, guild, member, role, config)
            else:
                if role in member.roles:
                    await member.remove_roles(role, reason=f"Reaction role panel: {panel.name}")
                    await self._on_role_removed(panel, guild, member, role, config)
        except discord.Forbidden:
            logger.warning(
                f"[{guild.name}] Cannot modify role {role.name} - insufficient permissions"
            )
        except Exception as e:
            logger.error(f"[{guild.name}] Error handling toggle: {e}")

    async def _handle_exclusive(
        self,
        panel: ReactionPanel,
        guild: discord.Guild,
        member: discord.Member,
        role: discord.Role,
        is_add: bool,
        config: dict[str, Any],
        channel_id: int,
        message_id: int,
    ) -> None:
        """Handle exclusive panel type - only one role allowed.

        Args:
            panel: Reaction panel
            guild: Discord guild
            member: Member who reacted
            role: Role to add
            is_add: True if reaction added
            config: Cog config
            channel_id: Channel ID
            message_id: Message ID
        """
        panel_roles = panel.get_all_role_ids()
        member_role_ids = {r.id for r in member.roles}
        has_panel_role = bool(set(panel_roles) & member_role_ids)

        if not is_add:
            # On unreact: only remove if user has another role from this panel
            other_roles = set(panel_roles) & member_role_ids - {role.id}

            if not other_roles:
                # Can't remove last role in exclusive mode
                return

            try:
                await member.remove_roles(role, reason=f"Reaction role panel: {panel.name}")
                await self._on_role_removed(panel, guild, member, role, config)
            except discord.Forbidden:
                logger.warning(f"[{guild.name}] Cannot remove role {role.name}")
            return

        # Check if user must have an existing role to switch (exclusive_require_existing)
        if panel.exclusive_require_existing and not has_panel_role:
            # User doesn't have any panel role - remove reaction and don't assign
            for mapping in panel.role_mappings:
                if mapping.get("role_id") and int(mapping["role_id"]) == role.id:
                    emoji = self._mapping_to_partial_emoji(mapping)
                    if emoji:
                        await self._remove_user_reaction(
                            guild, channel_id, message_id, emoji, member.id
                        )
                    break
            return

        # On react: remove other panel roles first
        try:
            roles_to_remove = []
            for r in member.roles:
                if r.id in panel_roles and r.id != role.id:
                    roles_to_remove.append(r)

            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove, reason=f"Reaction role panel: {panel.name} (exclusive mode)"
                )
                # Remove other reactions
                for r in roles_to_remove:
                    # Find emoji for this role
                    for mapping in panel.role_mappings:
                        mapping_role_id = mapping.get("role_id")
                        if mapping_role_id and int(mapping_role_id) == r.id:
                            emoji = self._mapping_to_partial_emoji(mapping)
                            if emoji:
                                await self._remove_user_reaction(
                                    guild, channel_id, message_id, emoji, member.id
                                )
                            break

            # Add the new role
            if role not in member.roles:
                await member.add_roles(role, reason=f"Reaction role panel: {panel.name}")
                await self._on_role_added(panel, guild, member, role, config)

        except discord.Forbidden:
            logger.warning(f"[{guild.name}] Cannot modify roles for exclusive panel")
        except Exception as e:
            logger.error(f"[{guild.name}] Error handling exclusive: {e}")

    async def _handle_verify(
        self,
        panel: ReactionPanel,
        guild: discord.Guild,
        member: discord.Member,
        role: discord.Role,
        is_add: bool,
        config: dict[str, Any],
        channel_id: int,
        message_id: int,
        emoji: discord.PartialEmoji,
        user_id: int,
    ) -> None:
        """Handle verify panel type - one-time selection, reaction removed after.

        Args:
            panel: Reaction panel
            guild: Discord guild
            member: Member who reacted
            role: Role to add
            is_add: True if reaction added
            config: Cog config
            channel_id: Channel ID
            message_id: Message ID
            emoji: Emoji used
            user_id: User ID
        """
        if not is_add:
            # Ignore reaction remove for verify panels (we remove it ourselves)
            return

        try:
            # Add role
            if role not in member.roles:
                await member.add_roles(role, reason=f"Reaction role panel: {panel.name} (verify)")
                await self._on_role_added(panel, guild, member, role, config)

            # Remove the reaction (one-time use)
            await self._remove_user_reaction(guild, channel_id, message_id, emoji, user_id)

        except discord.Forbidden:
            logger.warning(f"[{guild.name}] Cannot add role {role.name} for verify panel")
        except Exception as e:
            logger.error(f"[{guild.name}] Error handling verify: {e}")

    def _mapping_to_partial_emoji(self, mapping: dict[str, Any]) -> discord.PartialEmoji | None:
        """Convert a mapping to a PartialEmoji.

        Args:
            mapping: Role mapping dict

        Returns:
            PartialEmoji or None
        """
        emoji_str = mapping.get("emoji")
        emoji_id = mapping.get("emoji_id")

        if not emoji_str:
            return None

        if emoji_id:
            return discord.PartialEmoji(name=emoji_str, id=emoji_id)
        return discord.PartialEmoji(name=emoji_str)

    async def _remove_user_reaction(
        self,
        guild: discord.Guild,
        channel_id: int,
        message_id: int,
        emoji: discord.PartialEmoji,
        user_id: int,
    ) -> None:
        """Remove a user's reaction from a message.

        Args:
            guild: Discord guild
            channel_id: Channel ID
            message_id: Message ID
            emoji: Emoji to remove
            user_id: User whose reaction to remove
        """
        try:
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                return

            message = await channel.fetch_message(message_id)
            user = guild.get_member(user_id)
            if user:
                await message.remove_reaction(emoji, user)
        except discord.Forbidden:
            logger.debug(f"[{guild.name}] Cannot remove reaction - no permission")
        except discord.NotFound:
            pass
        except Exception as e:
            logger.error(f"[{guild.name}] Error removing reaction: {e}")

    async def _on_role_added(
        self,
        panel: ReactionPanel,
        guild: discord.Guild,
        member: discord.Member,
        role: discord.Role,
        config: dict[str, Any],
    ) -> None:
        """Handle role added event - send notifications.

        Args:
            panel: Reaction panel
            guild: Discord guild
            member: Member who gained role
            role: Role added
            config: Cog config
        """
        # Send user DM if configured
        if panel.dm_on_role_change:
            dm_template = config.get(ConfigKey.DM_ROLE_ADDED_MSG)
            if dm_template:
                data = build_role_change_placeholder_data(
                    panel=panel, guild=guild, user=member, role=role
                )
                msg = format_message(dm_template, **data)
                try:
                    await member.send(msg)
                except discord.Forbidden:
                    pass

        # Send audit notification if configured
        if config.get(ConfigKey.AUDIT_USER_ROLE_ADD):
            audit_channel_id = config.get(ConfigKey.AUDIT_CHANNEL)
            if audit_channel_id:
                template = config.get(ConfigKey.AUDIT_USER_ROLE_ADD_MSG)
                if template:
                    data = build_role_change_placeholder_data(
                        panel=panel, guild=guild, user=member, role=role
                    )
                    msg = format_message(template, **data)
                    await self._send_audit_message(guild, audit_channel_id, msg)

    async def _on_role_removed(
        self,
        panel: ReactionPanel,
        guild: discord.Guild,
        member: discord.Member,
        role: discord.Role,
        config: dict[str, Any],
    ) -> None:
        """Handle role removed event - send notifications.

        Args:
            panel: Reaction panel
            guild: Discord guild
            member: Member who lost role
            role: Role removed
            config: Cog config
        """
        # Send user DM if configured
        if panel.dm_on_role_change:
            dm_template = config.get(ConfigKey.DM_ROLE_REMOVED_MSG)
            if dm_template:
                data = build_role_change_placeholder_data(
                    panel=panel, guild=guild, user=member, role=role
                )
                msg = format_message(dm_template, **data)
                try:
                    await member.send(msg)
                except discord.Forbidden:
                    pass

        # Send audit notification if configured
        if config.get(ConfigKey.AUDIT_USER_ROLE_REMOVE):
            audit_channel_id = config.get(ConfigKey.AUDIT_CHANNEL)
            if audit_channel_id:
                template = config.get(ConfigKey.AUDIT_USER_ROLE_REMOVE_MSG)
                if template:
                    data = build_role_change_placeholder_data(
                        panel=panel, guild=guild, user=member, role=role
                    )
                    msg = format_message(template, **data)
                    await self._send_audit_message(guild, audit_channel_id, msg)

    async def _send_missing_role_dm(
        self,
        panel: ReactionPanel,
        guild: discord.Guild,
        member: discord.Member,
    ) -> None:
        """Send DM when user lacks required role.

        Args:
            panel: Reaction panel
            guild: Discord guild
            member: Member to DM
        """
        config = await self._get_config(guild.id)
        dm_template = config.get(ConfigKey.DM_MISSING_ROLE_MSG)
        if not dm_template:
            return

        data = build_panel_placeholder_data(panel=panel, guild=guild, user=member)
        msg = format_message(dm_template, **data)
        try:
            await member.send(msg)
        except discord.Forbidden:
            pass

    async def _send_audit_message(
        self,
        guild: discord.Guild,
        channel_id: int,
        message: str,
    ) -> None:
        """Send a message to the audit channel.

        Args:
            guild: Discord guild
            channel_id: Audit channel ID
            message: Message to send
        """
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            await channel.send(message)
        except discord.Forbidden:
            logger.warning(f"[{guild.name}] Cannot send to audit channel")
        except Exception as e:
            logger.error(f"[{guild.name}] Error sending audit message: {e}")

    # ===== CONFIG CHANGE CALLBACKS =====

    async def on_config_changed(self, guild: discord.Guild, keys: list[str]) -> None:
        """Handle configuration changes from the web dashboard.

        Args:
            guild: Guild where configuration changed
            keys: List of configuration keys that changed
        """
        keys_set = set(keys)

        # Re-register commands if prefix changed
        if ConfigKey.COMMAND_PREFIX in keys_set:
            logger.info(f"[{guild.name}] Command prefix changed, re-registering commands...")
            await self._register_guild_commands(guild)
            await self._sync_guild_commands(guild)

    async def on_cog_toggled(self, guild: discord.Guild, enabled: bool) -> None:
        """Handle when the cog is enabled or disabled.

        Args:
            guild: Guild where state changed
            enabled: True if enabled, False if disabled
        """
        if enabled:
            logger.info(f"[{guild.name}] Roles cog enabled, registering commands...")
            await self._register_guild_commands(guild)
            if guild.id in self._registered_commands:
                await self._sync_guild_commands(guild)
        else:
            logger.info(f"[{guild.name}] Roles cog disabled, removing commands...")
            await self._unregister_guild_commands(guild)
            await self._sync_guild_commands(guild)

    async def _is_cog_enabled(self, guild_id: int) -> bool:
        """Check if the cog is enabled for a guild.

        Args:
            guild_id: Guild ID

        Returns:
            bool: True if enabled
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.is_cog_enabled(guild_id=guild_id, cog_name=COG_NAME)

    async def _get_config(self, guild_id: int) -> dict[str, Any]:
        """Get all config for this cog.

        Args:
            guild_id: Guild ID

        Returns:
            dict[str, Any]: Configuration values
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.get_all_config(guild_id=guild_id, cog_name=COG_NAME)

    def _has_permission(
        self,
        member: discord.Member,
        allowed_role_ids: list[int],
    ) -> bool:
        """Check if member has any of the allowed roles.

        Args:
            member: Discord member
            allowed_role_ids: List of allowed role IDs

        Returns:
            bool: True if member has permission
        """
        if not allowed_role_ids:
            return False
        member_role_ids = {role.id for role in member.roles}
        return bool(member_role_ids & set(allowed_role_ids))

    # ===== AUTOCOMPLETE =====

    async def panel_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for panel name.

        Args:
            interaction: Discord interaction
            current: Current input value

        Returns:
            list[app_commands.Choice[str]]: Matching panel choices
        """
        if not interaction.guild:
            return []

        async with self.bot.database.session() as session:
            service = ReactionRolesService(session)
            names = await service.get_panel_names(interaction.guild.id)

        current_lower = current.lower()
        choices = [
            app_commands.Choice(name=name, value=name)
            for name in names
            if current_lower in name.lower()
        ]
        return choices[:25]

    # ===== COMMAND HANDLERS =====

    async def _handle_create(
        self,
        interaction: discord.Interaction,
        name: str,
        channel: discord.TextChannel,
        panel_type: str,
    ) -> None:
        """Handle create command.

        Args:
            interaction: Discord interaction
            name: Panel name
            channel: Target channel
            panel_type: Panel type
        """
        if not interaction.guild:
            return

        config = await self._get_config(interaction.guild.id)

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        # Check permission
        manage_roles = config.get(ConfigKey.MANAGE_ROLES) or []
        if not self._has_permission(member, manage_roles):
            await interaction.response.send_message(
                config.get(ConfigKey.NO_PERMISSION_TEXT) or "No permission.",
                ephemeral=True,
            )
            return

        # Validate name length
        if len(name) > 100:
            await interaction.response.send_message(
                "Panel name must be 100 characters or less.",
                ephemeral=True,
            )
            return

        async with self.bot.database.session() as session:
            service = ReactionRolesService(session)

            # Check for duplicate name
            existing = await service.get_by_name(guild_id=interaction.guild.id, name=name)
            if existing:
                await interaction.response.send_message(
                    f"A panel named **{name}** already exists.",
                    ephemeral=True,
                )
                return

            # Create panel
            panel = await service.create_panel(
                guild_id=interaction.guild.id,
                channel_id=channel.id,
                name=name,
                panel_type=PanelType(panel_type),
                created_by=member.id,
                guild_name=interaction.guild.name,
            )
            await session.commit()

        prefix = config.get(ConfigKey.COMMAND_PREFIX, "roles")
        await interaction.response.send_message(
            f"Panel **{name}** created! Use `/{prefix} add_role` to add emoji-role "
            f"mappings, then `/{prefix} post` to post it to {channel.mention}.",
            ephemeral=True,
        )

        # Send audit notification
        if config.get(ConfigKey.AUDIT_PANEL_CREATED):
            audit_channel_id = config.get(ConfigKey.AUDIT_CHANNEL)
            if audit_channel_id:
                template = config.get(ConfigKey.AUDIT_PANEL_CREATED_MSG)
                if template:
                    data = build_panel_placeholder_data(
                        panel=panel, guild=interaction.guild, user=member
                    )
                    msg = format_message(template, **data)
                    await self._send_audit_message(interaction.guild, audit_channel_id, msg)

    async def _handle_add_role(
        self,
        interaction: discord.Interaction,
        panel_name: str,
        emoji: str,
        role: discord.Role,
        display_name: str | None,
    ) -> None:
        """Handle add_role command.

        Args:
            interaction: Discord interaction
            panel_name: Panel name
            emoji: Emoji string
            role: Role to add
            display_name: Optional display name
        """
        if not interaction.guild:
            return

        config = await self._get_config(interaction.guild.id)

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        # Check permission
        manage_roles = config.get(ConfigKey.MANAGE_ROLES) or []
        if not self._has_permission(member, manage_roles):
            await interaction.response.send_message(
                config.get(ConfigKey.NO_PERMISSION_TEXT) or "No permission.",
                ephemeral=True,
            )
            return

        # Parse emoji
        emoji_str, emoji_id = self._parse_emoji(emoji)

        async with self.bot.database.session() as session:
            service = ReactionRolesService(session)

            panel = await service.get_by_name(guild_id=interaction.guild.id, name=panel_name)
            if not panel:
                await interaction.response.send_message(
                    config.get(ConfigKey.NOT_FOUND_TEXT) or "Panel not found.",
                    ephemeral=True,
                )
                return

            # Check if emoji already exists in mappings
            existing = panel.find_mapping_by_emoji(emoji_str, emoji_id)
            if existing:
                await interaction.response.send_message(
                    f"Emoji {emoji} is already mapped to a role in this panel.",
                    ephemeral=True,
                )
                return

            await service.add_mapping(
                panel_id=panel.id,
                emoji=emoji_str,
                emoji_id=emoji_id,
                role_id=role.id,
                display_name=display_name,
                guild_name=interaction.guild.name,
            )
            await session.commit()

        emoji_display = format_emoji_display(emoji=emoji_str, emoji_id=emoji_id)
        await interaction.response.send_message(
            f"Added mapping: {emoji_display} -> {role.mention}",
            ephemeral=True,
        )

    async def _handle_remove_role(
        self,
        interaction: discord.Interaction,
        panel_name: str,
        emoji: str,
    ) -> None:
        """Handle remove_role command.

        Args:
            interaction: Discord interaction
            panel_name: Panel name
            emoji: Emoji to remove
        """
        if not interaction.guild:
            return

        config = await self._get_config(interaction.guild.id)

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        # Check permission
        manage_roles = config.get(ConfigKey.MANAGE_ROLES) or []
        if not self._has_permission(member, manage_roles):
            await interaction.response.send_message(
                config.get(ConfigKey.NO_PERMISSION_TEXT) or "No permission.",
                ephemeral=True,
            )
            return

        # Parse emoji
        emoji_str, emoji_id = self._parse_emoji(emoji)

        async with self.bot.database.session() as session:
            service = ReactionRolesService(session)

            panel = await service.get_by_name(guild_id=interaction.guild.id, name=panel_name)
            if not panel:
                await interaction.response.send_message(
                    config.get(ConfigKey.NOT_FOUND_TEXT) or "Panel not found.",
                    ephemeral=True,
                )
                return

            # Check if emoji exists
            existing = panel.find_mapping_by_emoji(emoji_str, emoji_id)
            if not existing:
                await interaction.response.send_message(
                    f"Emoji {emoji} is not mapped in this panel.",
                    ephemeral=True,
                )
                return

            await service.remove_mapping(
                panel_id=panel.id,
                emoji=emoji_str,
                emoji_id=emoji_id,
                guild_name=interaction.guild.name,
            )
            await session.commit()

        await interaction.response.send_message(
            f"Removed mapping for {emoji}",
            ephemeral=True,
        )

    async def _handle_post(
        self,
        interaction: discord.Interaction,
        panel_name: str,
    ) -> None:
        """Handle post command - post panel to channel.

        Args:
            interaction: Discord interaction
            panel_name: Panel name
        """
        if not interaction.guild:
            return

        config = await self._get_config(interaction.guild.id)

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        # Check permission
        manage_roles = config.get(ConfigKey.MANAGE_ROLES) or []
        if not self._has_permission(member, manage_roles):
            await interaction.response.send_message(
                config.get(ConfigKey.NO_PERMISSION_TEXT) or "No permission.",
                ephemeral=True,
            )
            return

        async with self.bot.database.session() as session:
            service = ReactionRolesService(session)

            panel = await service.get_by_name(guild_id=interaction.guild.id, name=panel_name)
            if not panel:
                await interaction.response.send_message(
                    config.get(ConfigKey.NOT_FOUND_TEXT) or "Panel not found.",
                    ephemeral=True,
                )
                return

            # Check if already posted
            if panel.message_id:
                await interaction.response.send_message(
                    f"Panel **{panel_name}** is already posted. Use `refresh` to update it.",
                    ephemeral=True,
                )
                return

            # Check if there are mappings
            if not panel.role_mappings:
                await interaction.response.send_message(
                    "Add at least one emoji-role mapping before posting.",
                    ephemeral=True,
                )
                return

            # Get channel
            channel = interaction.guild.get_channel(panel.channel_id)
            if not isinstance(channel, discord.TextChannel):
                await interaction.response.send_message(
                    "Target channel not found or not a text channel.",
                    ephemeral=True,
                )
                return

            # Defer response as this may take a moment
            await interaction.response.defer(ephemeral=True)

            # Build and send embed
            embed = build_panel_embed(panel=panel, guild=interaction.guild)

            try:
                message = await channel.send(embed=embed)

                # Add reactions
                for mapping in panel.role_mappings:
                    emoji = self._mapping_to_partial_emoji(mapping)
                    if emoji:
                        try:
                            await message.add_reaction(emoji)
                        except discord.HTTPException as e:
                            guild_name = interaction.guild.name
                            logger.warning(f"[{guild_name}] Failed to add reaction: {e}")

                # Update panel with message ID
                await service.set_message_id(
                    panel_id=panel.id, message_id=message.id, guild_name=interaction.guild.name
                )
                await session.commit()

                await interaction.followup.send(
                    f"Panel **{panel_name}** posted to {channel.mention}!",
                    ephemeral=True,
                )

            except discord.Forbidden:
                await interaction.followup.send(
                    "Cannot send message to that channel - check permissions.",
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"[{interaction.guild.name}] Error posting panel: {e}")
                await interaction.followup.send(
                    "An error occurred while posting the panel.",
                    ephemeral=True,
                )

    async def _handle_refresh(
        self,
        interaction: discord.Interaction,
        panel_name: str,
    ) -> None:
        """Handle refresh command - update posted panel.

        Args:
            interaction: Discord interaction
            panel_name: Panel name
        """
        if not interaction.guild:
            return

        config = await self._get_config(interaction.guild.id)

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        # Check permission
        manage_roles = config.get(ConfigKey.MANAGE_ROLES) or []
        if not self._has_permission(member, manage_roles):
            await interaction.response.send_message(
                config.get(ConfigKey.NO_PERMISSION_TEXT) or "No permission.",
                ephemeral=True,
            )
            return

        async with self.bot.database.session() as session:
            service = ReactionRolesService(session)

            panel = await service.get_by_name(guild_id=interaction.guild.id, name=panel_name)
            if not panel:
                await interaction.response.send_message(
                    config.get(ConfigKey.NOT_FOUND_TEXT) or "Panel not found.",
                    ephemeral=True,
                )
                return

            if not panel.message_id:
                await interaction.response.send_message(
                    f"Panel **{panel_name}** is not posted yet. Use `post` first.",
                    ephemeral=True,
                )
                return

            # Get channel and message
            channel = interaction.guild.get_channel(panel.channel_id)
            if not isinstance(channel, discord.TextChannel):
                await interaction.response.send_message(
                    "Target channel not found.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True)

            try:
                message = await channel.fetch_message(panel.message_id)

                # Update embed
                embed = build_panel_embed(panel=panel, guild=interaction.guild)
                await message.edit(embed=embed)

                # Clear and re-add reactions
                await message.clear_reactions()
                for mapping in panel.role_mappings:
                    emoji = self._mapping_to_partial_emoji(mapping)
                    if emoji:
                        try:
                            await message.add_reaction(emoji)
                        except discord.HTTPException as e:
                            guild_name = interaction.guild.name
                            logger.warning(f"[{guild_name}] Failed to add reaction: {e}")

                await interaction.followup.send(
                    f"Panel **{panel_name}** refreshed!",
                    ephemeral=True,
                )

            except discord.NotFound:
                await interaction.followup.send(
                    "Panel message not found - it may have been deleted. "
                    "Use `post` to create a new one.",
                    ephemeral=True,
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "Cannot edit that message - check permissions.",
                    ephemeral=True,
                )

    async def _handle_delete(
        self,
        interaction: discord.Interaction,
        panel_name: str,
    ) -> None:
        """Handle delete command.

        Args:
            interaction: Discord interaction
            panel_name: Panel name
        """
        if not interaction.guild:
            return

        config = await self._get_config(interaction.guild.id)

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        # Check permission
        manage_roles = config.get(ConfigKey.MANAGE_ROLES) or []
        if not self._has_permission(member, manage_roles):
            await interaction.response.send_message(
                config.get(ConfigKey.NO_PERMISSION_TEXT) or "No permission.",
                ephemeral=True,
            )
            return

        async with self.bot.database.session() as session:
            service = ReactionRolesService(session)

            panel = await service.get_by_name(guild_id=interaction.guild.id, name=panel_name)
            if not panel:
                await interaction.response.send_message(
                    config.get(ConfigKey.NOT_FOUND_TEXT) or "Panel not found.",
                    ephemeral=True,
                )
                return

            # Try to delete the message if posted
            if panel.message_id:
                channel = interaction.guild.get_channel(panel.channel_id)
                if isinstance(channel, discord.TextChannel):
                    try:
                        message = await channel.fetch_message(panel.message_id)
                        await message.delete()
                    except (discord.NotFound, discord.Forbidden):
                        pass

            await service.delete(panel_id=panel.id, guild_name=interaction.guild.name)
            await session.commit()

        await interaction.response.send_message(
            f"Panel **{panel_name}** deleted.",
            ephemeral=True,
        )

        # Send audit notification
        if config.get(ConfigKey.AUDIT_PANEL_DELETED):
            audit_channel_id = config.get(ConfigKey.AUDIT_CHANNEL)
            if audit_channel_id:
                template = config.get(ConfigKey.AUDIT_PANEL_DELETED_MSG)
                if template:
                    msg = format_message(
                        template,
                        panel_name=panel_name,
                        user_mention=member.mention,
                    )
                    await self._send_audit_message(interaction.guild, audit_channel_id, msg)

    async def _handle_list(self, interaction: discord.Interaction) -> None:
        """Handle list command.

        Args:
            interaction: Discord interaction
        """
        if not interaction.guild:
            return

        async with self.bot.database.session() as session:
            service = ReactionRolesService(session)
            panels = await service.get_all_for_guild(interaction.guild.id)

        if not panels:
            await interaction.response.send_message(
                "No reaction role panels found.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Reaction Role Panels",
            color=0x5865F2,
        )

        for panel in panels:
            channel = interaction.guild.get_channel(panel.channel_id)
            channel_name = channel.mention if channel else f"<#{panel.channel_id}>"
            status = "Posted" if panel.message_id else "Not posted"
            mappings_count = len(panel.role_mappings)

            value_lines = [
                f"Type: {panel.panel_type}",
                f"Channel: {channel_name}",
                f"Mappings: {mappings_count}",
                f"Status: {status}",
            ]
            embed.add_field(
                name=panel.name,
                value="\n".join(value_lines),
                inline=True,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _handle_info(
        self,
        interaction: discord.Interaction,
        panel_name: str,
    ) -> None:
        """Handle info command.

        Args:
            interaction: Discord interaction
            panel_name: Panel name
        """
        if not interaction.guild:
            return

        config = await self._get_config(interaction.guild.id)

        async with self.bot.database.session() as session:
            service = ReactionRolesService(session)

            panel = await service.get_by_name(guild_id=interaction.guild.id, name=panel_name)
            if not panel:
                await interaction.response.send_message(
                    config.get(ConfigKey.NOT_FOUND_TEXT) or "Panel not found.",
                    ephemeral=True,
                )
                return

        channel = interaction.guild.get_channel(panel.channel_id)
        channel_name = channel.mention if channel else f"<#{panel.channel_id}>"

        creator = interaction.guild.get_member(panel.created_by)
        creator_str = creator.mention if creator else f"<@{panel.created_by}>"

        embed = discord.Embed(
            title=f"Panel: {panel.name}",
            color=0x5865F2,
        )
        embed.add_field(name="Type", value=panel.panel_type, inline=True)
        embed.add_field(name="Channel", value=channel_name, inline=True)
        embed.add_field(
            name="Status",
            value="Posted" if panel.message_id else "Not posted",
            inline=True,
        )
        embed.add_field(name="Created by", value=creator_str, inline=True)
        embed.add_field(
            name="Created at",
            value=f"<t:{int(panel.created_at.timestamp())}:R>",
            inline=True,
        )

        # DM settings
        dm_settings = []
        if panel.dm_on_missing_role:
            dm_settings.append("Missing role DM")
        if panel.dm_on_role_change:
            dm_settings.append("Role change DM")
        embed.add_field(
            name="DM Settings",
            value=", ".join(dm_settings) if dm_settings else "None",
            inline=True,
        )

        # Required roles
        if panel.required_roles:
            role_mentions = []
            for role_id in panel.required_roles:
                role = interaction.guild.get_role(role_id)
                role_mentions.append(role.mention if role else f"<@&{role_id}>")
            embed.add_field(
                name="Required Roles",
                value=", ".join(role_mentions),
                inline=False,
            )

        # Role mappings
        mappings_display = format_mappings_display(
            mappings=panel.role_mappings, guild=interaction.guild
        )
        embed.add_field(name="Mappings", value=mappings_display, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _parse_emoji(self, emoji_input: str) -> tuple[str, int | None]:
        """Parse an emoji input string.

        Args:
            emoji_input: Emoji string (unicode or <:name:id>)

        Returns:
            tuple[str, int | None]: (emoji_name, emoji_id or None)
        """
        # Check for custom emoji format <:name:id> or <a:name:id>
        import re

        custom_match = re.match(r"<a?:([^:]+):(\d+)>", emoji_input)
        if custom_match:
            return custom_match.group(1), int(custom_match.group(2))

        # Unicode emoji
        return emoji_input.strip(), None


async def setup(bot: DiscordBot) -> None:
    """Load the roles cog.

    Args:
        bot: Bot instance
    """
    get_config_schema_service().register_schema(ROLES_CONFIG_SCHEMA)
    await bot.add_cog(RolesCog(bot))
    logger.info("RolesCog loaded")


async def teardown(bot: DiscordBot) -> None:
    """Unload the roles cog.

    Args:
        bot: Bot instance
    """
    cog = bot.get_cog("RolesCog")
    if cog and isinstance(cog, RolesCog):
        for guild_id in list(cog._registered_commands.keys()):
            guild = bot.get_guild(guild_id)
            if guild:
                await cog._unregister_guild_commands(guild)
    get_config_schema_service().unregister_schema(COG_NAME)
    logger.info("RolesCog unloaded")
