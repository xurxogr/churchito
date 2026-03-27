"""Guild model for storing Discord guild configuration."""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from discord_bot.common.models import Base


class Guild(Base):
    """Model for Discord guild configuration."""

    __tablename__ = "guilds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str]
    prefix: Mapped[str] = mapped_column(default="!")
    language: Mapped[str] = mapped_column(String(5), default="en")
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
        """String representation.

        Returns:
            str: String representation of the guild
        """
        return f"<Guild(id={self.id}, name={self.name!r})>"
