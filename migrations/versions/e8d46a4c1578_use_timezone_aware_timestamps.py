"""Use timezone-aware timestamps.

Revision ID: e8d46a4c1578
Revises: 7d4d04118780
Create Date: 2026-02-15 21:20:17.201287

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import TIMESTAMP

# revision identifiers, used by Alembic.
revision: str = "e8d46a4c1578"
down_revision: str | Sequence[str] | None = "7d4d04118780"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Convert timestamp columns to timezone-aware
    op.alter_column(
        "guilds",
        "created_at",
        type_=TIMESTAMP(timezone=True),
    )
    op.alter_column(
        "guilds",
        "updated_at",
        type_=TIMESTAMP(timezone=True),
    )
    op.alter_column(
        "guild_configs",
        "updated_at",
        type_=TIMESTAMP(timezone=True),
    )
    op.alter_column(
        "verification_requests",
        "created_at",
        type_=TIMESTAMP(timezone=True),
    )
    op.alter_column(
        "verification_requests",
        "screenshots_submitted_at",
        type_=TIMESTAMP(timezone=True),
    )
    op.alter_column(
        "verification_requests",
        "reviewed_at",
        type_=TIMESTAMP(timezone=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Convert back to timezone-naive
    op.alter_column(
        "guilds",
        "created_at",
        type_=TIMESTAMP(timezone=False),
    )
    op.alter_column(
        "guilds",
        "updated_at",
        type_=TIMESTAMP(timezone=False),
    )
    op.alter_column(
        "guild_configs",
        "updated_at",
        type_=TIMESTAMP(timezone=False),
    )
    op.alter_column(
        "verification_requests",
        "created_at",
        type_=TIMESTAMP(timezone=False),
    )
    op.alter_column(
        "verification_requests",
        "screenshots_submitted_at",
        type_=TIMESTAMP(timezone=False),
    )
    op.alter_column(
        "verification_requests",
        "reviewed_at",
        type_=TIMESTAMP(timezone=False),
    )
