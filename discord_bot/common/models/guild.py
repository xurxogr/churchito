"""Modelo de Guild para almacenar la configuración del gremio de Discord."""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from discord_bot.common.models import Base


class Guild(Base):
    """Modelo para la configuración del gremio de Discord."""

    __tablename__ = "guilds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str]
    prefix: Mapped[str] = mapped_column(default="!")
    invited_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        """Representación en cadena.

        Returns:
            str: Representación en cadena del gremio
        """
        return f"<Guild(id={self.id}, name={self.name!r})>"
