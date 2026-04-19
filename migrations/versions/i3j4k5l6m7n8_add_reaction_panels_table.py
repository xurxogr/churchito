"""Add reaction_panels table.

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-04-18 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "i3j4k5l6m7n8"
down_revision: str | Sequence[str] | None = "h2i3j4k5l6m7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "reaction_panels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=21), nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("panel_type", sa.String(length=20), nullable=False),
        sa.Column("role_mappings", sa.JSON(), nullable=False),
        sa.Column("required_roles", sa.JSON(), nullable=False),
        sa.Column("dm_on_missing_role", sa.Boolean(), nullable=False, default=False),
        sa.Column("dm_on_role_change", sa.Boolean(), nullable=False, default=False),
        sa.Column("exclusive_require_existing", sa.Boolean(), nullable=False, default=False),
        sa.Column("embed_config", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    with op.batch_alter_table("reaction_panels", schema=None) as batch_op:
        batch_op.create_index("ix_reaction_panel_guild_id", ["guild_id"], unique=False)
        batch_op.create_index(
            "ix_reaction_panel_message",
            ["guild_id", "channel_id", "message_id"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("reaction_panels", schema=None) as batch_op:
        batch_op.drop_index("ix_reaction_panel_message")
        batch_op.drop_index("ix_reaction_panel_guild_id")

    op.drop_table("reaction_panels")
