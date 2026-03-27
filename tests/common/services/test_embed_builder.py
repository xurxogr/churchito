"""Tests for the embed builder service."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import discord
import pytest

from discord_bot.common.enums.embed_section_type import EmbedSectionType
from discord_bot.common.schemas.embed_section import EmbedConfig, EmbedSection
from discord_bot.common.services.embed_builder import (
    ANSI_COLORS,
    COLOR_TAGS,
    DOT_EMOJIS,
    GLOBAL_PLACEHOLDERS,
    EmbedFieldLimitError,
    PlaceholderContext,
    build_embed,
    build_embed_from_rows,
    create_progress_bar,
    format_placeholders,
    format_with_colors,
)


class TestCreateProgressBar:
    """Tests for create_progress_bar."""

    def test_empty_bar(self) -> None:
        """Test empty bar when value is 0."""
        bar = create_progress_bar(0, 100)
        assert bar == "░░░░░░░░░░"

    def test_full_bar(self) -> None:
        """Test full bar when value is maximum."""
        bar = create_progress_bar(100, 100)
        assert bar == "██████████"

    def test_half_bar(self) -> None:
        """Test bar at 50%."""
        bar = create_progress_bar(50, 100)
        assert bar == "█████░░░░░"

    def test_custom_length(self) -> None:
        """Test bar with custom length."""
        bar = create_progress_bar(50, 100, length=20)
        assert len(bar) == 20
        assert bar.count("█") == 10

    def test_custom_characters(self) -> None:
        """Test bar with custom characters."""
        bar = create_progress_bar(30, 100, filled_char="▓", empty_char="▒")
        assert "▓" in bar
        assert "▒" in bar

    def test_max_value_zero(self) -> None:
        """Test with max value 0 returns empty bar."""
        bar = create_progress_bar(50, 0)
        assert bar == "░░░░░░░░░░"

    def test_value_exceeds_max(self) -> None:
        """Test that value does not exceed 100%."""
        bar = create_progress_bar(150, 100)
        assert bar == "██████████"


class TestPlaceholderContext:
    """Tests for PlaceholderContext."""

    def test_resolve_extra_data(self) -> None:
        """Test resolving placeholder from extra_data."""
        context = PlaceholderContext(extra_data={"custom_key": "custom_value"})
        assert context.resolve("custom_key") == "custom_value"

    def test_resolve_server_name(self) -> None:
        """Test resolving server_name from guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Server"
        context = PlaceholderContext(guild=guild)
        assert context.resolve("server_name") == "Test Server"

    def test_resolve_server_id(self) -> None:
        """Test resolving server_id from guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123456789
        context = PlaceholderContext(guild=guild)
        assert context.resolve("server_id") == "123456789"

    def test_resolve_user_name(self) -> None:
        """Test resolving user_name from member."""
        member = MagicMock(spec=discord.Member)
        member.display_name = "TestUser"
        context = PlaceholderContext(member=member)
        assert context.resolve("user_name") == "TestUser"

    def test_resolve_user_mention(self) -> None:
        """Test resolving user_mention from member."""
        member = MagicMock(spec=discord.Member)
        member.mention = "<@123456>"
        context = PlaceholderContext(member=member)
        assert context.resolve("user_mention") == "<@123456>"

    def test_resolve_user_joined_server(self) -> None:
        """Test resolving user_joined_server from member."""
        member = MagicMock(spec=discord.Member)
        member.joined_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        context = PlaceholderContext(member=member)
        assert context.resolve("user_joined_server") == "2024-01-15 10:30"

    def test_resolve_user_joined_server_none(self) -> None:
        """Test resolving user_joined_server when it is None."""
        member = MagicMock(spec=discord.Member)
        member.joined_at = None
        context = PlaceholderContext(member=member)
        assert context.resolve("user_joined_server") == "N/A"

    def test_resolve_unknown_placeholder(self) -> None:
        """Test resolving unknown placeholder returns None."""
        context = PlaceholderContext()
        assert context.resolve("unknown_key") is None

    def test_extra_data_overrides_global(self) -> None:
        """Test that extra_data has priority over globals."""
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Real Server Name"
        context = PlaceholderContext(guild=guild, extra_data={"server_name": "Custom Name"})
        assert context.resolve("server_name") == "Custom Name"

    def test_resolve_server_member_count(self) -> None:
        """Test resolving server_member_count from guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.member_count = 150
        context = PlaceholderContext(guild=guild)
        assert context.resolve("server_member_count") == "150"

    def test_resolve_user_id(self) -> None:
        """Test resolving user_id from member."""
        member = MagicMock(spec=discord.Member)
        member.id = 987654321
        context = PlaceholderContext(member=member)
        assert context.resolve("user_id") == "987654321"

    def test_resolve_user_discriminator(self) -> None:
        """Test resolving user_discriminator from member."""
        member = MagicMock(spec=discord.Member)
        member.discriminator = "1234"
        context = PlaceholderContext(member=member)
        assert context.resolve("user_discriminator") == "1234"

    def test_resolve_user_avatar_url(self) -> None:
        """Test resolving user_avatar_url from member."""
        member = MagicMock(spec=discord.Member)
        member.display_avatar.url = "https://cdn.discord.com/avatar.png"
        context = PlaceholderContext(member=member)
        assert context.resolve("user_avatar_url") == "https://cdn.discord.com/avatar.png"

    def test_resolve_user_joined_server_relative(self) -> None:
        """Test resolving user_joined_server_relative from member."""
        member = MagicMock(spec=discord.Member)
        member.joined_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        context = PlaceholderContext(member=member)
        result = context.resolve("user_joined_server_relative")
        assert result is not None
        assert result.startswith("<t:")
        assert result.endswith(":R>")

    def test_resolve_user_joined_server_relative_none(self) -> None:
        """Test resolving user_joined_server_relative when joined_at is None."""
        member = MagicMock(spec=discord.Member)
        member.joined_at = None
        context = PlaceholderContext(member=member)
        assert context.resolve("user_joined_server_relative") == "N/A"

    def test_resolve_user_joined_discord(self) -> None:
        """Test resolving user_joined_discord from member."""
        member = MagicMock(spec=discord.Member)
        member.created_at = datetime(2020, 6, 1, 15, 0, tzinfo=UTC)
        context = PlaceholderContext(member=member)
        assert context.resolve("user_joined_discord") == "2020-06-01 15:00"

    def test_resolve_user_joined_discord_relative(self) -> None:
        """Test resolving user_joined_discord_relative from member."""
        member = MagicMock(spec=discord.Member)
        member.created_at = datetime(2020, 6, 1, 15, 0, tzinfo=UTC)
        context = PlaceholderContext(member=member)
        result = context.resolve("user_joined_discord_relative")
        assert result is not None
        assert result.startswith("<t:")
        assert result.endswith(":R>")


class TestFormatPlaceholders:
    """Tests for format_placeholders."""

    def test_single_placeholder(self) -> None:
        """Test replacing a single placeholder."""
        context = PlaceholderContext(extra_data={"name": "John"})
        result = format_placeholders("Hello {name}!", context)
        assert result == "Hello John!"

    def test_multiple_placeholders(self) -> None:
        """Test replacing multiple placeholders."""
        context = PlaceholderContext(extra_data={"name": "John", "level": "10"})
        result = format_placeholders("{name} level {level}", context)
        assert result == "John level 10"

    def test_unresolved_placeholder_stays(self) -> None:
        """Test that unresolved placeholders remain."""
        context = PlaceholderContext(extra_data={"name": "John"})
        result = format_placeholders("Hello {name}, your level is {level}", context)
        assert result == "Hello John, your level is {level}"

    def test_no_placeholders(self) -> None:
        """Test text without placeholders."""
        context = PlaceholderContext()
        result = format_placeholders("No placeholders", context)
        assert result == "No placeholders"


class TestBuildEmbed:
    """Tests for build_embed."""

    def test_empty_config(self) -> None:
        """Test building embed with empty config."""
        config = EmbedConfig(sections=[])
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert isinstance(embed, discord.Embed)
        assert embed.description is None or embed.description == ""

    def test_text_section(self) -> None:
        """Test simple text section renders as field."""
        config = EmbedConfig(
            sections=[
                EmbedSection(type=EmbedSectionType.TEXT, title="Title", content="Hello World")
            ]
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert len(embed.fields) == 1
        assert embed.fields[0].name == "Title"
        assert embed.fields[0].value == "Hello World"
        assert embed.fields[0].inline is False

    def test_text_section_with_placeholder(self) -> None:
        """Test text section with placeholder."""
        config = EmbedConfig(
            sections=[
                EmbedSection(type=EmbedSectionType.TEXT, title="Greeting", content="Hello {name}!")
            ]
        )
        context = PlaceholderContext(extra_data={"name": "User"})
        embed = build_embed(config, context)

        assert len(embed.fields) == 1
        assert embed.fields[0].value == "Hello User!"

    def test_description_field(self) -> None:
        """Test embed description from config."""
        config = EmbedConfig(
            description="This is the description with {name}",
            sections=[],
        )
        context = PlaceholderContext(extra_data={"name": "placeholder"})
        embed = build_embed(config, context)

        assert embed.description == "This is the description with placeholder"

    def test_fields_section(self) -> None:
        """Test fields section."""
        config = EmbedConfig(
            sections=[
                EmbedSection(
                    type=EmbedSectionType.FIELDS,
                    inline=True,
                    field_1_name="Field 1",
                    field_1_value="Value 1",
                    field_2_name="Field 2",
                    field_2_value="Value 2",
                )
            ]
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert len(embed.fields) == 2
        assert embed.fields[0].name == "Field 1"
        assert embed.fields[0].value == "Value 1"
        assert embed.fields[0].inline is True
        assert embed.fields[1].name == "Field 2"

    def test_custom_color(self) -> None:
        """Test custom color."""
        config = EmbedConfig(sections=[], color="#FF5733")
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.color == discord.Color(0xFF5733)

    def test_invalid_color_uses_default(self) -> None:
        """Test invalid color uses default."""
        config = EmbedConfig(sections=[], color="invalid")
        context = PlaceholderContext()
        embed = build_embed(config, context, default_color=discord.Color.red())

        assert embed.color == discord.Color.red()

    def test_invalid_hex_color_value_error(self) -> None:
        """Test hex color with invalid characters causing ValueError."""
        config = EmbedConfig(sections=[], color="#GGGGGG")
        context = PlaceholderContext()
        embed = build_embed(config, context, default_color=discord.Color.green())

        assert embed.color == discord.Color.green()

    def test_footer(self) -> None:
        """Test embed footer."""
        config = EmbedConfig(
            sections=[],
            footer_text="Footer with {name}",
        )
        context = PlaceholderContext(extra_data={"name": "placeholder"})
        embed = build_embed(config, context)

        assert embed.footer.text == "Footer with placeholder"

    def test_footer_with_icon(self) -> None:
        """Test embed footer with icon."""
        config = EmbedConfig(
            sections=[],
            footer_text="Footer",
            footer_icon_url="https://example.com/icon.png",
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.footer.text == "Footer"
        assert embed.footer.icon_url == "https://example.com/icon.png"

    def test_thumbnail(self) -> None:
        """Test embed thumbnail."""
        config = EmbedConfig(sections=[], thumbnail_url="https://example.com/image.png")
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.thumbnail.url == "https://example.com/image.png"

    def test_multiple_sections(self) -> None:
        """Test multiple sections render as fields."""
        config = EmbedConfig(
            description="Main description",
            sections=[
                EmbedSection(type=EmbedSectionType.TEXT, title="Intro", content="Welcome"),
                EmbedSection(type=EmbedSectionType.TEXT, title="Info", content="More data"),
                EmbedSection(
                    type=EmbedSectionType.FIELDS,
                    field_1_name="Field 1",
                    field_1_value="Value 1",
                ),
            ],
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.description == "Main description"
        assert len(embed.fields) == 3
        assert embed.fields[0].name == "Intro"
        assert embed.fields[0].value == "Welcome"
        assert embed.fields[1].name == "Info"
        assert embed.fields[2].name == "Field 1"

    def test_title_from_config(self) -> None:
        """Test title from config."""
        config = EmbedConfig(
            title="Hello {user_name}",
            sections=[],
        )
        context = PlaceholderContext(extra_data={"user_name": "John"})
        embed = build_embed(config, context)

        assert embed.title == "Hello John"

    def test_title_parameter_overrides_config(self) -> None:
        """Test that title parameter has priority over config."""
        config = EmbedConfig(
            title="Config title",
            sections=[],
        )
        context = PlaceholderContext()
        embed = build_embed(config, context, title="Parameter title")

        assert embed.title == "Parameter title"

    def test_image_url(self) -> None:
        """Test embed main image."""
        config = EmbedConfig(
            sections=[],
            image_url="https://example.com/main-image.png",
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.image.url == "https://example.com/main-image.png"

    def test_field_limit_validation_passes(self) -> None:
        """Test that validation passes with 25 fields or less."""
        # 8 FIELDS sections x 3 fields = 24 fields (within the limit)
        sections = [
            EmbedSection(
                type=EmbedSectionType.FIELDS,
                field_1_name="F1",
                field_1_value="V1",
                field_2_name="F2",
                field_2_value="V2",
                field_3_name="F3",
                field_3_value="V3",
            )
            for _ in range(8)
        ]
        config = EmbedConfig(sections=sections)
        context = PlaceholderContext()

        # Should not raise exception
        embed = build_embed(config, context)
        assert len(embed.fields) == 24

    def test_field_limit_validation_fails(self) -> None:
        """Test that validation fails with more than 25 fields."""
        # 9 FIELDS sections x 3 fields = 27 fields (exceeds the limit)
        sections = [
            EmbedSection(
                type=EmbedSectionType.FIELDS,
                field_1_name="F1",
                field_1_value="V1",
                field_2_name="F2",
                field_2_value="V2",
                field_3_name="F3",
                field_3_value="V3",
            )
            for _ in range(9)
        ]
        config = EmbedConfig(sections=sections)
        context = PlaceholderContext()

        with pytest.raises(EmbedFieldLimitError) as exc_info:
            build_embed(config, context)

        assert exc_info.value.field_count == 27

    def test_field_limit_validation_disabled(self) -> None:
        """Test that field validation can be disabled."""
        sections = [
            EmbedSection(
                type=EmbedSectionType.FIELDS,
                field_1_name="F1",
                field_1_value="V1",
                field_2_name="F2",
                field_2_value="V2",
                field_3_name="F3",
                field_3_value="V3",
            )
            for _ in range(9)
        ]
        config = EmbedConfig(sections=sections)
        context = PlaceholderContext()

        # Should not raise exception with validate_fields=False
        embed = build_embed(config, context, validate_fields=False)
        assert len(embed.fields) == 27


class TestBuildEmbedFromRows:
    """Tests for build_embed_from_rows."""

    def test_from_table_rows(self) -> None:
        """Test building embed from table rows."""
        rows: list[dict[str, Any]] = [
            {"type": "text", "title": "Welcome", "content": "Welcome {user_name}!"},
            {
                "type": "fields",
                "inline": True,
                "field_1_name": "Server",
                "field_1_value": "{server_name}",
            },
        ]

        guild = MagicMock(spec=discord.Guild)
        guild.name = "My Server"

        member = MagicMock(spec=discord.Member)
        member.display_name = "TestUser"

        context = PlaceholderContext(guild=guild, member=member)
        embed = build_embed_from_rows(rows, context, color="#00FF00", footer_text="Footer")

        # TEXT section becomes a field
        assert len(embed.fields) == 2
        assert embed.fields[0].name == "Welcome"
        assert embed.fields[0].value == "Welcome TestUser!"
        # FIELDS section
        assert embed.fields[1].value == "My Server"
        assert embed.color == discord.Color(0x00FF00)
        assert embed.footer.text == "Footer"


class TestGlobalPlaceholders:
    """Tests for the global placeholders list."""

    def test_global_placeholders_not_empty(self) -> None:
        """Test that the global placeholders list is not empty."""
        assert len(GLOBAL_PLACEHOLDERS) > 0

    def test_global_placeholders_have_required_keys(self) -> None:
        """Test that all placeholders have key and description."""
        for placeholder in GLOBAL_PLACEHOLDERS:
            assert "key" in placeholder
            assert "description" in placeholder

    def test_server_placeholders_exist(self) -> None:
        """Test that server placeholders exist."""
        keys = [p["key"] for p in GLOBAL_PLACEHOLDERS]
        assert "server_name" in keys
        assert "server_id" in keys

    def test_user_placeholders_exist(self) -> None:
        """Test that user placeholders exist."""
        keys = [p["key"] for p in GLOBAL_PLACEHOLDERS]
        assert "user_name" in keys
        assert "user_mention" in keys
        assert "user_joined_server" in keys

    def test_dot_emoji_placeholders_exist(self) -> None:
        """Test that dot emoji placeholders exist."""
        keys = [p["key"] for p in GLOBAL_PLACEHOLDERS]
        assert "dot_red" in keys
        assert "dot_green" in keys
        assert "dot_yellow" in keys
        assert "dot_blue" in keys


class TestDotEmojiPlaceholders:
    """Tests for colored dot emoji placeholders."""

    def test_dot_emojis_mapping(self) -> None:
        """Test that emoji mapping is complete."""
        assert DOT_EMOJIS["dot_red"] == "🔴"
        assert DOT_EMOJIS["dot_green"] == "🟢"
        assert DOT_EMOJIS["dot_yellow"] == "🟡"
        assert DOT_EMOJIS["dot_blue"] == "🔵"
        assert DOT_EMOJIS["dot_white"] == "⚪"
        assert DOT_EMOJIS["dot_black"] == "⚫"
        assert DOT_EMOJIS["dot_orange"] == "🟠"
        assert DOT_EMOJIS["dot_purple"] == "🟣"
        assert DOT_EMOJIS["dot_brown"] == "🟤"

    def test_resolve_dot_red(self) -> None:
        """Test resolving dot_red placeholder."""
        context = PlaceholderContext()
        assert context.resolve("dot_red") == "🔴"

    def test_resolve_dot_green(self) -> None:
        """Test resolving dot_green placeholder."""
        context = PlaceholderContext()
        assert context.resolve("dot_green") == "🟢"

    def test_format_with_dot_emojis(self) -> None:
        """Test using dot emojis in templates."""
        context = PlaceholderContext()
        result = format_placeholders("{dot_green} Online {dot_red} Offline", context)
        assert result == "🟢 Online 🔴 Offline"

    def test_dot_emojis_in_embed_field(self) -> None:
        """Test using dot emojis in embed fields."""
        config = EmbedConfig(
            sections=[
                EmbedSection(
                    type=EmbedSectionType.TEXT,
                    title="Status",
                    content="{dot_green} Active",
                )
            ]
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.fields[0].value == "🟢 Active"


class TestAnsiColors:
    """Tests for ANSI color support in text."""

    def test_ansi_colors_mapping(self) -> None:
        """Test that ANSI color mapping is complete."""
        assert "red" in ANSI_COLORS
        assert "green" in ANSI_COLORS
        assert "yellow" in ANSI_COLORS
        assert "blue" in ANSI_COLORS
        assert "pink" in ANSI_COLORS
        assert "cyan" in ANSI_COLORS
        assert "white" in ANSI_COLORS
        assert "gray" in ANSI_COLORS

    def test_color_tags_documentation(self) -> None:
        """Test that color tags documentation exists."""
        assert len(COLOR_TAGS) > 0
        for tag_info in COLOR_TAGS:
            assert "tag" in tag_info
            assert "description" in tag_info

    def test_format_with_colors_no_colors(self) -> None:
        """Test that text without colors is not modified."""
        context = PlaceholderContext(extra_data={"name": "Test"})
        result = format_with_colors("Hello {name}!", context)
        assert result == "Hello Test!"
        assert "```ansi" not in result

    def test_format_with_colors_single_color(self) -> None:
        """Test that text with one color is wrapped in ANSI block."""
        context = PlaceholderContext()
        result = format_with_colors("{red}Error{/red}", context)
        assert "```ansi" in result
        assert "\u001b[2;31m" in result  # Red ANSI code
        assert "\u001b[0m" in result  # Reset code

    def test_format_with_colors_multiple_colors(self) -> None:
        """Test that text with multiple colors works."""
        context = PlaceholderContext()
        result = format_with_colors("{green}OK{/green} - {red}Error{/red}", context)
        assert "```ansi" in result
        assert "\u001b[2;32m" in result  # Green
        assert "\u001b[2;31m" in result  # Red

    def test_format_with_colors_and_placeholders(self) -> None:
        """Test combining colors with placeholders."""
        context = PlaceholderContext(extra_data={"status": "Active"})
        result = format_with_colors("{green}{status}{/green}", context)
        assert "```ansi" in result
        assert "Active" in result

    def test_ansi_colors_in_embed_field(self) -> None:
        """Test using ANSI colors in embed fields."""
        config = EmbedConfig(
            sections=[
                EmbedSection(
                    type=EmbedSectionType.TEXT,
                    title="Status",
                    content="{green}Online{/green}",
                )
            ]
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.fields[0].value is not None
        assert "```ansi" in embed.fields[0].value
        assert "\u001b[2;32m" in embed.fields[0].value

    def test_field_name_does_not_use_ansi(self) -> None:
        """Test that field names do not use ANSI (would look ugly)."""
        config = EmbedConfig(
            sections=[
                EmbedSection(
                    type=EmbedSectionType.TEXT,
                    title="{red}Title{/red}",
                    content="Normal content",
                )
            ]
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        # Field name should NOT have ANSI code block
        assert embed.fields[0].name is not None
        assert "```ansi" not in embed.fields[0].name
        # But the tags remain unprocessed in name
        assert "{red}" in embed.fields[0].name

    def test_inline_fields_support_ansi(self) -> None:
        """Test that inline fields support ANSI colors."""
        config = EmbedConfig(
            sections=[
                EmbedSection(
                    type=EmbedSectionType.FIELDS,
                    inline=True,
                    field_1_name="Status",
                    field_1_value="{green}OK{/green}",
                )
            ]
        )
        context = PlaceholderContext()
        embed = build_embed(config, context)

        assert embed.fields[0].value is not None
        assert "```ansi" in embed.fields[0].value
