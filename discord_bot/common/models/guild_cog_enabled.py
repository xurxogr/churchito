"""Model for storing cog enabled state per guild."""

from sqlalchemy import BigInteger, Boolean, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from discord_bot.common.models import Base


class GuildCogEnabled(Base):
    """Model for storing whether a cog is enabled in a guild.

    This model allows each guild to enable or disable
    individual bot cogs.
    """

    __tablename__ = "guild_cogs_enabled"
    __table_args__ = (
        UniqueConstraint("guild_id", "cog_name", name="uq_guild_cog_enabled"),
        Index("ix_guild_cog_enabled_guild_id", "guild_id"),
        Index("ix_guild_cog_enabled_cog_name", "cog_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cog_name: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        """String representation.

        Returns:
            str: String representation of the state
        """
        status = "enabled" if self.enabled else "disabled"
        return f"<GuildCogEnabled(guild_id={self.guild_id}, cog={self.cog_name!r}, {status})>"
