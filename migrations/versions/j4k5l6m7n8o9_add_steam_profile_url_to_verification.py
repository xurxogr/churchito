"""Add steam_profile_url field to verification_requests.

Revision ID: j4k5l6m7n8o9
Revises: a2324ea221e5
Create Date: 2026-07-21 00:00:00.000000

Stores the optional Steam profile URL submitted during verification so it
can be checked for public/private status.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j4k5l6m7n8o9"
down_revision: str | None = "a2324ea221e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add steam_profile_url column."""
    op.add_column(
        "verification_requests",
        sa.Column("steam_profile_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove steam_profile_url column."""
    op.drop_column("verification_requests", "steam_profile_url")
