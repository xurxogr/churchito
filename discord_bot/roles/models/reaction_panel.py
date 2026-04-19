"""Model for reaction role panels."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from nanoid import generate
from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from discord_bot.common.models import Base


def _generate_public_id() -> str:
    """Generate a unique public ID using NanoID."""
    return str(generate(size=21))


class PanelType(StrEnum):
    """Types of reaction role panels."""

    TOGGLE = "toggle"  # React = add, unreact = remove (independent)
    EXCLUSIVE = "exclusive"  # Only one role active, switching removes previous
    VERIFY = "verify"  # React = add role + remove reaction (one-time use)


class ReactionPanel(Base):
    """Model for reaction role panels.

    A panel is a message with emoji reactions that allow users to
    self-assign roles by reacting.
    """

    __tablename__ = "reaction_panels"
    __table_args__ = (
        Index("ix_reaction_panel_guild_id", "guild_id"),
        Index("ix_reaction_panel_message", "guild_id", "channel_id", "message_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        String(21), unique=True, nullable=False, default=_generate_public_id
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    panel_type: Mapped[str] = mapped_column(String(20), nullable=False, default=PanelType.TOGGLE)

    # Emoji-role mappings: [{emoji, emoji_id, role_id, display_name}, ...]
    # emoji: unicode string OR custom emoji name
    # emoji_id: custom emoji ID (null for unicode)
    # role_id: Discord role ID
    # display_name: optional display name for the role option
    role_mappings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)

    # Role IDs allowed to use this panel (empty = everyone)
    required_roles: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

    # Per-panel DM settings
    dm_on_missing_role: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dm_on_role_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Exclusive panel settings
    # If True, user must already have one of the panel's roles to switch (no new assignments)
    exclusive_require_existing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Embed configuration (JSON)
    embed_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Metadata
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        """String representation.

        Returns:
            str: String representation of the panel
        """
        return (
            f"<ReactionPanel(id={self.id}, guild_id={self.guild_id}, "
            f"name={self.name!r}, type={self.panel_type})>"
        )

    def has_required_role(self, member_role_ids: list[int]) -> bool:
        """Check if user has any of the required roles.

        Args:
            member_role_ids: List of role IDs the user has

        Returns:
            bool: True if user has access (required_roles empty or has match)
        """
        if not self.required_roles:
            return True
        return bool(set(member_role_ids) & set(self.required_roles))

    def find_mapping_by_emoji(
        self, emoji_str: str, emoji_id: int | None = None
    ) -> dict[str, Any] | None:
        """Find a role mapping by emoji.

        Args:
            emoji_str: Unicode emoji string OR custom emoji name
            emoji_id: Custom emoji ID (None for unicode emojis)

        Returns:
            dict | None: Matching mapping or None
        """
        for mapping in self.role_mappings:
            mapping_emoji_id = mapping.get("emoji_id")

            # Custom emoji: match by ID (convert both to int for comparison)
            if emoji_id is not None and mapping_emoji_id is not None:
                if int(mapping_emoji_id) == emoji_id:
                    return mapping
            # Unicode emoji: match by string (and no emoji_id in mapping)
            elif emoji_id is None and mapping.get("emoji") == emoji_str and not mapping_emoji_id:
                return mapping
        return None

    def get_all_role_ids(self) -> list[int]:
        """Get all role IDs from mappings.

        Returns:
            list[int]: List of role IDs
        """
        return [int(mapping["role_id"]) for mapping in self.role_mappings if "role_id" in mapping]
