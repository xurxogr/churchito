"""Modelo de resultado de purga por usuario."""

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from discord_bot.common.models import Base


class PurgaUserResult(Base):
    """Resultado de una purga para un usuario específico.

    Almacena los cambios de roles aplicados a cada usuario durante una purga.
    """

    __tablename__ = "purga_user_results"
    __table_args__ = (
        Index("ix_purga_user_purga_id", "purga_id"),
        Index("ix_purga_user_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    purga_id: Mapped[int] = mapped_column(
        ForeignKey("purga_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Tipo de acción: "cleaned" (purgado) o "promoted" (promocionado)
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Si fue promocionado, indica si tenía un rol afectado o no
    in_affected_group: Mapped[bool] = mapped_column(Boolean, nullable=True)

    # Roles antes y después de la purga
    roles_before: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    roles_after: Mapped[list[int]] = mapped_column(JSON, nullable=False)

    # Relación con PurgaRecord
    purga = relationship("PurgaRecord", back_populates="user_results")

    def __repr__(self) -> str:
        """Representación en cadena.

        Returns:
            str: Representación del registro.
        """
        return (
            f"<PurgaUserResult(id={self.id}, purga_id={self.purga_id}, "
            f"user_id={self.user_id}, action={self.action_type})>"
        )
