"""Tests for the index layout of the hot tables."""

from sqlalchemy import Table

from discord_bot.common.models import GuildCogEnabled, GuildConfig
from discord_bot.verification.models import VerificationRequest


def _indexes(table: Table) -> dict[str, tuple[str, ...]]:
    """Index name → column names for a table.

    Args:
        table (Table): SQLAlchemy table.

    Returns:
        dict[str, tuple[str, ...]]: Indexed columns by index name.
    """
    return {str(idx.name): tuple(col.name for col in idx.columns) for idx in table.indexes}


class TestVerificationRequestIndexes:
    """verification_requests is queried by (guild, user), (guild, status), user and status."""

    def test_composite_indexes_exist(self) -> None:
        """Composite indexes back the per-guild lookups."""
        indexes = _indexes(VerificationRequest.__table__)

        assert indexes["ix_verification_guild_user"] == ("guild_id", "user_id")
        assert indexes["ix_verification_guild_status"] == ("guild_id", "status")

    def test_single_column_guild_index_removed(self) -> None:
        """A lone guild_id index is a prefix of the composites and is gone."""
        assert "ix_verification_guild_id" not in _indexes(VerificationRequest.__table__)

    def test_global_lookups_keep_their_indexes(self) -> None:
        """user_id and status are still queried alone (timers, cross-guild pending)."""
        indexes = _indexes(VerificationRequest.__table__)

        assert indexes["ix_verification_user_id"] == ("user_id",)
        assert indexes["ix_verification_status"] == ("status",)


class TestGuildConfigIndexes:
    """The unique (guild_id, cog_name[, key]) constraints already cover the lookups."""

    def test_guild_configs_has_no_redundant_indexes(self) -> None:
        """No single-column indexes shadowed by uq_guild_cog_key."""
        assert _indexes(GuildConfig.__table__) == {}

    def test_guild_cog_enabled_has_no_redundant_indexes(self) -> None:
        """No single-column indexes shadowed by uq_guild_cog_enabled."""
        assert _indexes(GuildCogEnabled.__table__) == {}
