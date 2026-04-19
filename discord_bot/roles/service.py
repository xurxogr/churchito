"""Service for reaction roles operations."""

import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.roles.models import PanelType, ReactionPanel

logger = logging.getLogger(__name__)


class ReactionRolesService:
    """Service for reaction panel CRUD operations.

    Handles the creation, update, query, and deletion of reaction panels.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the reaction roles service.

        Args:
            session (AsyncSession): Database session
        """
        self._session = session

    async def create_panel(
        self,
        guild_id: int,
        channel_id: int,
        name: str,
        panel_type: PanelType,
        created_by: int,
        guild_name: str,
        role_mappings: list[dict[str, Any]] | None = None,
        required_roles: list[int] | None = None,
        dm_on_missing_role: bool = False,
        dm_on_role_change: bool = False,
        embed_config: dict[str, Any] | None = None,
        exclusive_require_existing: bool = False,
    ) -> ReactionPanel:
        """Create a new reaction panel.

        Args:
            guild_id: Guild ID
            channel_id: Channel ID where panel will be posted
            name: Panel name
            panel_type: Type of panel (toggle, exclusive, verify)
            created_by: User ID who created the panel
            guild_name: Guild name for logging
            role_mappings: Emoji-role mappings
            required_roles: Role IDs required to use panel
            dm_on_missing_role: Send DM when user lacks required role
            dm_on_role_change: Send DM on role change
            embed_config: Embed configuration
            exclusive_require_existing: For exclusive panels, require existing role to switch

        Returns:
            ReactionPanel: Created panel
        """
        panel = ReactionPanel(
            guild_id=guild_id,
            channel_id=channel_id,
            name=name,
            panel_type=panel_type,
            created_by=created_by,
            role_mappings=role_mappings or [],
            required_roles=required_roles or [],
            dm_on_missing_role=dm_on_missing_role,
            dm_on_role_change=dm_on_role_change,
            embed_config=embed_config,
            exclusive_require_existing=exclusive_require_existing,
        )
        self._session.add(panel)
        await self._session.flush()
        logger.info(
            f"[{guild_name}] Reaction panel created: {name} (ID: {panel.id}, type: {panel_type})"
        )
        return panel

    async def get_by_id(self, panel_id: int) -> ReactionPanel | None:
        """Get a panel by ID.

        Args:
            panel_id: Panel ID

        Returns:
            ReactionPanel | None: Panel or None if not found
        """
        result = await self._session.execute(
            select(ReactionPanel).where(ReactionPanel.id == panel_id)
        )
        return result.scalar_one_or_none()

    async def get_by_public_id(self, public_id: str) -> ReactionPanel | None:
        """Get a panel by public_id.

        Args:
            public_id: Public panel ID (NanoID)

        Returns:
            ReactionPanel | None: Panel or None if not found
        """
        result = await self._session.execute(
            select(ReactionPanel).where(ReactionPanel.public_id == public_id)
        )
        return result.scalar_one_or_none()

    async def get_by_message_id(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
    ) -> ReactionPanel | None:
        """Get a panel by message location.

        Args:
            guild_id: Guild ID
            channel_id: Channel ID
            message_id: Message ID

        Returns:
            ReactionPanel | None: Panel or None if not found
        """
        result = await self._session.execute(
            select(ReactionPanel).where(
                ReactionPanel.guild_id == guild_id,
                ReactionPanel.channel_id == channel_id,
                ReactionPanel.message_id == message_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_all_for_guild(self, guild_id: int) -> Sequence[ReactionPanel]:
        """Get all panels for a guild.

        Args:
            guild_id: Guild ID

        Returns:
            Sequence[ReactionPanel]: List of panels
        """
        result = await self._session.execute(
            select(ReactionPanel)
            .where(ReactionPanel.guild_id == guild_id)
            .order_by(ReactionPanel.name)
        )
        return result.scalars().all()

    async def get_panel_names(self, guild_id: int) -> list[str]:
        """Get names of all panels for a guild.

        Used for autocomplete in commands.

        Args:
            guild_id: Guild ID

        Returns:
            list[str]: List of panel names
        """
        panels = await self.get_all_for_guild(guild_id)
        return [p.name for p in panels]

    async def get_by_name(self, guild_id: int, name: str) -> ReactionPanel | None:
        """Get a panel by name within a guild.

        Args:
            guild_id: Guild ID
            name: Panel name

        Returns:
            ReactionPanel | None: Panel or None if not found
        """
        result = await self._session.execute(
            select(ReactionPanel).where(
                ReactionPanel.guild_id == guild_id,
                ReactionPanel.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def set_message_id(
        self,
        panel_id: int,
        message_id: int | None,
        guild_name: str,
    ) -> ReactionPanel | None:
        """Set or clear the message ID for a panel.

        Args:
            panel_id: Panel ID
            message_id: Discord message ID, or None to clear (unpost)
            guild_name: Guild name for logging

        Returns:
            ReactionPanel | None: Updated panel or None if not found
        """
        panel = await self.get_by_id(panel_id)
        if not panel:
            return None

        panel.message_id = message_id
        await self._session.flush()
        if message_id:
            logger.info(f"[{guild_name}] Panel {panel.name} posted (message_id: {message_id})")
        else:
            logger.info(f"[{guild_name}] Panel {panel.name} unposted")
        return panel

    async def update_mappings(
        self,
        panel_id: int,
        role_mappings: list[dict[str, Any]],
        guild_name: str,
    ) -> ReactionPanel | None:
        """Update role mappings for a panel.

        Args:
            panel_id: Panel ID
            role_mappings: New emoji-role mappings
            guild_name: Guild name for logging

        Returns:
            ReactionPanel | None: Updated panel or None if not found
        """
        panel = await self.get_by_id(panel_id)
        if not panel:
            return None

        panel.role_mappings = role_mappings
        await self._session.flush()
        logger.info(
            f"[{guild_name}] Panel {panel.name} mappings updated ({len(role_mappings)} mappings)"
        )
        return panel

    async def add_mapping(
        self,
        panel_id: int,
        emoji: str,
        emoji_id: int | None,
        role_id: int,
        display_name: str | None,
        guild_name: str,
    ) -> ReactionPanel | None:
        """Add a single mapping to a panel.

        Args:
            panel_id: Panel ID
            emoji: Emoji string (unicode or custom name)
            emoji_id: Custom emoji ID (None for unicode)
            role_id: Role ID
            display_name: Optional display name
            guild_name: Guild name for logging

        Returns:
            ReactionPanel | None: Updated panel or None if not found
        """
        panel = await self.get_by_id(panel_id)
        if not panel:
            return None

        new_mapping: dict[str, Any] = {
            "emoji": emoji,
            "role_id": role_id,
        }
        if emoji_id is not None:
            new_mapping["emoji_id"] = emoji_id
        if display_name:
            new_mapping["display_name"] = display_name

        # Create new list (immutability)
        updated_mappings = list(panel.role_mappings) + [new_mapping]
        panel.role_mappings = updated_mappings
        await self._session.flush()
        logger.info(f"[{guild_name}] Added mapping to panel {panel.name}: {emoji} -> {role_id}")
        return panel

    async def remove_mapping(
        self,
        panel_id: int,
        emoji: str,
        emoji_id: int | None,
        guild_name: str,
    ) -> ReactionPanel | None:
        """Remove a mapping from a panel by emoji.

        Args:
            panel_id: Panel ID
            emoji: Emoji string to remove
            emoji_id: Custom emoji ID (None for unicode)
            guild_name: Guild name for logging

        Returns:
            ReactionPanel | None: Updated panel or None if not found
        """
        panel = await self.get_by_id(panel_id)
        if not panel:
            return None

        # Find and remove the mapping
        updated_mappings = []
        removed = False
        for mapping in panel.role_mappings:
            if emoji_id is not None:
                if mapping.get("emoji_id") == emoji_id:
                    removed = True
                    continue
            else:
                if mapping.get("emoji") == emoji and not mapping.get("emoji_id"):
                    removed = True
                    continue
            updated_mappings.append(mapping)

        if removed:
            panel.role_mappings = updated_mappings
            await self._session.flush()
            logger.info(f"[{guild_name}] Removed mapping from panel {panel.name}: {emoji}")

        return panel

    async def update_panel(
        self,
        panel_id: int,
        guild_name: str,
        name: str | None = None,
        panel_type: PanelType | None = None,
        required_roles: list[int] | None = None,
        dm_on_missing_role: bool | None = None,
        dm_on_role_change: bool | None = None,
        embed_config: dict[str, Any] | None = None,
        exclusive_require_existing: bool | None = None,
    ) -> ReactionPanel | None:
        """Update panel properties.

        Args:
            panel_id: Panel ID
            guild_name: Guild name for logging
            name: New name (optional)
            panel_type: New type (optional)
            required_roles: New required roles (optional)
            dm_on_missing_role: New DM setting (optional)
            dm_on_role_change: New DM setting (optional)
            embed_config: New embed config (optional)
            exclusive_require_existing: For exclusive panels, require existing role (optional)

        Returns:
            ReactionPanel | None: Updated panel or None if not found
        """
        panel = await self.get_by_id(panel_id)
        if not panel:
            return None

        if name is not None:
            panel.name = name
        if panel_type is not None:
            panel.panel_type = panel_type
        if required_roles is not None:
            panel.required_roles = required_roles
        if dm_on_missing_role is not None:
            panel.dm_on_missing_role = dm_on_missing_role
        if dm_on_role_change is not None:
            panel.dm_on_role_change = dm_on_role_change
        if embed_config is not None:
            panel.embed_config = embed_config
        if exclusive_require_existing is not None:
            panel.exclusive_require_existing = exclusive_require_existing

        await self._session.flush()
        logger.info(f"[{guild_name}] Panel {panel.name} updated")
        return panel

    async def delete(self, panel_id: int, guild_name: str) -> bool:
        """Delete a panel by ID.

        Args:
            panel_id: Panel ID
            guild_name: Guild name for logging

        Returns:
            bool: True if deleted, False if not found
        """
        panel = await self.get_by_id(panel_id)
        if not panel:
            return False

        panel_name = panel.name
        await self._session.execute(delete(ReactionPanel).where(ReactionPanel.id == panel_id))
        await self._session.flush()
        logger.info(f"[{guild_name}] Reaction panel deleted: {panel_name} (ID: {panel_id})")
        return True
