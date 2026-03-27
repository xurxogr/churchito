"""Purge user result model."""

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from discord_bot.common.models import Base


class PurgeUserResult(Base):
    """Purge result for a specific user.

    Stores the role changes applied to each user during a purge.
    """

    __tablename__ = "purge_user_results"
    __table_args__ = (
        Index("ix_purge_user_purge_id", "purge_id"),
        Index("ix_purge_user_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    purge_id: Mapped[int] = mapped_column(
        ForeignKey("purge_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Action type: "cleaned" (purged) or "promoted"
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # If promoted, indicates whether had an affected role or not
    in_affected_group: Mapped[bool] = mapped_column(Boolean, nullable=True)

    # Roles before and after purge
    roles_before: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    roles_after: Mapped[list[int]] = mapped_column(JSON, nullable=False)

    # Relationship with PurgeRecord
    purge = relationship("PurgeRecord", back_populates="user_results")

    def __repr__(self) -> str:
        """String representation.

        Returns:
            str: Record representation.
        """
        return (
            f"<PurgeUserResult(id={self.id}, purge_id={self.purge_id}, "
            f"user_id={self.user_id}, action={self.action_type})>"
        )
