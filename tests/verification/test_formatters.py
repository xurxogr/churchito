"""Tests for discord_bot/verification/formatters.py."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import discord

from discord_bot.verification.enums import ConfigKey, VerificationStatus, VerificationType
from discord_bot.verification.formatters import (
    _clean_status_text,
    _parse_hex_color,
    build_history_section,
    build_mod_embed_sections,
    create_mod_embeds,
    create_panel_embed,
    create_tracker_embed,
    format_message,
    get_verification_type_display,
)


class TestFormatMessage:
    """Tests for format_message."""

    def test_format_all_placeholders(self) -> None:
        """Test replacement of all placeholders."""
        template = "User: {username}, Server: {server_name}"

        result = format_message(
            template,
            username="TestUser",
            server_name="TestServer",
        )

        assert result == "User: TestUser, Server: TestServer"

    def test_format_empty_placeholders(self) -> None:
        """Test with placeholder passed as None."""
        template = "User: {username}"
        result = format_message(template, username=None)
        assert result == "User: "

    def test_format_unmatched_placeholder(self) -> None:
        """Test that unmatched placeholders are preserved."""
        template = "User: {username}"
        result = format_message(template)
        assert result == "User: {username}"

    def test_format_no_placeholders(self) -> None:
        """Test message without placeholders."""
        template = "Simple message without placeholders"
        result = format_message(template)
        assert result == template

    def test_format_none_template(self) -> None:
        """Test with None template."""
        result = format_message(None, username="Test")
        assert result == ""

    def test_format_multiple_same_placeholder(self) -> None:
        """Test that multiple occurrences of the same placeholder are replaced."""
        template = "{username} greets {username}"
        result = format_message(template, username="John")
        assert result == "John greets John"

    def test_format_with_special_characters(self) -> None:
        """Test with special characters in the value."""
        template = "User: {username}"
        result = format_message(template, username="Test<>User")
        assert result == "User: Test<>User"


class TestCreatePanelEmbed:
    """Tests for create_panel_embed."""

    def test_no_image_url(self) -> None:
        """Test that text without image URL returns embed with description."""
        text = "Simple message without image"
        embed = create_panel_embed(text)

        assert embed is not None
        assert isinstance(embed, discord.Embed)
        assert embed.description == text

    def test_with_png_image(self) -> None:
        """Test text with PNG image URL."""
        text = "Welcome to the server\nhttps://example.com/image.png"
        embed = create_panel_embed(text)

        assert embed is not None
        assert isinstance(embed, discord.Embed)
        assert "image.png" not in (embed.description or "")
        assert "Welcome" in (embed.description or "")
        assert embed.image is not None

    def test_with_jpg_image(self) -> None:
        """Test text with JPG image URL."""
        text = "Text with image https://example.com/photo.jpg here"
        embed = create_panel_embed(text)

        assert embed is not None
        assert "photo.jpg" not in (embed.description or "")
        assert embed.image is not None

    def test_with_jpeg_image(self) -> None:
        """Test text with JPEG image URL."""
        text = "https://example.com/photo.jpeg"
        embed = create_panel_embed(text)

        assert embed is not None
        assert embed.image is not None

    def test_with_gif_image(self) -> None:
        """Test text with GIF image URL."""
        text = "Animation: https://example.com/animation.gif"
        embed = create_panel_embed(text)

        assert embed is not None
        assert embed.image is not None

    def test_with_webp_image(self) -> None:
        """Test text with WEBP image URL."""
        text = "Modern image: https://example.com/image.webp"
        embed = create_panel_embed(text)

        assert embed is not None
        assert embed.image is not None

    def test_with_query_params(self) -> None:
        """Test image URL with query parameters."""
        text = "Image: https://example.com/image.png?width=100&height=200"
        embed = create_panel_embed(text)

        assert embed is not None
        assert "width=100" not in (embed.description or "")
        assert embed.image is not None

    def test_removes_extra_newlines(self) -> None:
        """Test that removes extra empty lines."""
        text = "First line\n\n\nhttps://example.com/image.png\n\n\nLast line"
        embed = create_panel_embed(text)

        assert embed is not None
        # Should not have more than 2 consecutive newlines
        assert "\n\n\n" not in (embed.description or "")

    def test_embed_has_blurple_color(self) -> None:
        """Test that the embed has blurple color."""
        text = "Text https://example.com/image.png"
        embed = create_panel_embed(text)

        assert embed is not None
        assert embed.color == discord.Color.blurple()

    def test_embed_description_contains_text(self) -> None:
        """Test that the embed contains the text in the description."""
        text = "Message content https://example.com/image.png"
        embed = create_panel_embed(text)

        assert embed is not None
        assert "Message content" in (embed.description or "")

    def test_case_insensitive_extension(self) -> None:
        """Test that the extension is case insensitive."""
        text = "Image: https://example.com/image.PNG"
        embed = create_panel_embed(text)

        assert embed is not None
        assert embed.image is not None


class TestGetVerificationTypeDisplay:
    """Tests for get_verification_type_display."""

    def test_regular_type_with_config(self) -> None:
        """Test regular type with config."""
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY: "Member",
        }

        result = get_verification_type_display(VerificationType.REGULAR, config)

        assert result == "Member"

    def test_regular_type_default(self) -> None:
        """Test regular type with default value."""
        config: dict[str, Any] = {}

        result = get_verification_type_display(VerificationType.REGULAR, config)

        assert result == "Normal"

    def test_ally_type_with_config(self) -> None:
        """Test ally type with config."""
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY: "Friend",
        }

        result = get_verification_type_display(VerificationType.ALLY, config)

        assert result == "Friend"

    def test_ally_type_default(self) -> None:
        """Test ally type with default value."""
        config: dict[str, Any] = {}

        result = get_verification_type_display(VerificationType.ALLY, config)

        assert result == "Ally"

    def test_regular_type_with_none_value(self) -> None:
        """Test regular type when config has None."""
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY: None,
        }

        result = get_verification_type_display(VerificationType.REGULAR, config)

        assert result == "Normal"

    def test_ally_type_with_empty_string(self) -> None:
        """Test ally type when config has empty string."""
        config: dict[str, Any] = {
            ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY: "",
        }

        result = get_verification_type_display(VerificationType.ALLY, config)

        # Empty string is falsy, so it should return default
        assert result == "Ally"


class TestParseHexColor:
    """Tests for _parse_hex_color."""

    def test_valid_hex_with_hash(self) -> None:
        """Test valid hex color with #."""
        result = _parse_hex_color("#FF5733")
        assert result is not None
        assert result == discord.Color(0xFF5733)

    def test_valid_hex_without_hash(self) -> None:
        """Test valid hex color without #."""
        result = _parse_hex_color("3498db")
        assert result is not None
        assert result == discord.Color(0x3498DB)

    def test_empty_string(self) -> None:
        """Test with empty string."""
        result = _parse_hex_color("")
        assert result is None

    def test_none_value(self) -> None:
        """Test with None."""
        result = _parse_hex_color(None)
        assert result is None

    def test_invalid_length(self) -> None:
        """Test with invalid length."""
        result = _parse_hex_color("#FFF")
        assert result is None

    def test_invalid_characters(self) -> None:
        """Test with invalid characters."""
        result = _parse_hex_color("#GGGGGG")
        assert result is None

    def test_with_whitespace(self) -> None:
        """Test that removes whitespace."""
        result = _parse_hex_color("  #FF5733  ")
        assert result is not None
        assert result == discord.Color(0xFF5733)


class TestCreateModEmbeds:
    """Tests for create_mod_embeds."""

    def test_basic_embed_with_default_config(self) -> None:
        """Test basic embed with default configuration."""
        config: dict[str, Any] = {}
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            status="Test status",
        )
        assert embeds[0].description is not None
        assert "Test status" in embeds[0].description
        # Default color is #FFA500 (orange) from DEFAULT_MOD_EMBED_CONFIG
        assert embeds[0].color == discord.Color(0xFFA500)

    def test_with_configured_footer(self) -> None:
        """Test embed with configured footer."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "footer_text": "User: {username}",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            username="TestUser",
        )
        assert embeds[0].footer is not None
        assert embeds[0].footer.text is not None
        assert "TestUser" in embeds[0].footer.text

    def test_with_user_id_default_thumbnail(self) -> None:
        """Test embed with default thumbnail based on user_id."""
        config: dict[str, Any] = {}
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            user_id=12345,
        )
        assert embeds[0].thumbnail is not None
        assert embeds[0].thumbnail.url is not None
        assert "cdn.discordapp.com" in embeds[0].thumbnail.url

    def test_custom_color_regular(self) -> None:
        """Test custom color for regular verification."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "color": "#3498db",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        assert embeds[0].color == discord.Color(0x3498DB)

    def test_custom_color_ally(self) -> None:
        """Test custom color for ally verification."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_ALLY: {
                "color": "#e74c3c",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.ALLY,
            config=config,
        )
        assert embeds[0].color == discord.Color(0xE74C3C)

    def test_custom_thumbnail_regular(self) -> None:
        """Test custom thumbnail for regular verification."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "thumbnail_url": "https://example.com/icon.png",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        assert embeds[0].thumbnail is not None
        assert embeds[0].thumbnail.url == "https://example.com/icon.png"

    def test_custom_thumbnail_ally(self) -> None:
        """Test custom thumbnail for ally verification."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_ALLY: {
                "thumbnail_url": "https://example.com/ally.png",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.ALLY,
            config=config,
        )
        assert embeds[0].thumbnail is not None
        assert embeds[0].thumbnail.url == "https://example.com/ally.png"

    def test_empty_config_uses_default_color(self) -> None:
        """Test that empty configuration uses orange by default."""
        config: dict[str, Any] = {}
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        # Default color is #FFA500 (orange) from DEFAULT_MOD_EMBED_CONFIG
        assert embeds[0].color == discord.Color(0xFFA500)

    def test_invalid_color_uses_default(self) -> None:
        """Test that invalid color uses orange by default."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "color": "invalid",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        assert embeds[0].color == discord.Color.orange()

    def test_custom_thumbnail_overrides_user_avatar(self) -> None:
        """Test that custom thumbnail takes priority over avatar."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "thumbnail_url": "https://example.com/custom.png",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            user_id=12345,
        )
        assert embeds[0].thumbnail is not None
        assert embeds[0].thumbnail.url == "https://example.com/custom.png"

    def test_title_regular(self) -> None:
        """Test custom title for regular verification."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "title": "🟢 Member Verification",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        assert embeds[0].title == "🟢 Member Verification"

    def test_title_ally(self) -> None:
        """Test custom title for ally verification."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_ALLY: {
                "title": "🟡 Ally Verification",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.ALLY,
            config=config,
        )
        assert embeds[0].title == "🟡 Ally Verification"

    def test_empty_title_not_shown(self) -> None:
        """Test that empty title is not shown."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "title": "",
                "sections": [{"type": "text", "content": "Test"}],
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        assert embeds[0].title is None

    def test_no_title_without_config(self) -> None:
        """Test that there is no title with default configuration."""
        config: dict[str, Any] = {}
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )
        assert embeds[0].title is None

    def test_placeholders_replaced(self) -> None:
        """Test that placeholders are replaced."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "description": "User: {username}, Status: {status}",
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            username="TestUser",
            status="Pending",
        )
        assert embeds[0].description is not None
        assert "TestUser" in embeds[0].description
        assert "Pending" in embeds[0].description

    def test_additional_content_appended(self) -> None:
        """Test that additional content is appended."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "description": "Base content",
            },
        }
        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            additional_content="\n\nPlayer Info: Level 25",
        )
        assert embeds[0].description is not None
        assert "Base content" in embeds[0].description
        assert "Player Info: Level 25" in embeds[0].description

    def test_additional_sections_text(self) -> None:
        """Test that additional text sections are added as fields."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "description": "Base content",
            },
        }
        additional_sections = [
            {"type": "text", "title": "Player Info", "content": "Name: {name}, Level: {level}"},
        ]
        sections_context = {"name": "TestPlayer", "level": "25"}

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            additional_sections=additional_sections,
            sections_context=sections_context,
        )

        assert embeds[0].description is not None
        assert "Base content" in embeds[0].description
        # TEXT section is now a field
        assert len(embeds[0].fields) == 1
        assert embeds[0].fields[0].name == "Player Info"
        assert embeds[0].fields[0].value is not None
        assert "TestPlayer" in embeds[0].fields[0].value
        assert "25" in embeds[0].fields[0].value

    def test_additional_sections_fields(self) -> None:
        """Test that additional sections with fields are added."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "description": "Base content",
            },
        }
        additional_sections = [
            {
                "type": "fields",
                "inline": True,
                "field_1_name": "Name",
                "field_1_value": "{name}",
                "field_2_name": "Level",
                "field_2_value": "{level}",
                "field_3_name": "Faction",
                "field_3_value": "{faction}",
            },
        ]
        sections_context = {"name": "TestPlayer", "level": "25", "faction": "colonial"}

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            additional_sections=additional_sections,
            sections_context=sections_context,
        )

        assert len(embeds[0].fields) == 3
        assert embeds[0].fields[0].name == "Name"
        assert embeds[0].fields[0].value == "TestPlayer"
        assert embeds[0].fields[1].name == "Level"
        assert embeds[0].fields[1].value == "25"
        assert embeds[0].fields[2].name == "Faction"
        assert embeds[0].fields[2].value == "colonial"

    def test_additional_sections_without_context(self) -> None:
        """Test additional sections without context (unresolved placeholders)."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "description": "Base",
            },
        }
        additional_sections = [
            {"type": "text", "title": "Info", "content": "Name: {name}"},
        ]

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            additional_sections=additional_sections,
        )

        # TEXT section is a field, placeholder not resolved stays as-is
        assert len(embeds[0].fields) == 1
        assert embeds[0].fields[0].value is not None
        assert "{name}" in embeds[0].fields[0].value

    def test_mixed_sections_as_fields(self) -> None:
        """Test that all sections are rendered as fields."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "color": "#FFA500",
                "description": "Main description",
                "footer_text": "User: {username}",
                "sections": [
                    {"type": "text", "title": "Section 1", "content": "Text content"},
                    {
                        "type": "fields",
                        "inline": True,
                        "field_1_name": "Field 1",
                        "field_1_value": "Value 1",
                        "field_2_name": "Field 2",
                        "field_2_value": "Value 2",
                    },
                ],
            },
        }

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            username="TestUser",
        )

        # Should be single embed
        assert len(embeds) == 1

        # Description from config
        assert embeds[0].description is not None
        assert "Main description" in embeds[0].description

        # All sections are fields
        assert len(embeds[0].fields) == 3
        assert embeds[0].fields[0].name == "Section 1"
        assert embeds[0].fields[0].value == "Text content"
        assert embeds[0].fields[1].name == "Field 1"
        assert embeds[0].fields[2].name == "Field 2"

        # Footer with username (now requires explicit config)
        assert embeds[0].footer is not None
        assert embeds[0].footer.text is not None
        assert "TestUser" in embeds[0].footer.text

    def test_text_sections_as_full_width_fields(self) -> None:
        """Test that TEXT sections are rendered as full-width fields."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "sections": [
                    {"type": "text", "title": "Title 1", "content": "Content 1"},
                    {"type": "text", "title": "Title 2", "content": "Content 2"},
                ],
            },
        }

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
        )

        # All sections as fields in single embed
        assert len(embeds) == 1
        assert len(embeds[0].fields) == 2
        assert embeds[0].fields[0].name == "Title 1"
        assert embeds[0].fields[0].value == "Content 1"
        assert embeds[0].fields[1].name == "Title 2"
        assert embeds[0].fields[1].value == "Content 2"


class TestBuildHistorySection:
    """Tests for build_history_section."""

    def test_returns_none_for_empty_history(self) -> None:
        """Test that returns None when there is no history."""
        result = build_history_section(
            past_requests=[],
            config={},
        )
        assert result is None

    def test_builds_history_with_approved_request(self) -> None:
        """Test that builds history with approved request."""
        mock_request = MagicMock()
        mock_request.status = VerificationStatus.APPROVED.value
        mock_request.verification_type = VerificationType.REGULAR.value
        mock_request.reviewed_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        mock_request.created_at = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        mock_request.reviewed_by_username = "Mod1"
        mock_request.rejection_reason = None

        result = build_history_section(
            past_requests=[mock_request],
            config={},
        )

        assert result is not None
        assert result["type"] == "text"
        assert result["title"] == "History"
        assert "✅" in result["content"]
        assert "Mod1" in result["content"]
        assert "2024-01-15" in result["content"]

    def test_builds_history_with_rejected_request(self) -> None:
        """Test that builds history with rejected request."""
        mock_request = MagicMock()
        mock_request.status = VerificationStatus.REJECTED.value
        mock_request.verification_type = VerificationType.ALLY.value
        mock_request.reviewed_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        mock_request.created_at = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        mock_request.reviewed_by_username = "Mod2"
        mock_request.rejection_reason = "Invalid screenshot"

        result = build_history_section(
            past_requests=[mock_request],
            config={ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY: "Ally"},
        )

        assert result is not None
        assert "❌" in result["content"]
        assert "Invalid screenshot" in result["content"]
        assert "Ally" in result["content"]

    def test_uses_custom_history_label(self) -> None:
        """Test that uses custom history label."""
        mock_request = MagicMock()
        mock_request.status = VerificationStatus.APPROVED.value
        mock_request.verification_type = VerificationType.REGULAR.value
        mock_request.reviewed_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        mock_request.created_at = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        mock_request.reviewed_by_username = "Mod1"
        mock_request.rejection_reason = None

        result = build_history_section(
            past_requests=[mock_request],
            config={ConfigKey.HISTORY_LABEL: "Previous Requests"},
        )

        assert result is not None
        assert result["title"] == "Previous Requests"

    def test_limits_to_five_requests(self) -> None:
        """Test that limits to 5 requests maximum."""
        past_requests = []
        for i in range(10):
            mock_request = MagicMock()
            mock_request.status = VerificationStatus.APPROVED.value
            mock_request.verification_type = VerificationType.REGULAR.value
            mock_request.reviewed_at = datetime(2024, 1, i + 1, 10, 30, tzinfo=UTC)
            mock_request.created_at = datetime(2024, 1, i + 1, 10, 0, tzinfo=UTC)
            mock_request.reviewed_by_username = f"Mod{i}"
            mock_request.rejection_reason = None
            past_requests.append(mock_request)

        result = build_history_section(
            past_requests=past_requests,
            config={},
        )

        assert result is not None
        # Should only have 5 entries
        lines = result["content"].split("\n")
        assert len(lines) == 5


class TestBuildModEmbedSections:
    """Tests for build_mod_embed_sections."""

    def test_returns_empty_without_player_info_or_history(self) -> None:
        """Test that returns empty without player info or history."""
        additional_sections, sections_context = build_mod_embed_sections(
            config={},
            player_info=None,
            past_requests=[],
        )

        assert additional_sections == []
        assert sections_context is None

    def test_returns_player_info_sections_when_configured(self) -> None:
        """Test that returns player info sections when configured."""
        player_info = {"name": "TestPlayer", "level": "25", "regiment": "TestReg"}
        config: dict[str, Any] = {
            ConfigKey.PLAYER_INFO_SECTIONS: [
                {"type": "text", "title": "Player", "content": "Name: {name}"},
                {"type": "fields", "field_1_name": "Level", "field_1_value": "{level}"},
            ],
        }

        additional_sections, sections_context = build_mod_embed_sections(
            config=config,
            player_info=player_info,
            past_requests=[],
        )

        assert len(additional_sections) == 2
        assert sections_context == player_info
        assert additional_sections[0]["title"] == "Player"
        assert additional_sections[1]["type"] == "fields"

    def test_returns_history_section_when_past_requests_exist(self) -> None:
        """Test that returns history section when past requests exist."""
        mock_request = MagicMock()
        mock_request.status = VerificationStatus.APPROVED.value
        mock_request.verification_type = VerificationType.REGULAR.value
        mock_request.reviewed_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        mock_request.created_at = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        mock_request.reviewed_by_username = "Mod1"
        mock_request.rejection_reason = None

        additional_sections, sections_context = build_mod_embed_sections(
            config={},
            player_info=None,
            past_requests=[mock_request],
        )

        assert len(additional_sections) == 1
        assert additional_sections[0]["type"] == "text"
        assert additional_sections[0]["title"] == "History"
        assert sections_context is None

    def test_combines_player_info_and_history(self) -> None:
        """Test that combines player info and history."""
        player_info = {"name": "TestPlayer", "level": "25"}
        config: dict[str, Any] = {
            ConfigKey.PLAYER_INFO_SECTIONS: [
                {"type": "text", "title": "Player", "content": "Name: {name}"},
            ],
        }
        mock_request = MagicMock()
        mock_request.status = VerificationStatus.APPROVED.value
        mock_request.verification_type = VerificationType.REGULAR.value
        mock_request.reviewed_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        mock_request.created_at = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        mock_request.reviewed_by_username = "Mod1"
        mock_request.rejection_reason = None

        additional_sections, sections_context = build_mod_embed_sections(
            config=config,
            player_info=player_info,
            past_requests=[mock_request],
        )

        assert len(additional_sections) == 2
        assert additional_sections[0]["title"] == "Player"
        assert additional_sections[1]["title"] == "History"
        assert sections_context == player_info

    def test_ignores_player_info_without_config_sections(self) -> None:
        """Test that ignores player info if no sections are configured."""
        player_info = {"name": "TestPlayer", "level": "25"}
        config: dict[str, Any] = {}

        additional_sections, sections_context = build_mod_embed_sections(
            config=config,
            player_info=player_info,
            past_requests=[],
        )

        assert additional_sections == []
        assert sections_context is None


class TestCreateTrackerEmbed:
    """Tests for create_tracker_embed."""

    def test_creates_embed_with_pending_requests(self) -> None:
        """Test that creates embed with pending requests."""
        request = MagicMock()
        request.username = "TestUser"
        request.status = VerificationStatus.PENDING_SCREENSHOTS
        request.verification_type = VerificationType.REGULAR
        request.mod_message_id = 12345
        request.created_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)

        config: dict[str, Any] = {
            ConfigKey.TRACKER_TITLE: "📋 Test Title",
            ConfigKey.STATUS_AWAITING_SCREENSHOTS: "⏳ Awaiting screenshots",
            ConfigKey.STATUS_PENDING_REVIEW: "🔍 Pending review",
            ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY: "Normal",
        }

        embed = create_tracker_embed(
            pending_requests=[request],
            config=config,
            guild_id=123,
            channel_id=456,
        )

        assert embed.title == "📋 Test Title"
        assert embed.description is not None
        assert "[TestUser]" in embed.description  # Username as link
        assert "Normal" in embed.description
        assert "discord.com" in embed.description  # Link URL present

    def test_creates_embed_without_mod_message_id(self) -> None:
        """Test that creates embed without link when there is no mod_message_id."""
        request = MagicMock()
        request.id = 42
        request.public_id = "42"
        request.username = "TestUser"
        request.status = VerificationStatus.PENDING_REVIEW
        request.verification_type = VerificationType.ALLY
        request.mod_message_id = None  # No mod message
        request.created_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)

        config: dict[str, Any] = {
            ConfigKey.STATUS_AWAITING_SCREENSHOTS: "⏳ Awaiting screenshots",
            ConfigKey.STATUS_PENDING_REVIEW: "🔍 Pending review",
            ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY: "Ally",
        }

        embed = create_tracker_embed(
            pending_requests=[request],
            config=config,
            guild_id=123,
            channel_id=456,
        )

        assert embed.description is not None
        assert "TestUser" in embed.description  # Username shown without link
        assert "Ally" in embed.description
        assert "[TestUser]" not in embed.description  # No link format
        assert "discord.com" not in embed.description  # No link URL
        assert "<t:" in embed.description  # Still has timestamp

    def test_groups_by_type(self) -> None:
        """Test that groups by verification type."""
        request1 = MagicMock()
        request1.id = 1
        request1.username = "User1"
        request1.status = VerificationStatus.PENDING_REVIEW
        request1.verification_type = VerificationType.REGULAR
        request1.mod_message_id = 12345
        request1.created_at = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)

        request2 = MagicMock()
        request2.id = 2
        request2.username = "User2"
        request2.status = VerificationStatus.PENDING_SCREENSHOTS
        request2.verification_type = VerificationType.ALLY
        request2.mod_message_id = 12346
        request2.created_at = datetime(2024, 1, 15, 11, 30, tzinfo=UTC)

        config: dict[str, Any] = {
            ConfigKey.STATUS_PENDING_REVIEW: "🔍 Pending review",
            ConfigKey.STATUS_AWAITING_SCREENSHOTS: "⏳ Awaiting screenshots",
            ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY: "Member",
            ConfigKey.VERIFICATION_TYPE_ALLY_DISPLAY: "Ally",
        }

        embed = create_tracker_embed(
            pending_requests=[request1, request2],
            config=config,
            guild_id=123,
            channel_id=456,
        )

        assert embed.description is not None
        # Type headers should be bold
        assert "**Member**" in embed.description
        assert "**Ally**" in embed.description
        # Usernames present
        assert "User1" in embed.description
        assert "User2" in embed.description


class TestCleanStatusText:
    """Tests for _clean_status_text."""

    def test_removes_bold_label(self) -> None:
        """Test that removes bold label."""
        result = _clean_status_text("**Status:** Waiting for screenshots")
        assert result == "Waiting for screenshots"

    def test_handles_plain_text(self) -> None:
        """Test that handles plain text."""
        result = _clean_status_text("Waiting for screenshots")
        assert result == "Waiting for screenshots"

    def test_removes_bold_label_only(self) -> None:
        """Test that removes only the bold label."""
        result = _clean_status_text("**Pending:** Manual review")
        assert result == "Manual review"


class TestCreateModEmbedsInvalidSections:
    """Tests for create_mod_embeds with invalid sections."""

    def test_skips_non_dict_sections(self) -> None:
        """Test that ignores sections that are not dictionaries."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "color": "#FF0000",
                "sections": [{"type": "text", "content": "Test"}],
            },
            ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY: "Normal",
        }

        # Additional sections with non-dict value (cast to bypass type check)
        additional_sections: list[dict[str, Any]] = [
            {"type": "text", "content": "Valid section"},
        ]
        # Inject invalid section for test
        additional_sections.insert(0, "not a dict")  # type: ignore[arg-type]

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            username="TestUser",
            status="Pending",
            additional_sections=additional_sections,
        )

        # Should still create embeds, skipping invalid section
        assert len(embeds) >= 1

    def test_skips_sections_without_type(self) -> None:
        """Test that ignores sections without type field."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "color": "#FF0000",
                "sections": [{"type": "text", "content": "Test"}],
            },
            ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY: "Normal",
        }

        additional_sections: list[dict[str, Any]] = [
            {"content": "No type field"},  # Missing type
            {"type": "text", "content": "Valid section"},
        ]

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            username="TestUser",
            status="Pending",
            additional_sections=additional_sections,
        )

        assert len(embeds) >= 1

    def test_skips_sections_with_invalid_embed_section(self) -> None:
        """Test that ignores sections that cannot create EmbedSection."""
        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "color": "#FF0000",
                "sections": [{"type": "text", "content": "Test"}],
            },
            ConfigKey.VERIFICATION_TYPE_REGULAR_DISPLAY: "Normal",
        }

        additional_sections: list[dict[str, Any]] = [
            {"type": "invalid_type", "content": "Bad type"},  # Invalid type
            {"type": "text", "content": "Valid section"},
        ]

        embeds = create_mod_embeds(
            verification_type=VerificationType.REGULAR,
            config=config,
            username="TestUser",
            status="Pending",
            additional_sections=additional_sections,
        )

        assert len(embeds) >= 1
