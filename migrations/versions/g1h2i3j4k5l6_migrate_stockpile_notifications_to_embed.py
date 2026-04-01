"""Migrate stockpile notification config from TEXTAREA to EMBED.

Revision ID: g1h2i3j4k5l6
Revises: a5b6c7d8e9f0
Create Date: 2026-04-01 12:00:00.000000

Converts add_notification_text and delete_notification_text from string templates
to EMBED config format. Also migrates placeholder names:
- {creator} -> {creator_mention} (was mention, now display name by default)
- {roles} -> {roles_mention} (was mention, now names by default)
- {deleted_by} -> {deleted_by_mention} (was mention, now display name by default)
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g1h2i3j4k5l6"
down_revision: str | None = "a5b6c7d8e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COG_NAME = "stockpile"

# Keys to migrate
KEYS_TO_MIGRATE = ["add_notification_text", "delete_notification_text"]

# Old defaults (string format)
OLD_DEFAULTS = {
    "add_notification_text": "📦 **{name}** added at {hex} - {city} by {creator}",
    "delete_notification_text": "🗑️ **{name}** at {hex} - {city} deleted by {deleted_by}",
}

# New defaults (EMBED format)
NEW_DEFAULTS = {
    "add_notification_text": {
        "sections": [
            {
                "type": "text",
                "content": "📦 **{name}** added at {hex} - {city} by {creator_mention}",
            }
        ],
    },
    "delete_notification_text": {
        "sections": [
            {
                "type": "text",
                "content": "🗑️ **{name}** at {hex} - {city} deleted by {deleted_by_mention}",
            }
        ],
    },
}

# Placeholder migrations for custom templates
PLACEHOLDER_MIGRATIONS = {
    # In old templates, these were mentions. Now they're display names,
    # so we migrate to the _mention variant to preserve behavior
    "{creator}": "{creator_mention}",
    "{roles}": "{roles_mention}",
    "{deleted_by}": "{deleted_by_mention}",
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


def _migrate_placeholders(template: str) -> str:
    """Migrate old placeholder names to new ones."""
    result = template
    for old, new in PLACEHOLDER_MIGRATIONS.items():
        result = result.replace(old, new)
    return result


def _string_to_embed(template: str) -> dict[str, Any]:
    """Convert a string template to EMBED format."""
    migrated_template = _migrate_placeholders(template)
    return {
        "sections": [
            {
                "type": "text",
                "content": migrated_template,
            }
        ],
    }


def upgrade() -> None:
    """Migrate notification configs from TEXTAREA to EMBED format."""
    conn = op.get_bind()

    # Build IN clause for SQLite compatibility
    keys_placeholders = ", ".join(f":k{i}" for i in range(len(KEYS_TO_MIGRATE)))
    keys_params = {f"k{i}": key for i, key in enumerate(KEYS_TO_MIGRATE)}

    # Get all guilds that have any of the notification keys
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

        for row in result:
            key = row[0]
            old_value = _parse_json_value(row[1])

            if old_value is None:
                continue

            # Check if it's already in EMBED format (dict)
            try:
                parsed = json.loads(row[1])
                if isinstance(parsed, dict) and "sections" in parsed:
                    # Already migrated, skip
                    continue
            except (json.JSONDecodeError, TypeError):
                pass

            # Convert string template to EMBED format
            new_value = _string_to_embed(old_value)

            # Update the value
            conn.execute(
                sa.text("""
                    UPDATE guild_configs
                    SET value = :value, updated_at = :updated_at
                    WHERE guild_id = :guild_id
                    AND cog_name = :cog_name
                    AND key = :key
                """),
                {
                    "guild_id": guild_id,
                    "cog_name": COG_NAME,
                    "key": key,
                    "value": json.dumps(new_value),
                    "updated_at": now,
                },
            )


def downgrade() -> None:
    """Revert EMBED format back to TEXTAREA string format."""
    conn = op.get_bind()

    # Build IN clause for SQLite compatibility
    keys_placeholders = ", ".join(f":k{i}" for i in range(len(KEYS_TO_MIGRATE)))
    keys_params = {f"k{i}": key for i, key in enumerate(KEYS_TO_MIGRATE)}

    # Get all guilds that have any of the notification keys
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

    # Reverse placeholder migrations
    reverse_migrations = {v: k for k, v in PLACEHOLDER_MIGRATIONS.items()}

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

        for row in result:
            key = row[0]

            try:
                embed_config = json.loads(row[1])
            except (json.JSONDecodeError, TypeError):
                continue

            # Check if it's in EMBED format
            if not isinstance(embed_config, dict) or "sections" not in embed_config:
                # Not in embed format, skip
                continue

            # Extract text content from first TEXT section
            sections = embed_config.get("sections", [])
            template = OLD_DEFAULTS.get(key, "")

            for section in sections:
                if isinstance(section, dict) and section.get("type") == "text":
                    template = section.get("content", template)
                    break

            # Reverse placeholder migrations
            for new, old in reverse_migrations.items():
                template = template.replace(new, old)

            # Update back to string format
            conn.execute(
                sa.text("""
                    UPDATE guild_configs
                    SET value = :value, updated_at = :updated_at
                    WHERE guild_id = :guild_id
                    AND cog_name = :cog_name
                    AND key = :key
                """),
                {
                    "guild_id": guild_id,
                    "cog_name": COG_NAME,
                    "key": key,
                    "value": json.dumps(template),
                    "updated_at": now,
                },
            )
