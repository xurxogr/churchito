"""Add cancelled_by to purga_records.

Revision ID: e3bbb18b1809
Revises: 0466b869c689
Create Date: 2026-02-17 18:14:54.047542
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3bbb18b1809"
down_revision: str | Sequence[str] | None = "0466b869c689"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("purga_records", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("cancelled_by", sa.JSON(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("purga_records", schema=None) as batch_op:
        batch_op.drop_column("cancelled_by")
