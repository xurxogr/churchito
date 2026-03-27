"""add_guild_language.

Revision ID: cf032f502400
Revises: c42443ef0dd0
Create Date: 2026-03-12 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cf032f502400"
down_revision: str | Sequence[str] | None = "c42443ef0dd0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add language column to guilds table."""
    with op.batch_alter_table("guilds", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("language", sa.String(5), server_default="en", nullable=False)
        )


def downgrade() -> None:
    """Remove language column from guilds table."""
    with op.batch_alter_table("guilds", schema=None) as batch_op:
        batch_op.drop_column("language")
