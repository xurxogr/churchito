"""Migrate player_info_template to player_info_sections.

Revision ID: e3500efa1ba3
Revises: d32877b15cc0
Create Date: 2026-03-03 14:00:00.000000

Convierte el valor de texto del template antiguo a una sección de tipo 'text'
en el nuevo formato de secciones.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3500efa1ba3"
down_revision: str | Sequence[str] | None = "d32877b15cc0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KEY = "player_info_template"
NEW_KEY = "player_info_sections"

# Default sections config (same as in verification/config.py)
DEFAULT_SECTIONS: list[dict[str, object]] = [
    {
        "type": "header",
        "content": "Información del jugador",
    },
    {
        "type": "fields",
        "inline": True,
        "field_1_name": "Nombre",
        "field_1_value": "{name}",
        "field_2_name": "Regimiento",
        "field_2_value": "{regiment}",
        "field_3_name": "Nivel",
        "field_3_value": "{level}",
    },
    {
        "type": "fields",
        "inline": True,
        "field_1_name": "Facción",
        "field_1_value": "{faction}",
        "field_2_name": "Shard",
        "field_2_value": "{shard}",
        "field_3_name": "Tiempo de juego",
        "field_3_value": "{time}",
    },
    {
        "type": "fields",
        "inline": True,
        "field_1_name": "Guerra",
        "field_1_value": "{war}",
        "field_2_name": "Tiempo actual",
        "field_2_value": "{war_time}",
        "field_3_name": "",
        "field_3_value": "",
    },
]

# Default template (to detect if user customized it)
DEFAULT_TEMPLATE = (
    "**Información del jugador:**\n"
    "Nombre: {name}\n"
    "Regimiento: {regiment}\n"
    "Nivel: {level}\n"
    "Facción: {faction}\n"
    "Shard: {shard}\n"
    "Tiempo de juego: {time}\n"
    "Guerra: {war}\n"
    "Tiempo actual: {war_time}"
)


def _parse_json_value(value: str | None) -> str:
    """Parse a JSON string value from the database."""
    if value is None:
        return ""
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, str) else ""
    except (json.JSONDecodeError, TypeError):
        return ""


def upgrade() -> None:
    """Convert player_info_template to player_info_sections."""
    conn = op.get_bind()

    # Get all guilds with the old key
    result = conn.execute(
        sa.text("""
            SELECT guild_id, value
            FROM guild_configs
            WHERE cog_name = 'verification'
            AND key = :old_key
        """),
        {"old_key": OLD_KEY},
    )

    rows = list(result)
    now = datetime.now(UTC).isoformat()

    for guild_id, raw_value in rows:
        template_value = _parse_json_value(raw_value)

        # Determine the sections to use
        sections: list[dict[str, object]]
        if template_value and template_value != DEFAULT_TEMPLATE:
            # User customized the template - convert to a single text section
            sections = [
                {
                    "type": "text",
                    "content": template_value,
                }
            ]
        else:
            # Using default or empty - use the new default sections
            sections = DEFAULT_SECTIONS

        # Insert the new sections config
        conn.execute(
            sa.text("""
                INSERT INTO guild_configs (guild_id, cog_name, key, value, updated_at)
                VALUES (:guild_id, 'verification', :key, :value, :updated_at)
                ON CONFLICT (guild_id, cog_name, key)
                DO UPDATE SET value = :value, updated_at = :updated_at
            """),
            {
                "guild_id": guild_id,
                "key": NEW_KEY,
                "value": json.dumps(sections),
                "updated_at": now,
            },
        )

    # Delete all old template entries
    conn.execute(
        sa.text("""
            DELETE FROM guild_configs
            WHERE cog_name = 'verification'
            AND key = :old_key
        """),
        {"old_key": OLD_KEY},
    )


def downgrade() -> None:
    """Revert player_info_sections back to player_info_template."""
    conn = op.get_bind()

    # Get all guilds with the new key
    result = conn.execute(
        sa.text("""
            SELECT guild_id, value
            FROM guild_configs
            WHERE cog_name = 'verification'
            AND key = :new_key
        """),
        {"new_key": NEW_KEY},
    )

    rows = list(result)
    now = datetime.now(UTC).isoformat()

    for guild_id, raw_value in rows:
        try:
            sections = json.loads(raw_value) if raw_value else []
        except (json.JSONDecodeError, TypeError):
            sections = []

        # Try to extract text content from sections
        template_content = ""
        for section in sections:
            if isinstance(section, dict):
                section_type = section.get("type", "")
                if section_type in ("text", "header"):
                    content = section.get("content", "")
                    if section_type == "header":
                        template_content += f"**{content}**\n"
                    else:
                        template_content += content + "\n"

        # If we couldn't extract anything, use default
        if not template_content.strip():
            template_content = DEFAULT_TEMPLATE

        # Insert the old template config
        conn.execute(
            sa.text("""
                INSERT INTO guild_configs (guild_id, cog_name, key, value, updated_at)
                VALUES (:guild_id, 'verification', :key, :value, :updated_at)
                ON CONFLICT (guild_id, cog_name, key)
                DO UPDATE SET value = :value, updated_at = :updated_at
            """),
            {
                "guild_id": guild_id,
                "key": OLD_KEY,
                "value": json.dumps(template_content.strip()),
                "updated_at": now,
            },
        )

    # Delete all new sections entries
    conn.execute(
        sa.text("""
            DELETE FROM guild_configs
            WHERE cog_name = 'verification'
            AND key = :new_key
        """),
        {"new_key": NEW_KEY},
    )
