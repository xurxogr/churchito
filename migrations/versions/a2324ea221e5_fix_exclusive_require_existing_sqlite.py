"""Fix exclusive_require_existing SQLite compatibility.

This migration replaces j4k5l6m7n8o9 which had SQLite batch mode issues.
It adds the exclusive_require_existing column using raw SQL.

Revision ID: a2324ea221e5
Revises: i3j4k5l6m7n8
Create Date: 2026-04-20 15:09:59.690257
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2324ea221e5"
down_revision: str | Sequence[str] | None = "i3j4k5l6m7n8"  # Skip broken migration
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add exclusive_require_existing column using raw SQL for SQLite compatibility."""
    # Check if column already exists (in case broken migration partially succeeded)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("reaction_panels")]

    if "exclusive_require_existing" not in columns:
        # Use raw SQL to add column - avoids SQLite batch mode issues
        op.execute(
            sa.text(
                "ALTER TABLE reaction_panels "
                "ADD COLUMN exclusive_require_existing BOOLEAN NOT NULL DEFAULT 0"
            )
        )


def downgrade() -> None:
    """Remove exclusive_require_existing column."""
    with op.batch_alter_table("reaction_panels", schema=None) as batch_op:
        batch_op.drop_column("exclusive_require_existing")
