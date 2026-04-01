"""Migrate stockpile show config from STRING/TEXTAREA to EMBED.

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-04-01 14:00:00.000000

Converts show_item_text to show_location_embed (description only),
and show_empty_text to show_empty_embed.
Note: show_header_text is kept as-is (now a separate config option).
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h2i3j4k5l6m7"
down_revision: str | None = "g1h2i3j4k5l6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COG_NAME = "stockpile"

# Keys to migrate (NOT including show_header_text - it stays as-is)
OLD_KEYS_TO_MIGRATE = ["show_item_text", "show_empty_text"]

# New keys
NEW_LOCATION_KEY = "show_location_embed"
NEW_EMPTY_KEY = "show_empty_embed"

# Old defaults
OLD_DEFAULTS = {
    "show_item_text": "**{name}**: `{code}` (by {creator_mention})",
    "show_empty_text": "No stockpiles found at **{hex}** - **{city}**",
}

# New defaults
NEW_DEFAULTS = {
    NEW_LOCATION_KEY: {
        "description": "**{name}**: `{code}` (by {creator_mention})",
    },
    NEW_EMPTY_KEY: {
        "title": "No stockpiles found",
        "description": "No stockpiles found at **{hex}** - **{city}**",
    },
}


def _parse_json_value(value: str | None) -> str | None:
    """Parse a JSON string value from the database."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, str) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _build_location_embed(item_template: str) -> dict[str, Any]:
    """Build location embed config from item template (description only)."""
    return {
        "description": item_template,
    }


def _build_empty_embed(empty_text: str) -> dict[str, Any]:
    """Build empty embed config from empty text."""
    return {
        "title": "No stockpiles found",
        "description": empty_text,
    }


def upgrade() -> None:
    """Migrate show configs from STRING/TEXTAREA to EMBED format."""
    conn = op.get_bind()

    # Build IN clause for SQLite compatibility
    keys_placeholders = ", ".join(f":k{i}" for i in range(len(OLD_KEYS_TO_MIGRATE)))
    keys_params = {f"k{i}": key for i, key in enumerate(OLD_KEYS_TO_MIGRATE)}

    # Get all guilds that have any of the old keys to migrate
    result = conn.execute(
        sa.text(f"""
            SELECT DISTINCT guild_id
            FROM guild_configs
            WHERE cog_name = :cog_name
            AND key IN ({keys_placeholders})
        """),
        {"cog_name": COG_NAME, **keys_params},
    )
    guild_ids = [row[0] for row in result]

    now = datetime.now(UTC).isoformat()

    for guild_id in guild_ids:
        # Get existing values for this guild
        result = conn.execute(
            sa.text(f"""
                SELECT key, value
                FROM guild_configs
                WHERE guild_id = :guild_id
                AND cog_name = :cog_name
                AND key IN ({keys_placeholders})
            """),
            {"guild_id": guild_id, "cog_name": COG_NAME, **keys_params},
        )

        values: dict[str, str | None] = {}
        for row in result:
            values[row[0]] = _parse_json_value(row[1])

        # Get item and empty values (use defaults if not set)
        item_template = values.get("show_item_text") or OLD_DEFAULTS["show_item_text"]
        empty_text = values.get("show_empty_text") or OLD_DEFAULTS["show_empty_text"]

        # Build new embed configs
        location_embed = _build_location_embed(item_template)
        empty_embed = _build_empty_embed(empty_text)

        # Check if new keys already exist
        existing = conn.execute(
            sa.text("""
                SELECT key FROM guild_configs
                WHERE guild_id = :guild_id
                AND cog_name = :cog_name
                AND key IN (:k1, :k2)
            """),
            {
                "guild_id": guild_id,
                "cog_name": COG_NAME,
                "k1": NEW_LOCATION_KEY,
                "k2": NEW_EMPTY_KEY,
            },
        )
        existing_keys = {row[0] for row in existing}

        # Insert location embed if not exists
        if NEW_LOCATION_KEY not in existing_keys:
            conn.execute(
                sa.text("""
                    INSERT INTO guild_configs (guild_id, cog_name, key, value, updated_at)
                    VALUES (:guild_id, :cog_name, :key, :value, :updated_at)
                """),
                {
                    "guild_id": guild_id,
                    "cog_name": COG_NAME,
                    "key": NEW_LOCATION_KEY,
                    "value": json.dumps(location_embed),
                    "updated_at": now,
                },
            )

        # Insert empty embed if not exists
        if NEW_EMPTY_KEY not in existing_keys:
            conn.execute(
                sa.text("""
                    INSERT INTO guild_configs (guild_id, cog_name, key, value, updated_at)
                    VALUES (:guild_id, :cog_name, :key, :value, :updated_at)
                """),
                {
                    "guild_id": guild_id,
                    "cog_name": COG_NAME,
                    "key": NEW_EMPTY_KEY,
                    "value": json.dumps(empty_embed),
                    "updated_at": now,
                },
            )

        # Delete old keys (only the ones we migrated, NOT show_header_text)
        conn.execute(
            sa.text(f"""
                DELETE FROM guild_configs
                WHERE guild_id = :guild_id
                AND cog_name = :cog_name
                AND key IN ({keys_placeholders})
            """),
            {"guild_id": guild_id, "cog_name": COG_NAME, **keys_params},
        )


def downgrade() -> None:
    """Revert EMBED format back to STRING/TEXTAREA format."""
    conn = op.get_bind()

    # Get all guilds that have the new keys
    result = conn.execute(
        sa.text("""
            SELECT DISTINCT guild_id
            FROM guild_configs
            WHERE cog_name = :cog_name
            AND key IN (:k1, :k2)
        """),
        {"cog_name": COG_NAME, "k1": NEW_LOCATION_KEY, "k2": NEW_EMPTY_KEY},
    )
    guild_ids = [row[0] for row in result]

    now = datetime.now(UTC).isoformat()

    for guild_id in guild_ids:
        # Get existing embed configs
        result = conn.execute(
            sa.text("""
                SELECT key, value
                FROM guild_configs
                WHERE guild_id = :guild_id
                AND cog_name = :cog_name
                AND key IN (:k1, :k2)
            """),
            {
                "guild_id": guild_id,
                "cog_name": COG_NAME,
                "k1": NEW_LOCATION_KEY,
                "k2": NEW_EMPTY_KEY,
            },
        )

        location_embed = None
        empty_embed = None
        for row in result:
            try:
                value = json.loads(row[1])
                if row[0] == NEW_LOCATION_KEY:
                    location_embed = value
                elif row[0] == NEW_EMPTY_KEY:
                    empty_embed = value
            except (json.JSONDecodeError, TypeError):
                pass

        # Extract old values from embeds
        item_template = OLD_DEFAULTS["show_item_text"]
        empty_text = OLD_DEFAULTS["show_empty_text"]

        if location_embed:
            # Description is now directly in the embed
            item_template = location_embed.get("description", item_template)

        if empty_embed:
            empty_text = empty_embed.get("description", empty_text)

        # Insert old keys (only the ones we migrated)
        for key, value in [
            ("show_item_text", item_template),
            ("show_empty_text", empty_text),
        ]:
            conn.execute(
                sa.text("""
                    INSERT INTO guild_configs (guild_id, cog_name, key, value, updated_at)
                    VALUES (:guild_id, :cog_name, :key, :value, :updated_at)
                """),
                {
                    "guild_id": guild_id,
                    "cog_name": COG_NAME,
                    "key": key,
                    "value": json.dumps(value),
                    "updated_at": now,
                },
            )

        # Delete new keys
        conn.execute(
            sa.text("""
                DELETE FROM guild_configs
                WHERE guild_id = :guild_id
                AND cog_name = :cog_name
                AND key IN (:k1, :k2)
            """),
            {
                "guild_id": guild_id,
                "cog_name": COG_NAME,
                "k1": NEW_LOCATION_KEY,
                "k2": NEW_EMPTY_KEY,
            },
        )
