"""Convierte verification_match_name de boolean a enum.

Revision ID: fc6585a02a0f
Revises: e89b3f1774f4
Create Date: 2026-02-28 22:08:41.039956

Convierte el campo verification_match_name de boolean a enum string.
- true -> "exact"
- false -> "none"
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fc6585a02a0f"
down_revision: str | Sequence[str] | None = "e89b3f1774f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convierte valores booleanos a enum strings."""
    conn = op.get_bind()

    # Convertir true -> "exact"
    conn.execute(
        sa.text("""
            UPDATE guild_configs
            SET value = '"exact"'
            WHERE cog_name = 'verification'
            AND key = 'verification_match_name'
            AND value = 'true'
        """)
    )

    # Convertir false -> "none"
    conn.execute(
        sa.text("""
            UPDATE guild_configs
            SET value = '"none"'
            WHERE cog_name = 'verification'
            AND key = 'verification_match_name'
            AND value = 'false'
        """)
    )


def downgrade() -> None:
    """Revierte enum strings a valores booleanos."""
    conn = op.get_bind()

    # Convertir "exact" -> true
    conn.execute(
        sa.text("""
            UPDATE guild_configs
            SET value = 'true'
            WHERE cog_name = 'verification'
            AND key = 'verification_match_name'
            AND value = '"exact"'
        """)
    )

    # Convertir "none", "contains" -> false
    conn.execute(
        sa.text("""
            UPDATE guild_configs
            SET value = 'false'
            WHERE cog_name = 'verification'
            AND key = 'verification_match_name'
            AND value IN ('"none"', '"contains"')
        """)
    )
