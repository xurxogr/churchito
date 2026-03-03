"""Convert header sections to text sections.

Revision ID: a1b2c3d4e5f6
Revises: e3500efa1ba3
Create Date: 2026-03-03 18:00:00.000000

Converts all embed sections with type 'header' to type 'text', moving
the content to the title field. This is needed because the HEADER
section type was removed in favor of using TEXT with a title field.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "e3500efa1ba3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keys that contain embed sections
SECTION_KEYS = [
    "player_info_sections",
    "mod_embed_regular",
    "mod_embed_ally",
]


def _convert_header_to_text(
    sections: list[dict[str, object]],
) -> tuple[list[dict[str, object]], bool]:
    """Convert header sections to text sections.

    Returns:
        Tuple of (converted_sections, was_modified)
    """
    modified = False
    result = []

    for section in sections:
        if not isinstance(section, dict):
            result.append(section)
            continue

        section_type = section.get("type", "")

        if section_type == "header":
            # Convert header to text: content becomes title
            new_section = {
                "type": "text",
                "title": section.get("content", ""),
                "content": "",
            }
            result.append(new_section)
            modified = True
        else:
            result.append(section)

    return result, modified


def _convert_text_to_header(
    sections: list[dict[str, object]],
) -> tuple[list[dict[str, object]], bool]:
    """Convert text sections back to header sections (for downgrade).

    Only converts TEXT sections that have a title but no content.

    Returns:
        Tuple of (converted_sections, was_modified)
    """
    modified = False
    result = []

    for section in sections:
        if not isinstance(section, dict):
            result.append(section)
            continue

        section_type = section.get("type", "")
        title = section.get("title", "")
        content = section.get("content", "")

        # Convert back to header if it's a text with only title (no content)
        if section_type == "text" and title and not content:
            new_section = {
                "type": "header",
                "content": title,
            }
            result.append(new_section)
            modified = True
        else:
            result.append(section)

    return result, modified


def upgrade() -> None:
    """Convert header sections to text sections."""
    conn = op.get_bind()
    now = datetime.now(UTC).isoformat()

    for key in SECTION_KEYS:
        # Get all configs with this key
        result = conn.execute(
            sa.text("""
                SELECT guild_id, cog_name, value
                FROM guild_configs
                WHERE key = :key
            """),
            {"key": key},
        )

        rows = list(result)

        for guild_id, cog_name, raw_value in rows:
            if not raw_value:
                continue

            try:
                data = json.loads(raw_value)
            except (json.JSONDecodeError, TypeError):
                continue

            # Handle EMBED type (has sections inside)
            if isinstance(data, dict) and "sections" in data:
                sections = data.get("sections", [])
                if isinstance(sections, list):
                    converted, modified = _convert_header_to_text(sections)
                    if modified:
                        data["sections"] = converted
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
                                "cog_name": cog_name,
                                "key": key,
                                "value": json.dumps(data),
                                "updated_at": now,
                            },
                        )

            # Handle EMBED_SECTIONS type (is a list directly)
            elif isinstance(data, list):
                converted, modified = _convert_header_to_text(data)
                if modified:
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
                            "cog_name": cog_name,
                            "key": key,
                            "value": json.dumps(converted),
                            "updated_at": now,
                        },
                    )


def downgrade() -> None:
    """Convert text sections back to header sections where applicable."""
    conn = op.get_bind()
    now = datetime.now(UTC).isoformat()

    for key in SECTION_KEYS:
        result = conn.execute(
            sa.text("""
                SELECT guild_id, cog_name, value
                FROM guild_configs
                WHERE key = :key
            """),
            {"key": key},
        )

        rows = list(result)

        for guild_id, cog_name, raw_value in rows:
            if not raw_value:
                continue

            try:
                data = json.loads(raw_value)
            except (json.JSONDecodeError, TypeError):
                continue

            # Handle EMBED type
            if isinstance(data, dict) and "sections" in data:
                sections = data.get("sections", [])
                if isinstance(sections, list):
                    converted, modified = _convert_text_to_header(sections)
                    if modified:
                        data["sections"] = converted
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
                                "cog_name": cog_name,
                                "key": key,
                                "value": json.dumps(data),
                                "updated_at": now,
                            },
                        )

            # Handle EMBED_SECTIONS type
            elif isinstance(data, list):
                converted, modified = _convert_text_to_header(data)
                if modified:
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
                            "cog_name": cog_name,
                            "key": key,
                            "value": json.dumps(converted),
                            "updated_at": now,
                        },
                    )
