"""Tests for the welcome card renderer and poster."""

from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import httpx
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

    def test_in_game_source_falls_back_to_display_name_without_request(self) -> None:
        """Test that in-game falls back to the member's display name with no request."""
        member = MagicMock(display_name="★[7-HP | CMD] Xurxogr")

        result = welcome_card.resolve_card_name(request=None, member=member, name_source="in_game")

        assert result == "★[7-HP | CMD] Xurxogr"

    def test_username_source_falls_back_to_member_name_without_request(self) -> None:
        """Test that username source falls back to the member's raw name with no request."""
        member = MagicMock()
        member.name = "xurxogr"

        result = welcome_card.resolve_card_name(request=None, member=member, name_source="username")

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
        member = MagicMock(id=456, display_name="★ Xurxogr")

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

    def test_uses_member_when_no_request(self) -> None:
        """Test that mention/username come from the member when there is no request."""
        member = MagicMock(id=789, display_name="Role Joiner")
        member.name = "rolejoiner"

        result = welcome_card.build_card_message(
            template="{user_mention} {username} {display_name}",
            request=None,
            member=member,
            name="Xurxogr",
            server_name="Guild",
        )

        assert result == "<@789> rolejoiner Role Joiner"


class TestShouldTriggerWelcomeCard:
    """Tests for should_trigger_welcome_card."""

    def test_no_required_roles_never_triggers(self) -> None:
        """Test that an empty required-role config never triggers."""
        assert (
            welcome_card.should_trigger_welcome_card(
                before_role_ids={1}, after_role_ids={1, 2}, required_role_ids=[]
            )
            is False
        )

    def test_completing_the_set_triggers(self) -> None:
        """Test that adding the last missing required role triggers."""
        assert (
            welcome_card.should_trigger_welcome_card(
                before_role_ids={10}, after_role_ids={10, 20}, required_role_ids=[10, 20]
            )
            is True
        )

    def test_already_complete_does_not_retrigger(self) -> None:
        """Test that a role change while already complete does not retrigger."""
        assert (
            welcome_card.should_trigger_welcome_card(
                before_role_ids={10, 20}, after_role_ids={10, 20, 30}, required_role_ids=[10, 20]
            )
            is False
        )

    def test_still_incomplete_does_not_trigger(self) -> None:
        """Test that adding a role that still leaves the set incomplete does not trigger."""
        assert (
            welcome_card.should_trigger_welcome_card(
                before_role_ids=set(), after_role_ids={10}, required_role_ids=[10, 20]
            )
            is False
        )

    def test_losing_a_required_role_does_not_trigger(self) -> None:
        """Test that removing a required role never triggers."""
        assert (
            welcome_card.should_trigger_welcome_card(
                before_role_ids={10, 20}, after_role_ids={10}, required_role_ids=[10, 20]
            )
            is False
        )


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


class TestLoadFont:
    """Tests for _load_font caching."""

    def test_same_size_returns_cached_font(self) -> None:
        """Test that repeated loads of the same size reuse one font object."""
        assert welcome_card._load_font(20) is welcome_card._load_font(20)


class TestRenderWelcomeCard:
    """Tests for render_welcome_card."""

    def test_does_not_mutate_global_pixel_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that rendering leaves Pillow's global pixel limit untouched."""
        sentinel = 123_456_789
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", sentinel)

        welcome_card.render_welcome_card(
            template_bytes=_make_template(),
            name="Xurxogr",
            box=(100, 150, 500, 250),
        )

        assert Image.MAX_IMAGE_PIXELS == sentinel

    def test_oversized_template_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a template above the pixel limit raises ValueError."""
        monkeypatch.setattr(welcome_card, "MAX_IMAGE_PIXELS", 1000)

        with pytest.raises(ValueError):
            welcome_card.render_welcome_card(
                template_bytes=_make_template(),
                name="Xurxogr",
                box=(100, 150, 500, 250),
            )

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


def _mock_client(handler: Any) -> httpx.AsyncClient:
    """Build an httpx client whose transport answers with the given handler.

    Args:
        handler (Any): Callable receiving the request and returning a response.

    Returns:
        httpx.AsyncClient: Client backed by a MockTransport.
    """
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _static_client(*responses: httpx.Response) -> httpx.AsyncClient:
    """Build a client answering the given responses in order (last one repeats).

    Args:
        *responses (httpx.Response): Responses to return, one per request.

    Returns:
        httpx.AsyncClient: Client backed by a MockTransport.
    """
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return _mock_client(handler)


class TestFetchTemplate:
    """Tests for fetch_template."""

    @pytest.fixture(autouse=True)
    def _fresh_cache(self) -> None:
        """Start every test with an empty template cache."""
        welcome_card.clear_template_cache()

    @pytest.mark.asyncio
    async def test_success_returns_bytes(self) -> None:
        """Test that a successful fetch returns the image bytes."""
        payload = _make_template()
        client = _static_client(
            httpx.Response(200, content=payload, headers={"content-type": "image/png"})
        )

        result = await welcome_card.fetch_template(url="https://example.com/t.png", client=client)

        assert result == payload

    @pytest.mark.asyncio
    async def test_non_200_returns_none(self) -> None:
        """Test that a non-200 response returns None."""
        client = _static_client(httpx.Response(404, content=b""))

        result = await welcome_card.fetch_template(url="https://example.com/t.png", client=client)

        assert result is None

    @pytest.mark.asyncio
    async def test_oversize_returns_none(self) -> None:
        """Test that an oversized payload returns None."""
        big = b"x" * (welcome_card.MAX_IMAGE_BYTES + 1)
        client = _static_client(httpx.Response(200, content=big))

        result = await welcome_card.fetch_template(url="https://example.com/t.png", client=client)

        assert result is None

    @pytest.mark.asyncio
    async def test_declared_oversize_is_rejected_before_reading_the_body(self) -> None:
        """A Content-Length above the limit is refused without downloading anything."""
        chunks_served = 0

        async def body() -> AsyncIterator[bytes]:
            nonlocal chunks_served
            for _ in range(3):
                chunks_served += 1
                yield b"x" * 1024

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=body(),
                headers={"content-length": str(welcome_card.MAX_IMAGE_BYTES + 1)},
            )

        result = await welcome_card.fetch_template(
            url="https://example.com/t.png", client=_mock_client(handler)
        )

        assert result is None
        assert chunks_served == 0

    @pytest.mark.asyncio
    async def test_unbounded_body_is_cut_off_at_the_limit(self) -> None:
        """Without Content-Length the download stops as soon as the limit is exceeded."""
        chunk = b"x" * (1024 * 1024)
        chunks_served = 0

        async def body() -> AsyncIterator[bytes]:
            nonlocal chunks_served
            for _ in range(20):
                chunks_served += 1
                yield chunk

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body())

        result = await welcome_card.fetch_template(
            url="https://example.com/t.png", client=_mock_client(handler)
        )

        assert result is None
        # 8 MiB fit, the 9th chunk crosses the limit; nothing more is pulled
        assert chunks_served <= welcome_card.MAX_IMAGE_BYTES // len(chunk) + 2

    @pytest.mark.asyncio
    async def test_request_error_returns_none(self) -> None:
        """Test that a transport error returns None."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        result = await welcome_card.fetch_template(
            url="https://example.com/t.png", client=_mock_client(handler)
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_same_url_is_fetched_once_within_ttl(self) -> None:
        """A second card for the same template reuses the downloaded bytes."""
        payload = _make_template()
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, content=payload)

        client = _mock_client(handler)

        first = await welcome_card.fetch_template(url="https://example.com/t.png", client=client)
        second = await welcome_card.fetch_template(url="https://example.com/t.png", client=client)

        assert first == second == payload
        assert calls == 1

    @pytest.mark.asyncio
    async def test_different_urls_are_cached_separately(self) -> None:
        """Each template URL is fetched and cached on its own."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=request.url.path.strip("/").encode())

        client = _mock_client(handler)

        first = await welcome_card.fetch_template(url="https://example.com/a", client=client)
        second = await welcome_card.fetch_template(url="https://example.com/b", client=client)

        assert (first, second) == (b"a", b"b")

    @pytest.mark.asyncio
    async def test_failed_fetch_is_retried_next_time(self) -> None:
        """A failed download is not cached, so the next card tries again."""
        payload = _make_template()
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(503, content=b"")
            return httpx.Response(200, content=payload)

        client = _mock_client(handler)

        first = await welcome_card.fetch_template(url="https://example.com/t.png", client=client)
        second = await welcome_card.fetch_template(url="https://example.com/t.png", client=client)

        assert first is None
        assert second == payload
        assert calls == 2

    @pytest.mark.asyncio
    async def test_default_client_is_shared_and_closable(self) -> None:
        """Without an explicit client, one shared client is reused until closed."""
        client = welcome_card.get_template_client()
        assert welcome_card.get_template_client() is client
        assert client.follow_redirects is True

        await welcome_card.close_template_client()

        assert client.is_closed
        assert welcome_card.get_template_client() is not client
        await welcome_card.close_template_client()


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
            member=MagicMock(id=456, display_name="Xurxogr"),
        )

        channel.send.assert_awaited_once()
        _, kwargs = channel.send.call_args
        assert kwargs["content"] == "Welcome <@456> to Test Guild!"
        assert "file" in kwargs

    @pytest.mark.asyncio
    async def test_render_runs_under_semaphore(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that rendering happens while the concurrency semaphore is held."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        guild = self._guild_with_channel(channel)
        monkeypatch.setattr(
            welcome_card, "fetch_template", AsyncMock(return_value=_make_template())
        )
        monkeypatch.setattr(welcome_card, "_RENDER_SEMAPHORE", asyncio.Semaphore(1))

        held: list[bool] = []

        def fake_render(**kwargs: object) -> bytes:
            held.append(welcome_card._RENDER_SEMAPHORE.locked())
            return _make_template()

        monkeypatch.setattr(welcome_card, "render_welcome_card", fake_render)

        await welcome_card.post_welcome_card(
            guild=guild,
            config=_valid_config(),
            request=_regular_request("X"),
            member=MagicMock(),
        )

        assert held == [True]

    @pytest.mark.asyncio
    async def test_posts_without_a_verification_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that the card posts for a plain role-completion trigger with no request."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        guild = self._guild_with_channel(channel)
        monkeypatch.setattr(
            welcome_card, "fetch_template", AsyncMock(return_value=_make_template())
        )

        await welcome_card.post_welcome_card(
            guild=guild,
            config=_valid_config(),
            member=MagicMock(id=456, display_name="Role Joiner", name="rolejoiner"),
        )

        channel.send.assert_awaited_once()
        _, kwargs = channel.send.call_args
        assert "file" in kwargs
