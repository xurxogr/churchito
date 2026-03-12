"""Add public_id field to verification_requests and purga_records.

Revision ID: b2c3d4e5f6g7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-11 12:00:00.000000

Adds NanoID-based public_id field to avoid exposing sequential internal IDs.
Existing records get public_id = str(id) for backwards compatibility with
existing Discord button custom_ids.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6g7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add public_id columns and populate existing records."""
    # 1. Add columns as nullable first
    op.add_column(
        "verification_requests",
        sa.Column("public_id", sa.String(21), nullable=True),
    )
    op.add_column(
        "purga_records",
        sa.Column("public_id", sa.String(21), nullable=True),
    )

    # 2. Populate existing records with str(id) for backwards compatibility
    connection = op.get_bind()
    connection.execute(text("UPDATE verification_requests SET public_id = CAST(id AS TEXT)"))
    connection.execute(text("UPDATE purga_records SET public_id = CAST(id AS TEXT)"))

    # 3. Make columns NOT NULL
    op.alter_column(
        "verification_requests",
        "public_id",
        nullable=False,
    )
    op.alter_column(
        "purga_records",
        "public_id",
        nullable=False,
    )

    # 4. Create unique constraints
    op.create_unique_constraint(
        "uq_verification_public_id",
        "verification_requests",
        ["public_id"],
    )
    op.create_unique_constraint(
        "uq_purga_public_id",
        "purga_records",
        ["public_id"],
    )


def downgrade() -> None:
    """Remove public_id columns."""
    op.drop_constraint("uq_purga_public_id", "purga_records", type_="unique")
    op.drop_constraint("uq_verification_public_id", "verification_requests", type_="unique")
    op.drop_column("purga_records", "public_id")
    op.drop_column("verification_requests", "public_id")
