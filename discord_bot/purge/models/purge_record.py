"""Purge record model."""

from datetime import UTC, datetime
from typing import Any

from nanoid import generate
from sqlalchemy import JSON, BigInteger, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from discord_bot.common.models import Base
from discord_bot.purge.enums import PurgeStatus


def _generate_public_id() -> str:
    """Generate a unique public ID using NanoID."""
    return str(generate(size=21))


class PurgeRecord(Base):
    """Purge record.

    Stores the history of performed purges, including status,
    authorizers, message IDs and results.
    """

    __tablename__ = "purge_records"
    __table_args__ = (
        Index("ix_purge_guild_id", "guild_id"),
        Index("ix_purge_status", "status"),
        Index("ix_purge_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        String(21), unique=True, nullable=False, default=_generate_public_id
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purge_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=PurgeStatus.PENDING)

    # User who initiated the purge
    initiated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Message IDs to be able to delete them if cancelled
    mod_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mod_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # List of user IDs who authorized
    authorized_by: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

    # List of user IDs who voted to cancel
    cancelled_by: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

    # List of user IDs who confirmed (reacted in user channel)
    confirmed_by: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

    # Configuration used in this purge (snapshot)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Execution results (summary)
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Per-user results
    user_results = relationship(
        "PurgeUserResult",
        back_populates="purge",
        cascade="all, delete-orphan",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    authorized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        """String representation.

        Returns:
            str: Record representation.
        """
        return (
            f"<PurgeRecord(id={self.id}, guild_id={self.guild_id}, "
            f"type={self.purge_type}, status={self.status})>"
        )
