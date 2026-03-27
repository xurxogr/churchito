"""Add stockpiles table.

Revision ID: a5b6c7d8e9f0
Revises: cf032f502400
Create Date: 2026-03-27 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a5b6c7d8e9f0"
down_revision: str | Sequence[str] | None = "cf032f502400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "stockpiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=21), nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("hex_key", sa.String(length=50), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=10), nullable=False),
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("view_roles", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint(
            "guild_id", "hex_key", "city", "name", name="uq_stockpile_location_name"
        ),
    )
    with op.batch_alter_table("stockpiles", schema=None) as batch_op:
        batch_op.create_index("ix_stockpile_guild_id", ["guild_id"], unique=False)
        batch_op.create_index(
            "ix_stockpile_hex_city", ["guild_id", "hex_key", "city"], unique=False
        )
        batch_op.create_index(
            "ix_stockpile_location_name",
            ["guild_id", "hex_key", "city", "name"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("stockpiles", schema=None) as batch_op:
        batch_op.drop_index("ix_stockpile_location_name")
        batch_op.drop_index("ix_stockpile_hex_city")
        batch_op.drop_index("ix_stockpile_guild_id")

    op.drop_table("stockpiles")
