"""Model for stockpiles."""

from datetime import UTC, datetime

from nanoid import generate
from sqlalchemy import JSON, BigInteger, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from discord_bot.common.models import Base


def _generate_public_id() -> str:
    """Generate a unique public ID using NanoID."""
    return str(generate(size=21))


class Stockpile(Base):
    """Model for stockpiles.

    Stores stockpile information including location, access code,
    and which roles can view it.
    """

    __tablename__ = "stockpiles"
    __table_args__ = (
        Index("ix_stockpile_guild_id", "guild_id"),
        Index("ix_stockpile_hex_city", "guild_id", "hex_key", "city"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        String(21), unique=True, nullable=False, default=_generate_public_id
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hex_key: Mapped[str] = mapped_column(String(50), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(10), nullable=False)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    view_roles: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        """String representation.

        Returns:
            str: String representation of the stockpile
        """
        return (
            f"<Stockpile(id={self.id}, guild_id={self.guild_id}, "
            f"hex_key={self.hex_key!r}, city={self.city!r}, name={self.name!r})>"
        )

    def can_view(self, user_role_ids: list[int]) -> bool:
        """Check if user can view this stockpile based on roles.

        Args:
            user_role_ids: List of role IDs the user has

        Returns:
            bool: True if user has at least one view role
        """
        if not self.view_roles:
            return True
        return bool(set(user_role_ids) & set(self.view_roles))
