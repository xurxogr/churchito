"""Migrate block_already_verified to blocking_roles.

Revision ID: f1a2b3c4d5e6
Revises: c3d4e5f6a7b8
Create Date: 2026-03-04 18:00:00.000000

Replaces the boolean option block_already_verified with a role list blocking_roles.
For guilds where block_already_verified was true (or not set, since default was true),
the roles from regular_roles_add and ally_roles_add are combined and stored in blocking_roles.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _parse_json_value(value: str | None, default: Any = None) -> Any:
    """Parse a JSON value from the database."""
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def upgrade() -> None:
    """Migrate block_already_verified to blocking_roles."""
    conn = op.get_bind()

    # Get all guilds that have verification config
    result = conn.execute(
        sa.text("""
            SELECT DISTINCT guild_id
            FROM guild_configs
            WHERE cog_name = 'verification'
            AND key IN ('block_already_verified', 'regular_roles_add', 'ally_roles_add')
        """)
    )
    guild_ids = [row[0] for row in result]

    now = datetime.now(UTC).isoformat()

    for guild_id in guild_ids:
        # Get the relevant config values for this guild
        result = conn.execute(
            sa.text("""
                SELECT key, value
                FROM guild_configs
                WHERE guild_id = :guild_id
                AND cog_name = 'verification'
                AND key IN ('block_already_verified', 'regular_roles_add', 'ally_roles_add')
            """),
            {"guild_id": guild_id},
        )

        values: dict[str, str | None] = {}
        for row in result:
            values[row[0]] = row[1]

        # Check if block_already_verified was true (default was true)
        block_verified = _parse_json_value(values.get("block_already_verified"), default=True)

        if block_verified:
            # Combine regular_roles_add and ally_roles_add
            regular_roles = _parse_json_value(values.get("regular_roles_add"), default=[])
            ally_roles = _parse_json_value(values.get("ally_roles_add"), default=[])

            # Ensure they are lists
            if not isinstance(regular_roles, list):
                regular_roles = []
            if not isinstance(ally_roles, list):
                ally_roles = []

            # Combine and deduplicate
            blocking_roles = list(set(regular_roles) | set(ally_roles))

            # Only insert if there are roles to block
            if blocking_roles:
                conn.execute(
                    sa.text("""
                        INSERT INTO guild_configs (guild_id, cog_name, key, value, updated_at)
                        VALUES (:guild_id, 'verification', 'blocking_roles', :value, :updated_at)
                        ON CONFLICT (guild_id, cog_name, key)
                        DO UPDATE SET value = :value, updated_at = :updated_at
                    """),
                    {
                        "guild_id": guild_id,
                        "value": json.dumps(blocking_roles),
                        "updated_at": now,
                    },
                )

    # Delete the old block_already_verified key
    conn.execute(
        sa.text("""
            DELETE FROM guild_configs
            WHERE cog_name = 'verification'
            AND key = 'block_already_verified'
        """)
    )


def downgrade() -> None:
    """Revert to block_already_verified boolean."""
    conn = op.get_bind()

    # Get all guilds that have blocking_roles
    result = conn.execute(
        sa.text("""
            SELECT DISTINCT guild_id
            FROM guild_configs
            WHERE cog_name = 'verification'
            AND key = 'blocking_roles'
        """)
    )
    guild_ids = [row[0] for row in result]

    now = datetime.now(UTC).isoformat()

    for guild_id in guild_ids:
        # Get blocking_roles value
        result = conn.execute(
            sa.text("""
                SELECT value
                FROM guild_configs
                WHERE guild_id = :guild_id
                AND cog_name = 'verification'
                AND key = 'blocking_roles'
            """),
            {"guild_id": guild_id},
        )

        row = result.fetchone()
        blocking_roles = _parse_json_value(row[0] if row else None, default=[])

        # If there were blocking roles, set block_already_verified to true
        if blocking_roles:
            conn.execute(
                sa.text("""
                    INSERT INTO guild_configs
                        (guild_id, cog_name, key, value, updated_at)
                    VALUES
                        (:guild_id, 'verification', 'block_already_verified',
                         :value, :updated_at)
                    ON CONFLICT (guild_id, cog_name, key)
                    DO UPDATE SET value = :value, updated_at = :updated_at
                """),
                {
                    "guild_id": guild_id,
                    "value": json.dumps(True),
                    "updated_at": now,
                },
            )

    # Delete the blocking_roles key
    conn.execute(
        sa.text("""
            DELETE FROM guild_configs
            WHERE cog_name = 'verification'
            AND key = 'blocking_roles'
        """)
    )
