"""Convierte verification_automatic de boolean a enum.

Revision ID: e89b3f1774f4
Revises: e93ba4d9c838
Create Date: 2026-02-28 21:57:16.852050

Convierte el campo verification_automatic de boolean a enum string.
- true -> "both"
- false -> "none"
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e89b3f1774f4"
down_revision: str | Sequence[str] | None = "e93ba4d9c838"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convierte valores booleanos a enum strings."""
    conn = op.get_bind()

    # Convertir true -> "both"
    conn.execute(
        sa.text("""
            UPDATE guild_configs
            SET value = '"both"'
            WHERE cog_name = 'verification'
            AND key = 'verification_automatic'
            AND value = 'true'
        """)
    )

    # Convertir false -> "none"
    conn.execute(
        sa.text("""
            UPDATE guild_configs
            SET value = '"none"'
            WHERE cog_name = 'verification'
            AND key = 'verification_automatic'
            AND value = 'false'
        """)
    )


def downgrade() -> None:
    """Revierte enum strings a valores booleanos."""
    conn = op.get_bind()

    # Convertir "both" -> true
    conn.execute(
        sa.text("""
            UPDATE guild_configs
            SET value = 'true'
            WHERE cog_name = 'verification'
            AND key = 'verification_automatic'
            AND value = '"both"'
        """)
    )

    # Convertir "none", "reject_only", "approve_only" -> false
    conn.execute(
        sa.text("""
            UPDATE guild_configs
            SET value = 'false'
            WHERE cog_name = 'verification'
            AND key = 'verification_automatic'
            AND value IN ('"none"', '"reject_only"', '"approve_only"')
        """)
    )
