"""rename_purga_to_purge_tables.

Revision ID: c42443ef0dd0
Revises: b2c3d4e5f6g7
Create Date: 2026-03-12 15:38:44.468021

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "c42443ef0dd0"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6g7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename purga tables and columns to purge."""
    # Rename purga_records table to purge_records
    op.rename_table("purga_records", "purge_records")

    # Drop old indexes first (outside batch to avoid conflicts)
    op.drop_index("ix_purga_created_at", table_name="purge_records")
    op.drop_index("ix_purga_guild_id", table_name="purge_records")
    op.drop_index("ix_purga_status", table_name="purge_records")

    # Rename column and constraint on purge_records
    with op.batch_alter_table("purge_records", recreate="always") as batch_op:
        batch_op.alter_column("purga_type", new_column_name="purge_type")
        batch_op.drop_constraint("uq_purga_public_id", type_="unique")
        batch_op.create_unique_constraint("uq_purge_public_id", ["public_id"])

    # Create new indexes after batch
    op.create_index("ix_purge_created_at", "purge_records", ["created_at"])
    op.create_index("ix_purge_guild_id", "purge_records", ["guild_id"])
    op.create_index("ix_purge_status", "purge_records", ["status"])

    # Rename purga_user_results table to purge_user_results
    op.rename_table("purga_user_results", "purge_user_results")

    # Drop old indexes first
    op.drop_index("ix_purga_user_purga_id", table_name="purge_user_results")
    op.drop_index("ix_purga_user_user_id", table_name="purge_user_results")

    # Rename column on purge_user_results
    with op.batch_alter_table("purge_user_results", recreate="always") as batch_op:
        batch_op.alter_column("purga_id", new_column_name="purge_id")

    # Create new indexes after batch
    op.create_index("ix_purge_user_purge_id", "purge_user_results", ["purge_id"])
    op.create_index("ix_purge_user_user_id", "purge_user_results", ["user_id"])

    # Update cog_name in guild_configs from 'purga' to 'purge'
    connection = op.get_bind()
    connection.execute(text("UPDATE guild_configs SET cog_name = 'purge' WHERE cog_name = 'purga'"))
    connection.execute(
        text("UPDATE guild_cogs_enabled SET cog_name = 'purge' WHERE cog_name = 'purga'")
    )


def downgrade() -> None:
    """Revert purge tables and columns back to purga."""
    # Revert cog_name in guild_configs from 'purge' to 'purga'
    connection = op.get_bind()
    connection.execute(text("UPDATE guild_configs SET cog_name = 'purga' WHERE cog_name = 'purge'"))
    connection.execute(
        text("UPDATE guild_cogs_enabled SET cog_name = 'purga' WHERE cog_name = 'purge'")
    )

    # Drop new indexes first
    op.drop_index("ix_purge_user_user_id", table_name="purge_user_results")
    op.drop_index("ix_purge_user_purge_id", table_name="purge_user_results")

    # Rename column on purge_user_results back
    with op.batch_alter_table("purge_user_results", recreate="always") as batch_op:
        batch_op.alter_column("purge_id", new_column_name="purga_id")

    # Rename purge_user_results back to purga_user_results
    op.rename_table("purge_user_results", "purga_user_results")

    # Create old indexes after rename
    op.create_index("ix_purga_user_purga_id", "purga_user_results", ["purga_id"])
    op.create_index("ix_purga_user_user_id", "purga_user_results", ["user_id"])

    # Drop new indexes first
    op.drop_index("ix_purge_status", table_name="purge_records")
    op.drop_index("ix_purge_guild_id", table_name="purge_records")
    op.drop_index("ix_purge_created_at", table_name="purge_records")

    # Rename column and constraint on purge_records back
    with op.batch_alter_table("purge_records", recreate="always") as batch_op:
        batch_op.alter_column("purge_type", new_column_name="purga_type")
        batch_op.drop_constraint("uq_purge_public_id", type_="unique")
        batch_op.create_unique_constraint("uq_purga_public_id", ["public_id"])

    # Rename purge_records back to purga_records
    op.rename_table("purge_records", "purga_records")

    # Create old indexes after rename
    op.create_index("ix_purga_created_at", "purga_records", ["created_at"])
    op.create_index("ix_purga_guild_id", "purga_records", ["guild_id"])
    op.create_index("ix_purga_status", "purga_records", ["status"])
