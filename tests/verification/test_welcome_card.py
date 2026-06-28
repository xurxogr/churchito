"""Tests for the welcome card renderer and poster."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from PIL import Image

from discord_bot.verification.enums import ConfigKey, VerificationType
from discord_bot.verification.handlers import welcome_card


def _regular_request(username: str) -> MagicMock:
    """Build a mock regular-member verification request.

    Args:
        username (str): In-game username.

    Returns:
        MagicMock: Request mock with a REGULAR verification type.
    """
    return MagicMock(
        username=username,
        verification_type=VerificationType.REGULAR,
        player_info=None,
    )


def _make_template(width: int = 600, height: int = 400) -> bytes:
    """Create an in-memory PNG template for tests.

    Args:
        width (int): Template width in pixels.
        height (int): Template height in pixels.

    Returns:
        bytes: PNG-encoded image bytes.
    """
    image = Image.new("RGB", (width, height), color=(200, 200, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _valid_config() -> dict:
    """Build a fully-populated welcome card config.

    Returns:
        dict: Config keyed by ConfigKey.
    """
    return {
        ConfigKey.WELCOME_CARD_ENABLED: True,
        ConfigKey.WELCOME_CARD_CHANNEL: 555,
        ConfigKey.WELCOME_CARD_TEMPLATE_URL: "https://example.com/template.png",
        ConfigKey.WELCOME_CARD_BOX_X1: 100,
        ConfigKey.WELCOME_CARD_BOX_Y1: 150,
        ConfigKey.WELCOME_CARD_BOX_X2: 500,
        ConfigKey.WELCOME_CARD_BOX_Y2: 250,
        ConfigKey.WELCOME_CARD_NAME_SOURCE: "in_game",
        ConfigKey.WELCOME_CARD_FONT_COLOR: "#000000",
        ConfigKey.WELCOME_CARD_MAX_FONT_SIZE: 120,
    }


class TestResolveCardName:
    """Tests for resolve_card_name."""

    def test_in_game_source_uses_ocr_name(self) -> None:
        """Test that the in-game source returns the OCR name from the screenshot."""
        request = MagicMock(username="xurxogr", player_info={"name": "Xurxogr"})
        member = MagicMock(display_name="★[7-HP | CMD] Xurxogr")

        result = welcome_card.resolve_card_name(
            request=request, member=member, name_source="in_game"
        )

        assert result == "Xurxogr"

    def test_in_game_source_falls_back_to_username_without_ocr(self) -> None:
        """Test that in-game falls back to the username when OCR data is missing."""
        request = MagicMock(username="xurxogr", player_info=None)

        result = welcome_card.resolve_card_name(request=request, member=None, name_source="in_game")

        assert result == "xurxogr"

    def test_in_game_source_ignores_blank_ocr_name(self) -> None:
        """Test that a blank OCR name falls back to the username."""
        request = MagicMock(username="xurxogr", player_info={"name": "   "})

        result = welcome_card.resolve_card_name(request=request, member=None, name_source="in_game")

        assert result == "xurxogr"

    def test_display_source_uses_member_display_name(self) -> None:
        """Test that the display source returns the member display name."""
        request = MagicMock(username="xurxogr", player_info={"name": "Xurxogr"})
        member = MagicMock(display_name="NickName")

        result = welcome_card.resolve_card_name(
            request=request, member=member, name_source="display"
        )

        assert result == "NickName"

    def test_display_source_falls_back_to_in_game_without_member(self) -> None:
        """Test that display source falls back to the in-game name when member is None."""
        request = MagicMock(username="xurxogr", player_info={"name": "Xurxogr"})

        result = welcome_card.resolve_card_name(request=request, member=None, name_source="display")

        assert result == "Xurxogr"

    def test_username_source_uses_discord_handle(self) -> None:
        """Test that the username source returns the raw Discord handle."""
        request = MagicMock(username="xurxogr", player_info={"name": "Xurxogr"})
        member = MagicMock(display_name="NickName")

        result = welcome_card.resolve_card_name(
            request=request, member=member, name_source="username"
        )

        assert result == "xurxogr"

    def test_unknown_source_defaults_to_in_game(self) -> None:
        """Test that an unknown source defaults to the in-game name."""
        request = MagicMock(username="xurxogr", player_info={"name": "Xurxogr"})
        member = MagicMock(display_name="NickName")

        result = welcome_card.resolve_card_name(
            request=request, member=member, name_source="something_else"
        )

        assert result == "Xurxogr"


class TestBuildCardMessage:
    """Tests for build_card_message."""

    def test_empty_template_returns_none(self) -> None:
        """Test that an empty template yields no message."""
        request = MagicMock(user_id=456, username="xurxogr")
        assert (
            welcome_card.build_card_message(
                template="", request=request, member=None, name="Xurxogr", server_name="Guild"
            )
            is None
        )

    def test_replaces_user_mention(self) -> None:
        """Test that {user_mention} becomes a Discord mention."""
        request = MagicMock(user_id=456, username="xurxogr")

        result = welcome_card.build_card_message(
            template="Welcome {user_mention}!",
            request=request,
            member=None,
            name="Xurxogr",
            server_name="Guild",
        )

        assert result == "Welcome <@456>!"

    def test_replaces_all_placeholders(self) -> None:
        """Test that every supported placeholder is substituted."""
        request = MagicMock(user_id=456, username="xurxogr")
        member = MagicMock(display_name="★ Xurxogr")

        result = welcome_card.build_card_message(
            template="{user_mention} {username} {display_name} {name} {server_name}",
            request=request,
            member=member,
            name="Xurxogr",
            server_name="7th Pelotón",
        )

        assert result == "<@456> xurxogr ★ Xurxogr Xurxogr 7th Pelotón"

    def test_display_name_falls_back_to_username_without_member(self) -> None:
        """Test that {display_name} falls back to the username when member is None."""
        request = MagicMock(user_id=456, username="xurxogr")

        result = welcome_card.build_card_message(
            template="{display_name}",
            request=request,
            member=None,
            name="Xurxogr",
            server_name="Guild",
        )

        assert result == "xurxogr"


class TestParseBox:
    """Tests for parse_box."""

    def test_valid_box_returns_tuple(self) -> None:
        """Test that a valid box returns the coordinate tuple."""
        result = welcome_card.parse_box(_valid_config())
        assert result == (100, 150, 500, 250)

    def test_missing_coordinates_returns_none(self) -> None:
        """Test that missing coordinates return None."""
        config = _valid_config()
        del config[ConfigKey.WELCOME_CARD_BOX_X2]
        assert welcome_card.parse_box(config) is None

    def test_non_positive_width_returns_none(self) -> None:
        """Test that x2 <= x1 returns None."""
        config = _valid_config()
        config[ConfigKey.WELCOME_CARD_BOX_X2] = 100
        assert welcome_card.parse_box(config) is None

    def test_non_positive_height_returns_none(self) -> None:
        """Test that y2 <= y1 returns None."""
        config = _valid_config()
        config[ConfigKey.WELCOME_CARD_BOX_Y2] = 150
        assert welcome_card.parse_box(config) is None


class TestParseColor:
    """Tests for parse_color."""

    def test_hex_with_hash(self) -> None:
        """Test parsing a hex color with leading hash."""
        assert welcome_card.parse_color("#FF0000") == (255, 0, 0)

    def test_hex_without_hash(self) -> None:
        """Test parsing a hex color without leading hash."""
        assert welcome_card.parse_color("00FF00") == (0, 255, 0)

    def test_invalid_defaults_to_black(self) -> None:
        """Test that an invalid color defaults to black."""
        assert welcome_card.parse_color("notacolor") == (0, 0, 0)

    def test_none_defaults_to_black(self) -> None:
        """Test that None defaults to black."""
        assert welcome_card.parse_color(None) == (0, 0, 0)


class TestSanitizeName:
    """Tests for sanitize_name."""

    def test_plain_name_unchanged(self) -> None:
        """Test that a plain name is returned unchanged."""
        assert welcome_card.sanitize_name("Lázaro Bayy") == "Lázaro Bayy"

    def test_strips_control_characters(self) -> None:
        """Test that control characters and newlines are removed."""
        assert welcome_card.sanitize_name("Lazaro\n\tBayy") == "Lazaro Bayy"

    def test_truncates_long_names(self) -> None:
        """Test that overly long names are truncated."""
        result = welcome_card.sanitize_name("A" * 200)
        assert len(result) <= welcome_card.MAX_NAME_LENGTH


class TestRenderWelcomeCard:
    """Tests for render_welcome_card."""

    def test_returns_png_preserving_dimensions(self) -> None:
        """Test that the output is a PNG with the template's dimensions."""
        template = _make_template(width=600, height=400)

        result = welcome_card.render_welcome_card(
            template_bytes=template,
            name="Lázaro Bayy",
            box=(100, 150, 500, 250),
        )

        assert result[:8] == b"\x89PNG\r\n\x1a\n"
        rendered = Image.open(io.BytesIO(result))
        assert rendered.size == (600, 400)

    def test_long_name_still_renders(self) -> None:
        """Test that a very long name shrinks to fit without raising."""
        template = _make_template()

        result = welcome_card.render_welcome_card(
            template_bytes=template,
            name="A Very Long Soldier Name That Will Not Fit At Big Sizes",
            box=(100, 150, 500, 250),
        )

        rendered = Image.open(io.BytesIO(result))
        assert rendered.size == (600, 400)

    def test_accented_name_renders(self) -> None:
        """Test that accented characters render without error."""
        template = _make_template()

        result = welcome_card.render_welcome_card(
            template_bytes=template,
            name="Lázaro Ñoño Über",
            box=(100, 150, 500, 250),
            color=(255, 255, 255),
        )

        assert Image.open(io.BytesIO(result)).size == (600, 400)

    def test_empty_name_returns_image(self) -> None:
        """Test that an empty name still returns a valid image."""
        template = _make_template()

        result = welcome_card.render_welcome_card(
            template_bytes=template,
            name="",
            box=(100, 150, 500, 250),
        )

        assert Image.open(io.BytesIO(result)).size == (600, 400)


class TestFetchTemplate:
    """Tests for fetch_template."""

    @pytest.mark.asyncio
    async def test_success_returns_bytes(self) -> None:
        """Test that a successful fetch returns the image bytes."""
        payload = _make_template()
        response = MagicMock(status_code=200, content=payload)
        response.headers = {"content-type": "image/png", "content-length": str(len(payload))}
        client = MagicMock()
        client.get = AsyncMock(return_value=response)

        result = await welcome_card.fetch_template(url="https://example.com/t.png", client=client)

        assert result == payload

    @pytest.mark.asyncio
    async def test_non_200_returns_none(self) -> None:
        """Test that a non-200 response returns None."""
        response = MagicMock(status_code=404, content=b"", headers={})
        client = MagicMock()
        client.get = AsyncMock(return_value=response)

        result = await welcome_card.fetch_template(url="https://example.com/t.png", client=client)

        assert result is None

    @pytest.mark.asyncio
    async def test_oversize_returns_none(self) -> None:
        """Test that an oversized payload returns None."""
        big = b"x" * (welcome_card.MAX_IMAGE_BYTES + 1)
        response = MagicMock(status_code=200, content=big)
        response.headers = {"content-type": "image/png"}
        client = MagicMock()
        client.get = AsyncMock(return_value=response)

        result = await welcome_card.fetch_template(url="https://example.com/t.png", client=client)

        assert result is None

    @pytest.mark.asyncio
    async def test_request_error_returns_none(self) -> None:
        """Test that a transport error returns None."""
        client = MagicMock()
        client.get = AsyncMock(side_effect=Exception("boom"))

        result = await welcome_card.fetch_template(url="https://example.com/t.png", client=client)

        assert result is None


class TestPostWelcomeCard:
    """Tests for post_welcome_card."""

    def _guild_with_channel(self, channel: MagicMock) -> MagicMock:
        """Build a guild mock whose get_channel returns the given channel."""
        guild = MagicMock()
        guild.get_channel = MagicMock(return_value=channel)
        guild.name = "Test Guild"
        return guild

    @pytest.mark.asyncio
    async def test_disabled_does_not_post(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a disabled card never posts."""
        channel = MagicMock()
        channel.send = AsyncMock()
        guild = self._guild_with_channel(channel)
        config = _valid_config()
        config[ConfigKey.WELCOME_CARD_ENABLED] = False
        fetch = AsyncMock()
        monkeypatch.setattr(welcome_card, "fetch_template", fetch)

        await welcome_card.post_welcome_card(
            guild=guild, config=config, request=_regular_request("X"), member=MagicMock()
        )

        channel.send.assert_not_called()
        fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_template_url_does_not_post(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that a missing template URL never posts."""
        channel = MagicMock()
        channel.send = AsyncMock()
        guild = self._guild_with_channel(channel)
        config = _valid_config()
        config[ConfigKey.WELCOME_CARD_TEMPLATE_URL] = ""
        monkeypatch.setattr(welcome_card, "fetch_template", AsyncMock())

        await welcome_card.post_welcome_card(
            guild=guild, config=config, request=_regular_request("X"), member=MagicMock()
        )

        channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_failure_does_not_post(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a failed template fetch never posts and never raises."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        guild = self._guild_with_channel(channel)
        monkeypatch.setattr(welcome_card, "fetch_template", AsyncMock(return_value=None))

        await welcome_card.post_welcome_card(
            guild=guild,
            config=_valid_config(),
            request=_regular_request("X"),
            member=MagicMock(),
        )

        channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_channel_not_found_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a missing channel does not raise."""
        guild = MagicMock()
        guild.get_channel = MagicMock(return_value=None)
        monkeypatch.setattr(
            welcome_card, "fetch_template", AsyncMock(return_value=_make_template())
        )

        await welcome_card.post_welcome_card(
            guild=guild,
            config=_valid_config(),
            request=_regular_request("X"),
            member=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_valid_posts_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a valid configuration posts a file to the channel."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        guild = self._guild_with_channel(channel)
        monkeypatch.setattr(
            welcome_card, "fetch_template", AsyncMock(return_value=_make_template())
        )

        request = _regular_request("Lázaro Bayy")
        await welcome_card.post_welcome_card(
            guild=guild, config=_valid_config(), request=request, member=MagicMock()
        )

        channel.send.assert_awaited_once()
        _, kwargs = channel.send.call_args
        assert "file" in kwargs
        assert kwargs["content"] is None

    @pytest.mark.asyncio
    async def test_message_posted_as_content(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a configured message is sent as content with the user mention."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        guild = self._guild_with_channel(channel)
        monkeypatch.setattr(
            welcome_card, "fetch_template", AsyncMock(return_value=_make_template())
        )

        config = _valid_config()
        config[ConfigKey.WELCOME_CARD_MESSAGE] = "Welcome {user_mention} to {server_name}!"
        request = MagicMock(
            user_id=456,
            username="xurxogr",
            verification_type=VerificationType.REGULAR,
            player_info={"name": "Xurxogr"},
        )

        await welcome_card.post_welcome_card(
            guild=guild,
            config=config,
            request=request,
            member=MagicMock(display_name="Xurxogr"),
        )

        channel.send.assert_awaited_once()
        _, kwargs = channel.send.call_args
        assert kwargs["content"] == "Welcome <@456> to Test Guild!"
        assert "file" in kwargs

    @pytest.mark.asyncio
    async def test_ally_verification_does_not_post(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that an ally verification never posts a welcome card."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        guild = self._guild_with_channel(channel)
        fetch = AsyncMock(return_value=_make_template())
        monkeypatch.setattr(welcome_card, "fetch_template", fetch)

        ally_request = MagicMock(username="AllyUser", verification_type=VerificationType.ALLY)
        await welcome_card.post_welcome_card(
            guild=guild, config=_valid_config(), request=ally_request, member=MagicMock()
        )

        channel.send.assert_not_called()
        fetch.assert_not_called()
