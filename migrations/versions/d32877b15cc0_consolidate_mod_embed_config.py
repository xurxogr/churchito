"""Consolida las opciones de embed de moderación en ConfigOptionType.EMBED.

Revision ID: d32877b15cc0
Revises: fc6585a02a0f
Create Date: 2026-03-03 12:00:00.000000

Migra las opciones separadas de embed de moderación a la nueva estructura EMBED:
- mod_embed_color_regular -> mod_embed_regular.color
- mod_embed_icon_regular -> mod_embed_regular.thumbnail_url
- mod_embed_title_regular -> mod_embed_regular.title
- mod_embed_color_ally -> mod_embed_ally.color
- mod_embed_icon_ally -> mod_embed_ally.thumbnail_url
- mod_embed_title_ally -> mod_embed_ally.title
- mod_message_template -> mod_embed_regular.sections + mod_embed_ally.sections
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d32877b15cc0"
down_revision: str | Sequence[str] | None = "fc6585a02a0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Claves antiguas a migrar
OLD_KEYS = [
    "mod_embed_color_regular",
    "mod_embed_color_ally",
    "mod_embed_icon_regular",
    "mod_embed_icon_ally",
    "mod_embed_title_regular",
    "mod_embed_title_ally",
    "mod_message_template",
]

# Build IN clause for SQLite compatibility (doesn't support IN :tuple)
OLD_KEYS_PLACEHOLDERS = ", ".join(f":k{i}" for i in range(len(OLD_KEYS)))
OLD_KEYS_PARAMS = {f"k{i}": key for i, key in enumerate(OLD_KEYS)}

# Template por defecto (mismo que estaba en MOD_MESSAGE_TEMPLATE)
DEFAULT_TEMPLATE = (
    "**Usuario:** {user_mention} ({username})\n"
    "**Tipo:** {verification_type}\n"
    "**Fecha:** {created_at}\n\n"
    "{status}"
)


def _parse_json_value(value: str | None) -> str:
    """Parsea un valor JSON de la base de datos.

    Los valores en guild_configs están almacenados como JSON strings,
    por ejemplo: '"texto"' para strings, 'true' para booleans.
    """
    if value is None:
        return ""
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, str) else ""
    except (json.JSONDecodeError, TypeError):
        return ""


def _build_embed_config(
    color: str | None,
    icon: str | None,
    title: str | None,
    template: str | None,
) -> dict[str, Any]:
    """Construye la estructura del embed config."""
    # Usar template por defecto si no hay uno personalizado
    content = template if template else DEFAULT_TEMPLATE

    embed_config: dict[str, Any] = {
        "sections": [
            {
                "type": "text",
                "content": content,
            }
        ],
    }

    # Solo agregar campos si tienen valor
    if color:
        embed_config["color"] = color
    if icon:
        embed_config["thumbnail_url"] = icon
    if title:
        embed_config["title"] = title

    return embed_config


def upgrade() -> None:
    """Consolida las opciones de embed en la nueva estructura."""
    conn = op.get_bind()

    # Obtener todos los guilds que tienen alguna de las claves antiguas
    result = conn.execute(
        sa.text(f"""
            SELECT DISTINCT guild_id
            FROM guild_configs
            WHERE cog_name = 'verification'
            AND key IN ({OLD_KEYS_PLACEHOLDERS})
        """),
        OLD_KEYS_PARAMS,
    )
    guild_ids = [row[0] for row in result]

    for guild_id in guild_ids:
        # Obtener todas las configuraciones antiguas para este guild
        result = conn.execute(
            sa.text(f"""
                SELECT key, value
                FROM guild_configs
                WHERE guild_id = :guild_id
                AND cog_name = 'verification'
                AND key IN ({OLD_KEYS_PLACEHOLDERS})
            """),
            {"guild_id": guild_id, **OLD_KEYS_PARAMS},
        )

        old_values: dict[str, str] = {}
        for row in result:
            old_values[row[0]] = _parse_json_value(row[1])

        # Construir los nuevos embeds
        embed_regular = _build_embed_config(
            color=old_values.get("mod_embed_color_regular"),
            icon=old_values.get("mod_embed_icon_regular"),
            title=old_values.get("mod_embed_title_regular"),
            template=old_values.get("mod_message_template"),
        )

        embed_ally = _build_embed_config(
            color=old_values.get("mod_embed_color_ally"),
            icon=old_values.get("mod_embed_icon_ally"),
            title=old_values.get("mod_embed_title_ally"),
            template=old_values.get("mod_message_template"),
        )

        # Insertar los nuevos embeds
        now = datetime.now(UTC).isoformat()
        for key, embed_config in [
            ("mod_embed_regular", embed_regular),
            ("mod_embed_ally", embed_ally),
        ]:
            conn.execute(
                sa.text("""
                    INSERT INTO guild_configs (guild_id, cog_name, key, value, updated_at)
                    VALUES (:guild_id, 'verification', :key, :value, :updated_at)
                    ON CONFLICT (guild_id, cog_name, key)
                    DO UPDATE SET value = :value, updated_at = :updated_at
                """),
                {
                    "guild_id": guild_id,
                    "key": key,
                    "value": json.dumps(embed_config),
                    "updated_at": now,
                },
            )

    # Eliminar las claves antiguas
    conn.execute(
        sa.text(f"""
            DELETE FROM guild_configs
            WHERE cog_name = 'verification'
            AND key IN ({OLD_KEYS_PLACEHOLDERS})
        """),
        OLD_KEYS_PARAMS,
    )


def downgrade() -> None:
    """Revierte la consolidación extrayendo los valores a claves separadas."""
    conn = op.get_bind()

    # Obtener todos los guilds con los nuevos embeds
    result = conn.execute(
        sa.text("""
            SELECT DISTINCT guild_id
            FROM guild_configs
            WHERE cog_name = 'verification'
            AND key IN ('mod_embed_regular', 'mod_embed_ally')
        """)
    )
    guild_ids = [row[0] for row in result]

    for guild_id in guild_ids:
        # Obtener los embeds
        result = conn.execute(
            sa.text("""
                SELECT key, value
                FROM guild_configs
                WHERE guild_id = :guild_id
                AND cog_name = 'verification'
                AND key IN ('mod_embed_regular', 'mod_embed_ally')
            """),
            {"guild_id": guild_id},
        )

        embeds: dict[str, dict[str, Any]] = {}
        for row in result:
            try:
                embeds[row[0]] = json.loads(row[1])
            except (json.JSONDecodeError, TypeError):
                embeds[row[0]] = {}

        # Extraer valores del embed regular
        embed_regular = embeds.get("mod_embed_regular", {})
        embed_ally = embeds.get("mod_embed_ally", {})

        # Reconstruir las claves antiguas
        old_configs = [
            ("mod_embed_color_regular", embed_regular.get("color", "")),
            ("mod_embed_icon_regular", embed_regular.get("thumbnail_url", "")),
            ("mod_embed_title_regular", embed_regular.get("title", "")),
            ("mod_embed_color_ally", embed_ally.get("color", "")),
            ("mod_embed_icon_ally", embed_ally.get("thumbnail_url", "")),
            ("mod_embed_title_ally", embed_ally.get("title", "")),
        ]

        # Extraer el template del primer TEXT section del embed regular
        template = DEFAULT_TEMPLATE
        sections = embed_regular.get("sections", [])
        if sections and isinstance(sections, list):
            for section in sections:
                if isinstance(section, dict) and section.get("type") == "text":
                    template = section.get("content", DEFAULT_TEMPLATE)
                    break

        old_configs.append(("mod_message_template", template))

        # Insertar las claves antiguas
        now = datetime.now(UTC).isoformat()
        for key, value in old_configs:
            conn.execute(
                sa.text("""
                    INSERT INTO guild_configs (guild_id, cog_name, key, value, updated_at)
                    VALUES (:guild_id, 'verification', :key, :value, :updated_at)
                    ON CONFLICT (guild_id, cog_name, key)
                    DO UPDATE SET value = :value, updated_at = :updated_at
                """),
                {
                    "guild_id": guild_id,
                    "key": key,
                    "value": json.dumps(value),
                    "updated_at": now,
                },
            )

    # Eliminar los nuevos embeds
    conn.execute(
        sa.text("""
            DELETE FROM guild_configs
            WHERE cog_name = 'verification'
            AND key IN ('mod_embed_regular', 'mod_embed_ally')
        """)
    )
