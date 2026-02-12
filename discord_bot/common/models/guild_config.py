"""Modelo para almacenar valores de configuración de guilds."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from discord_bot.common.models import Base


class GuildConfig(Base):
    """Modelo para almacenar valores de configuración por guild y cog.

    Este modelo almacena los valores de configuración establecidos
    por cada guild para cada cog del bot.
    """

    __tablename__ = "guild_configs"
    __table_args__ = (
        UniqueConstraint("guild_id", "cog_name", "key", name="uq_guild_cog_key"),
        Index("ix_guild_config_guild_id", "guild_id"),
        Index("ix_guild_config_cog_name", "cog_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cog_name: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        """Representación en cadena.

        Returns:
            str: Representación en cadena de la configuración
        """
        return f"<GuildConfig(guild_id={self.guild_id}, cog={self.cog_name!r}, key={self.key!r})>"
