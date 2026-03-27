"""Stockpile management cog."""

import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.utils import (
    get_hex_display_name,
    is_valid_city,
    is_valid_hex,
    load_hex_cities,
)
from discord_bot.stockpile.config import COG_NAME, STOCKPILE_CONFIG_SCHEMA
from discord_bot.stockpile.enums import ConfigKey
from discord_bot.stockpile.formatters import (
    format_message,
    format_stockpile_item,
    group_stockpiles_by_location,
    validate_code,
)
from discord_bot.stockpile.service import StockpileService

logger = logging.getLogger(__name__)


class StockpileCog(commands.Cog):
    """Cog for stockpile management."""

    def __init__(self, bot: DiscordBot) -> None:
        """Initialize the stockpile cog.

        Args:
            bot (DiscordBot): Bot instance
        """
        self.bot = bot
        # Track registered commands per guild:
        # {guild_id: {"add": name, "show": name, "delete": name}}
        self._registered_commands: dict[int, dict[str, str]] = {}

    def get_locked_options(self) -> dict[str, dict[str, Any]]:
        """Get options locked by deployment configuration.

        Returns:
            dict[str, dict[str, Any]]: Map of key -> {locked, reason}
        """
        return {}

    # ===== DYNAMIC COMMAND REGISTRATION =====

    async def _register_guild_commands(self, guild: discord.Guild) -> None:
        """Register stockpile commands for a guild.

        Args:
            guild (discord.Guild): Discord guild
        """
        if not await self._is_cog_enabled(guild.id):
            logger.debug(f"[{guild.name}] Stockpile cog disabled, not registering commands")
            if guild.id in self._registered_commands:
                await self._unregister_guild_commands(guild)
            return

        config = await self._get_config(guild.id)

        # Only register commands if a command channel is configured
        command_channel = config.get(ConfigKey.COMMAND_CHANNEL)
        if not command_channel:
            logger.debug(f"[{guild.name}] No command channel configured, not registering commands")
            if guild.id in self._registered_commands:
                await self._unregister_guild_commands(guild)
            return

        if guild.id not in self._registered_commands:
            self._registered_commands[guild.id] = {}

        # Register commands with configured names
        add_name = config.get(ConfigKey.ADD_COMMAND_NAME, "stockpile_add")
        show_name = config.get(ConfigKey.SHOW_COMMAND_NAME, "stockpile_show")
        delete_name = config.get(ConfigKey.DELETE_COMMAND_NAME, "stockpile_delete")

        await self._register_command(guild, "add", add_name, "Add a new stockpile")
        await self._register_command(guild, "show", show_name, "Show stockpiles")
        await self._register_command(guild, "delete", delete_name, "Delete a stockpile")

    async def _register_command(
        self,
        guild: discord.Guild,
        key: str,
        name: str,
        description: str,
    ) -> None:
        """Register a single stockpile command.

        Args:
            guild (discord.Guild): Discord guild
            key (str): Command key for tracking
            name (str): Command name
            description (str): Command description
        """
        old_name = self._registered_commands.get(guild.id, {}).get(key)
        if old_name == name:
            return  # Already registered

        if old_name:
            self.bot.tree.remove_command(old_name, guild=guild)
            logger.info(f"[{guild.name}] Command '/{old_name}' removed")

        if key == "add":
            cmd = self._create_add_command(name, description)
        elif key == "show":
            cmd = self._create_show_command(name, description)
        elif key == "delete":
            cmd = self._create_delete_command(name, description)
        else:
            return

        self.bot.tree.add_command(cmd, guild=guild)
        self._registered_commands[guild.id][key] = name
        logger.info(f"[{guild.name}] Command '/{name}' registered")

    def _create_add_command(
        self, name: str, description: str
    ) -> app_commands.Command[Any, Any, Any]:
        """Create the stockpile_add command.

        Args:
            name (str): Command name
            description (str): Command description

        Returns:
            app_commands.Command: The command
        """

        @app_commands.command(name=name, description=description)
        @app_commands.describe(
            hex="The hex location",
            city="The city within the hex",
            stockpile_name="Stockpile name (max 10 characters)",
            code="6-digit access code",
            role1="First role that can view this stockpile",
            role2="Second role that can view (optional)",
            role3="Third role that can view (optional)",
        )
        @app_commands.autocomplete(
            hex=self.hex_autocomplete,
            city=self.city_autocomplete,
            role1=self.role1_autocomplete,
            role2=self.role2_autocomplete,
            role3=self.role3_autocomplete,
        )
        async def stockpile_add_cmd(
            interaction: discord.Interaction,
            hex: str,
            city: str,
            stockpile_name: str,
            code: str,
            role1: str,
            role2: str | None = None,
            role3: str | None = None,
        ) -> None:
            await self._handle_stockpile_add(
                interaction, hex, city, stockpile_name, code, role1, role2, role3
            )

        return stockpile_add_cmd

    def _create_show_command(
        self, name: str, description: str
    ) -> app_commands.Command[Any, Any, Any]:
        """Create the stockpile_show command.

        Args:
            name (str): Command name
            description (str): Command description

        Returns:
            app_commands.Command: The command
        """

        @app_commands.command(name=name, description=description)
        @app_commands.describe(
            hex="Filter by hex (optional)",
            city="Filter by city (optional, requires hex)",
        )
        @app_commands.autocomplete(hex=self.hex_autocomplete, city=self.city_autocomplete)
        async def stockpile_show_cmd(
            interaction: discord.Interaction,
            hex: str | None = None,
            city: str | None = None,
        ) -> None:
            await self._handle_stockpile_show(interaction, hex, city)

        return stockpile_show_cmd

    def _create_delete_command(
        self, name: str, description: str
    ) -> app_commands.Command[Any, Any, Any]:
        """Create the stockpile_delete command.

        Args:
            name (str): Command name
            description (str): Command description

        Returns:
            app_commands.Command: The command
        """

        @app_commands.command(name=name, description=description)
        @app_commands.describe(
            hex="The hex location",
            city="The city within the hex",
            stockpile_name="The stockpile name to delete",
        )
        @app_commands.autocomplete(
            hex=self.hex_autocomplete,
            city=self.city_autocomplete,
            stockpile_name=self.stockpile_name_autocomplete,
        )
        async def stockpile_delete_cmd(
            interaction: discord.Interaction,
            hex: str,
            city: str,
            stockpile_name: str,
        ) -> None:
            await self._handle_stockpile_delete(interaction, hex, city, stockpile_name)

        return stockpile_delete_cmd

    async def _unregister_guild_commands(self, guild: discord.Guild) -> None:
        """Remove registered commands from a guild.

        Args:
            guild (discord.Guild): Discord guild
        """
        commands = self._registered_commands.get(guild.id, {})
        for _key, command_name in list(commands.items()):
            self.bot.tree.remove_command(command_name, guild=guild)
            logger.info(f"[{guild.name}] Command '/{command_name}' removed")
        if guild.id in self._registered_commands:
            del self._registered_commands[guild.id]

    async def _sync_guild_commands(self, guild: discord.Guild) -> None:
        """Sync commands of a guild with Discord.

        Args:
            guild (discord.Guild): Discord guild
        """
        try:
            await self.bot.tree.sync(guild=guild)
            logger.info(f"[{guild.name}] Stockpile commands synced")
        except Exception as e:
            logger.error(f"[{guild.name}] Error syncing stockpile commands: {e}")

    # ===== EVENT LISTENERS =====

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Register commands when the bot is ready."""
        logger.info("StockpileCog: Registering commands in all guilds...")
        for guild in self.bot.guilds:
            try:
                await self._register_guild_commands(guild)
            except Exception as e:
                logger.error(f"[{guild.name}] Error registering stockpile commands: {e}")

        # Sync commands for all guilds
        for guild in self.bot.guilds:
            if guild.id in self._registered_commands:
                await self._sync_guild_commands(guild)

        logger.info("StockpileCog: Command registration completed")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Register commands when the bot joins a guild.

        Args:
            guild (discord.Guild): Guild the bot joined
        """
        logger.info(f"[{guild.name}] StockpileCog: Bot joined, registering commands...")
        await self._register_guild_commands(guild)
        if guild.id in self._registered_commands:
            await self._sync_guild_commands(guild)

    # ===== CONFIG CHANGE CALLBACKS =====

    async def on_config_changed(self, guild: discord.Guild, keys: list[str]) -> None:
        """Handle configuration changes from the web dashboard.

        Args:
            guild (discord.Guild): Guild where configuration changed
            keys (list[str]): List of configuration keys that changed
        """
        # Keys that affect command registration
        command_registration_keys = {
            ConfigKey.ADD_COMMAND_NAME,
            ConfigKey.SHOW_COMMAND_NAME,
            ConfigKey.DELETE_COMMAND_NAME,
            ConfigKey.COMMAND_CHANNEL,
        }

        if set(keys) & command_registration_keys:
            changed = set(keys) & command_registration_keys
            logger.info(f"[{guild.name}] Config {changed} changed, re-registering commands...")
            await self._register_guild_commands(guild)
            await self._sync_guild_commands(guild)

    async def on_cog_toggled(self, guild: discord.Guild, enabled: bool) -> None:
        """Handle when the cog is enabled or disabled.

        Args:
            guild (discord.Guild): Guild where state changed
            enabled (bool): True if enabled, False if disabled
        """
        if enabled:
            logger.info(f"[{guild.name}] Stockpile cog enabled, registering commands...")
            await self._register_guild_commands(guild)
            if guild.id in self._registered_commands:
                await self._sync_guild_commands(guild)
        else:
            logger.info(f"[{guild.name}] Stockpile cog disabled, removing commands...")
            await self._unregister_guild_commands(guild)
            await self._sync_guild_commands(guild)

    async def _is_cog_enabled(self, guild_id: int) -> bool:
        """Check if the cog is enabled for a guild.

        Args:
            guild_id (int): Guild ID

        Returns:
            bool: True if enabled
        """
        async with self.bot.database.session() as session:
            config_service = ConfigService(session=session)
            return await config_service.is_cog_enabled(guild_id=guild_id, cog_name=COG_NAME)

    async def _get_config(self, guild_id: int) -> dict[str, Any]:
        """Get all config for this cog.

        Args:
            guild_id (int): Guild ID

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
            member (discord.Member): Discord member
            allowed_role_ids (list[int]): List of allowed role IDs

        Returns:
            bool: True if member has permission
        """
        if not allowed_role_ids:
            # No roles configured means no permission
            return False
        member_role_ids = {role.id for role in member.roles}
        return bool(member_role_ids & set(allowed_role_ids))

    async def _check_channel(
        self,
        interaction: discord.Interaction,
        config: dict[str, Any],
    ) -> bool:
        """Check if command is used in the correct channel.

        Args:
            interaction (discord.Interaction): Discord interaction
            config (dict[str, Any]): Cog configuration

        Returns:
            bool: True if channel is correct or not configured, False otherwise
        """
        command_channel_id = config.get(ConfigKey.COMMAND_CHANNEL)
        if not command_channel_id:
            # No channel configured, allow anywhere
            return True

        if interaction.channel_id == command_channel_id:
            return True

        # Wrong channel - send error message
        channel = interaction.guild.get_channel(command_channel_id) if interaction.guild else None
        channel_mention = channel.mention if channel else f"<#{command_channel_id}>"
        error_msg = (
            config.get(ConfigKey.WRONG_CHANNEL_TEXT)
            or "This command can only be used in {channel}."
        )
        error_msg = error_msg.replace("{channel}", channel_mention)

        await interaction.response.send_message(error_msg, ephemeral=True)
        return False

    async def _send_add_notification(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
        name: str,
        hex_display: str,
        city: str,
        code: str,
        roles: list[discord.Role],
        creator: discord.Member,
    ) -> None:
        """Send notification when a stockpile is added.

        Args:
            guild (discord.Guild): Discord guild
            config (dict[str, Any]): Cog configuration
            name (str): Stockpile name
            hex_display (str): Hex display name
            city (str): City name
            code (str): Access code
            roles (list[discord.Role]): View roles
            creator (discord.Member): User who created the stockpile
        """
        channel_id = config.get(ConfigKey.COMMAND_CHANNEL)
        message_template = config.get(ConfigKey.ADD_NOTIFICATION_TEXT)

        if not channel_id or not message_template:
            return

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        roles_str = ", ".join(role.mention for role in roles)
        message = format_message(
            message_template,
            name=name,
            hex=hex_display,
            city=city,
            code=code,
            roles=roles_str,
            creator=creator.mention,
        )

        try:
            await channel.send(message)
        except discord.Forbidden:
            logger.warning(f"[{guild.name}] Cannot send add notification: no permission")
        except Exception as e:
            logger.error(f"[{guild.name}] Error sending add notification: {e}")

    async def _send_delete_notification(
        self,
        guild: discord.Guild,
        config: dict[str, Any],
        name: str,
        hex_display: str,
        city: str,
        deleted_by: discord.Member,
    ) -> None:
        """Send notification when a stockpile is deleted.

        Args:
            guild (discord.Guild): Discord guild
            config (dict[str, Any]): Cog configuration
            name (str): Stockpile name
            hex_display (str): Hex display name
            city (str): City name
            deleted_by (discord.Member): User who deleted the stockpile
        """
        channel_id = config.get(ConfigKey.COMMAND_CHANNEL)
        message_template = config.get(ConfigKey.DELETE_NOTIFICATION_TEXT)

        if not channel_id or not message_template:
            return

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        message = format_message(
            message_template,
            name=name,
            hex=hex_display,
            city=city,
            deleted_by=deleted_by.mention,
        )

        try:
            await channel.send(message)
        except discord.Forbidden:
            logger.warning(f"[{guild.name}] Cannot send delete notification: no permission")
        except Exception as e:
            logger.error(f"[{guild.name}] Error sending delete notification: {e}")

    # ===== AUTOCOMPLETE HANDLERS =====

    async def _get_allowed_roles(
        self,
        guild: discord.Guild,
        exclude_role_ids: set[int] | None = None,
    ) -> list[discord.Role]:
        """Get allowed view roles for a guild, optionally excluding some.

        Args:
            guild (discord.Guild): Discord guild
            exclude_role_ids (set[int] | None): Role IDs to exclude from the list

        Returns:
            list[discord.Role]: Filtered list of allowed roles
        """
        config = await self._get_config(guild.id)
        allowed_role_ids = config.get(ConfigKey.ALLOWED_VIEW_ROLES) or []

        if not allowed_role_ids:
            return []

        exclude = exclude_role_ids or set()
        roles = []
        for role_id in allowed_role_ids:
            if role_id in exclude:
                continue
            role = guild.get_role(role_id)
            if role:
                roles.append(role)

        return roles

    async def role1_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for first role selection.

        Args:
            interaction (discord.Interaction): Discord interaction
            current (str): Current input value

        Returns:
            list[app_commands.Choice[str]]: Matching role choices
        """
        if not interaction.guild:
            return []

        roles = await self._get_allowed_roles(interaction.guild)
        current_lower = current.lower()

        choices = [
            app_commands.Choice(name=role.name, value=str(role.id))
            for role in roles
            if current_lower in role.name.lower()
        ]
        return choices[:25]

    async def role2_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for second role selection, excluding role1.

        Args:
            interaction (discord.Interaction): Discord interaction
            current (str): Current input value

        Returns:
            list[app_commands.Choice[str]]: Matching role choices
        """
        if not interaction.guild:
            return []

        # Exclude role1 if selected
        exclude: set[int] = set()
        role1_id = getattr(interaction.namespace, "role1", None)
        if role1_id:
            try:
                exclude.add(int(role1_id))
            except (ValueError, TypeError):
                pass

        roles = await self._get_allowed_roles(interaction.guild, exclude)
        current_lower = current.lower()

        choices = [
            app_commands.Choice(name=role.name, value=str(role.id))
            for role in roles
            if current_lower in role.name.lower()
        ]
        return choices[:25]

    async def role3_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for third role selection, excluding role1 and role2.

        Args:
            interaction (discord.Interaction): Discord interaction
            current (str): Current input value

        Returns:
            list[app_commands.Choice[str]]: Matching role choices
        """
        if not interaction.guild:
            return []

        # Exclude role1 and role2 if selected
        exclude: set[int] = set()
        for attr in ("role1", "role2"):
            role_id = getattr(interaction.namespace, attr, None)
            if role_id:
                try:
                    exclude.add(int(role_id))
                except (ValueError, TypeError):
                    pass

        roles = await self._get_allowed_roles(interaction.guild, exclude)
        current_lower = current.lower()

        choices = [
            app_commands.Choice(name=role.name, value=str(role.id))
            for role in roles
            if current_lower in role.name.lower()
        ]
        return choices[:25]

    async def hex_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for hex selection.

        Args:
            interaction (discord.Interaction): Discord interaction
            current (str): Current input value

        Returns:
            list[app_commands.Choice[str]]: Matching hex choices
        """
        hex_data = load_hex_cities()
        current_lower = current.lower()

        choices = [
            app_commands.Choice(name=data["display_name"], value=hex_key)
            for hex_key, data in hex_data.items()
            if current_lower in data["display_name"].lower()
        ]
        return choices[:25]  # Discord limit

    async def city_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for city selection, filtered by selected hex.

        Args:
            interaction (discord.Interaction): Discord interaction
            current (str): Current input value

        Returns:
            list[app_commands.Choice[str]]: Matching city choices
        """
        hex_key = interaction.namespace.hex
        if not hex_key:
            return []

        hex_data = load_hex_cities()
        cities = hex_data.get(hex_key, {}).get("major_locations", [])
        current_lower = current.lower()

        choices = [
            app_commands.Choice(name=city, value=city)
            for city in cities
            if current_lower in city.lower()
        ]
        return choices[:25]

    async def stockpile_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for stockpile name (for delete command).

        Shows only stockpiles accessible to the user.

        Args:
            interaction (discord.Interaction): Discord interaction
            current (str): Current input value

        Returns:
            list[app_commands.Choice[str]]: Matching stockpile name choices
        """
        if not interaction.guild:
            return []

        hex_key = interaction.namespace.hex
        city = interaction.namespace.city
        if not hex_key or not city:
            return []

        member = interaction.user
        if not isinstance(member, discord.Member):
            return []

        user_role_ids = [role.id for role in member.roles]
        current_lower = current.lower()

        async with self.bot.database.session() as session:
            service = StockpileService(session=session)
            names = await service.get_stockpile_names_at_location(
                guild_id=interaction.guild.id,
                hex_key=hex_key,
                city=city,
                user_role_ids=user_role_ids,
            )

        choices = [
            app_commands.Choice(name=name, value=name)
            for name in names
            if current_lower in name.lower()
        ]
        return choices[:25]

    # ===== COMMAND HANDLERS =====

    async def _handle_stockpile_add(
        self,
        interaction: discord.Interaction,
        hex: str,
        city: str,
        name: str,
        code: str,
        role1: str,
        role2: str | None = None,
        role3: str | None = None,
    ) -> None:
        """Handle stockpile add command.

        Args:
            interaction (discord.Interaction): Discord interaction
            hex (str): Hex key
            city (str): City name
            name (str): Stockpile name
            code (str): Access code
            role1 (str): First view role ID
            role2 (str | None): Second view role ID
            role3 (str | None): Third view role ID
        """
        if not interaction.guild:
            return

        # Check if cog is enabled
        if not await self._is_cog_enabled(interaction.guild.id):
            await interaction.response.send_message("This feature is not enabled.", ephemeral=True)
            return

        config = await self._get_config(interaction.guild.id)

        # Check if command is used in the correct channel
        if not await self._check_channel(interaction, config):
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        # Check add permission
        add_roles = config.get(ConfigKey.ADD_ROLES) or []
        if not self._has_permission(member, add_roles):
            await interaction.response.send_message(
                config.get(ConfigKey.NO_PERMISSION_TEXT) or "No permission.",
                ephemeral=True,
            )
            return

        # Validate hex location
        if not is_valid_hex(hex):
            await interaction.response.send_message(
                "Invalid hex location selected.",
                ephemeral=True,
            )
            return

        # Validate city for hex
        if not is_valid_city(hex_key=hex, city=city):
            await interaction.response.send_message(
                "Invalid city selected for this hex.",
                ephemeral=True,
            )
            return

        # Validate name length
        if len(name) > 10:
            await interaction.response.send_message(
                "Stockpile name must be 10 characters or less.",
                ephemeral=True,
            )
            return

        # Validate code format
        if not validate_code(code):
            await interaction.response.send_message(
                config.get(ConfigKey.INVALID_CODE_TEXT) or "Invalid code.",
                ephemeral=True,
            )
            return

        # Convert role ID strings to Role objects
        role_ids_str = [role1]
        if role2:
            role_ids_str.append(role2)
        if role3:
            role_ids_str.append(role3)

        selected_roles: list[discord.Role] = []
        for role_id_str in role_ids_str:
            try:
                role_id = int(role_id_str)
                role = interaction.guild.get_role(role_id)
                if role:
                    selected_roles.append(role)
                else:
                    await interaction.response.send_message(
                        "One or more selected roles no longer exist.",
                        ephemeral=True,
                    )
                    return
            except (ValueError, TypeError):
                await interaction.response.send_message(
                    "Invalid role selection.",
                    ephemeral=True,
                )
                return

        # Validate roles are in allowed list
        allowed_view_roles = config.get(ConfigKey.ALLOWED_VIEW_ROLES) or []
        if allowed_view_roles:
            for role in selected_roles:
                if role.id not in allowed_view_roles:
                    await interaction.response.send_message(
                        config.get(ConfigKey.INVALID_ROLES_TEXT) or "Invalid roles.",
                        ephemeral=True,
                    )
                    return

        view_role_ids = [role.id for role in selected_roles]

        hex_display = get_hex_display_name(hex)

        # Check for duplicate stockpile (guild-wide uniqueness)
        async with self.bot.database.session() as session:
            service = StockpileService(session=session)
            existing = await service.get_by_guild_and_name(
                guild_id=interaction.guild.id,
                name=name,
            )
            if existing:
                existing_hex_display = get_hex_display_name(existing.hex_key)
                await interaction.response.send_message(
                    f"A stockpile named **{name}** already exists at "
                    f"**{existing_hex_display}** - **{existing.city}**.",
                    ephemeral=True,
                )
                return

            # Create stockpile
            await service.create(
                guild_id=interaction.guild.id,
                hex_key=hex,
                city=city,
                name=name,
                code=code,
                view_roles=view_role_ids,
                created_by=member.id,
                guild_name=interaction.guild.name,
            )
            await session.commit()

        # Send success message
        success_msg = format_message(
            config.get(ConfigKey.ADD_SUCCESS_TEXT),
            name=name,
            hex=hex_display,
            city=city,
            code=code,
        )
        await interaction.response.send_message(success_msg, ephemeral=True)

        # Send notification if configured
        await self._send_add_notification(
            interaction.guild,
            config,
            name=name,
            hex_display=hex_display,
            city=city,
            code=code,
            roles=selected_roles,
            creator=member,
        )

    async def _handle_stockpile_show(
        self,
        interaction: discord.Interaction,
        hex: str | None = None,
        city: str | None = None,
    ) -> None:
        """Handle stockpile show command.

        Args:
            interaction (discord.Interaction): Discord interaction
            hex (str | None): Optional hex filter
            city (str | None): Optional city filter
        """
        if not interaction.guild:
            return

        if not await self._is_cog_enabled(interaction.guild.id):
            await interaction.response.send_message("This feature is not enabled.", ephemeral=True)
            return

        config = await self._get_config(interaction.guild.id)

        # Check if command is used in the correct channel
        if not await self._check_channel(interaction, config):
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        user_role_ids = [role.id for role in member.roles]

        async with self.bot.database.session() as session:
            service = StockpileService(session=session)
            stockpiles = await service.get_accessible_stockpiles(
                guild_id=interaction.guild.id,
                user_role_ids=user_role_ids,
                hex_key=hex,
                city=city,
            )

        if not stockpiles:
            hex_display = get_hex_display_name(hex) if hex else "all hexes"
            city_display = city or "all cities"
            empty_msg = format_message(
                config.get(ConfigKey.SHOW_EMPTY_TEXT),
                hex=hex_display,
                city=city_display,
            )
            await interaction.response.send_message(empty_msg, ephemeral=True)
            return

        # Group by location
        grouped = group_stockpiles_by_location(list(stockpiles))
        header_template = config.get(ConfigKey.SHOW_HEADER_TEXT) or ""
        item_template = config.get(ConfigKey.SHOW_ITEM_TEXT) or ""

        lines: list[str] = []
        for (hex_key, city_name), location_stockpiles in grouped.items():
            hex_display = get_hex_display_name(hex_key)

            # Add header
            header = format_message(
                header_template,
                hex=hex_display,
                city=city_name,
                count=len(location_stockpiles),
            )
            lines.append(header)

            # Add items
            for stockpile in location_stockpiles:
                item = format_stockpile_item(stockpile, item_template, hex_display)
                lines.append(f"  {item}")

            lines.append("")  # Empty line between groups

        message = "\n".join(lines).strip()

        # Discord has a 2000 character limit
        if len(message) > 2000:
            message = message[:1997] + "..."

        await interaction.response.send_message(message, ephemeral=True)

    async def _handle_stockpile_delete(
        self,
        interaction: discord.Interaction,
        hex: str,
        city: str,
        name: str,
    ) -> None:
        """Handle stockpile delete command.

        Args:
            interaction (discord.Interaction): Discord interaction
            hex (str): Hex key
            city (str): City name
            name (str): Stockpile name
        """
        if not interaction.guild:
            return

        if not await self._is_cog_enabled(interaction.guild.id):
            await interaction.response.send_message("This feature is not enabled.", ephemeral=True)
            return

        config = await self._get_config(interaction.guild.id)

        # Check if command is used in the correct channel
        if not await self._check_channel(interaction, config):
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        # Check delete permission
        delete_roles = config.get(ConfigKey.DELETE_ROLES) or []
        if not self._has_permission(member, delete_roles):
            await interaction.response.send_message(
                config.get(ConfigKey.NO_PERMISSION_TEXT) or "No permission.",
                ephemeral=True,
            )
            return

        user_role_ids = [role.id for role in member.roles]

        async with self.bot.database.session() as session:
            service = StockpileService(session=session)

            # First check if stockpile exists and user can view it
            stockpile = await service.get_by_location_and_name(
                guild_id=interaction.guild.id,
                hex_key=hex,
                city=city,
                name=name,
            )

            if not stockpile:
                await interaction.response.send_message(
                    config.get(ConfigKey.NOT_FOUND_TEXT) or "Not found.",
                    ephemeral=True,
                )
                return

            # Verify user can view this stockpile before allowing deletion
            if not stockpile.can_view(user_role_ids):
                await interaction.response.send_message(
                    config.get(ConfigKey.NO_PERMISSION_TEXT) or "No permission.",
                    ephemeral=True,
                )
                return

            # Now delete
            deleted = await service.delete(stockpile.id, interaction.guild.name)
            await session.commit()

        if not deleted:
            await interaction.response.send_message(
                config.get(ConfigKey.NOT_FOUND_TEXT) or "Not found.",
                ephemeral=True,
            )
            return

        hex_display = get_hex_display_name(hex)
        success_msg = format_message(
            config.get(ConfigKey.DELETE_SUCCESS_TEXT),
            name=name,
            hex=hex_display,
            city=city,
        )
        await interaction.response.send_message(success_msg, ephemeral=True)

        # Send notification if configured
        await self._send_delete_notification(
            interaction.guild,
            config,
            name=name,
            hex_display=hex_display,
            city=city,
            deleted_by=member,
        )


async def setup(bot: DiscordBot) -> None:
    """Load the stockpile cog.

    Args:
        bot (DiscordBot): Bot instance
    """
    get_config_schema_service().register_schema(STOCKPILE_CONFIG_SCHEMA)
    await bot.add_cog(StockpileCog(bot))
    logger.info("StockpileCog loaded")


async def teardown(bot: DiscordBot) -> None:
    """Unload the stockpile cog.

    Args:
        bot (DiscordBot): Bot instance
    """
    cog = bot.get_cog("StockpileCog")
    if cog and isinstance(cog, StockpileCog):
        for guild_id in list(cog._registered_commands.keys()):
            guild = bot.get_guild(guild_id)
            if guild:
                await cog._unregister_guild_commands(guild)
    get_config_schema_service().unregister_schema(COG_NAME)
    logger.info("StockpileCog unloaded")
