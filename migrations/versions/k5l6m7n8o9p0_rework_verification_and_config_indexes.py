"""Rework verification_requests and config table indexes.

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-08-18 00:00:00.000000

verification_requests is looked up per guild by user (pending/latest/history)
and by status (pending list), so those get composite indexes; the lone
guild_id index becomes a redundant prefix and is dropped. guild_configs and
guild_cogs_enabled keep only their unique constraints, whose indexes already
cover the (guild_id) and (guild_id, cog_name) lookups.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "k5l6m7n8o9p0"
down_revision: str | None = "j4k5l6m7n8o9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add composite verification indexes and drop redundant single-column ones."""
    op.create_index("ix_verification_guild_user", "verification_requests", ["guild_id", "user_id"])
    op.create_index("ix_verification_guild_status", "verification_requests", ["guild_id", "status"])
    op.drop_index("ix_verification_guild_id", table_name="verification_requests")

    op.drop_index("ix_guild_config_guild_id", table_name="guild_configs")
    op.drop_index("ix_guild_config_cog_name", table_name="guild_configs")

    op.drop_index("ix_guild_cog_enabled_guild_id", table_name="guild_cogs_enabled")
    op.drop_index("ix_guild_cog_enabled_cog_name", table_name="guild_cogs_enabled")


def downgrade() -> None:
    """Restore the single-column indexes and drop the composites."""
    op.create_index("ix_guild_cog_enabled_cog_name", "guild_cogs_enabled", ["cog_name"])
    op.create_index("ix_guild_cog_enabled_guild_id", "guild_cogs_enabled", ["guild_id"])

    op.create_index("ix_guild_config_cog_name", "guild_configs", ["cog_name"])
    op.create_index("ix_guild_config_guild_id", "guild_configs", ["guild_id"])

    op.create_index("ix_verification_guild_id", "verification_requests", ["guild_id"])
    op.drop_index("ix_verification_guild_status", table_name="verification_requests")
    op.drop_index("ix_verification_guild_user", table_name="verification_requests")
