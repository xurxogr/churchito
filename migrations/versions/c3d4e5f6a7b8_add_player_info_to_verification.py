"""Add player_info JSON field to verification_requests.

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-03-04 12:00:00.000000

Stores OCR-extracted player information (name, regiment, level, faction, shard, etc.)
so it can be preserved when rebuilding embeds after config changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add player_info column."""
    op.add_column(
        "verification_requests",
        sa.Column("player_info", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Remove player_info column."""
    op.drop_column("verification_requests", "player_info")
