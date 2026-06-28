"""Welcome card rendering and posting for approved verifications.

Renders the approved member's name onto a guild-provided template image and
posts it to a configured channel. Everything here is best-effort: any failure
is logged and swallowed so it can never block or break the approval flow.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from typing import TYPE_CHECKING, Any

import discord
import httpx
from PIL import Image, ImageDraw, ImageFont

from discord_bot.verification.enums import ConfigKey, VerificationType

if TYPE_CHECKING:
    from discord_bot.verification.models import VerificationRequest

logger = logging.getLogger(__name__)

# Name source choices (stored in config as plain strings)
NAME_SOURCE_IN_GAME = "in_game"
NAME_SOURCE_DISPLAY = "display"
NAME_SOURCE_USERNAME = "username"

# Safety limits (template images are fetched from an admin-supplied URL)
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 6000 * 6000

# Rendering bounds
MAX_NAME_LENGTH = 100
DEFAULT_MAX_FONT_SIZE = 120
MIN_FONT_SIZE = 8
DEFAULT_COLOR = (0, 0, 0)
OUTPUT_FILENAME = "welcome.png"

# Bundled with Pillow; covers Latin text including accents (e.g. "Lázaro").
_FONT_NAME = "DejaVuSans.ttf"

_CONTROL_CHARS = re.compile(r"\s+")


def resolve_card_name(
    *,
    request: VerificationRequest,
    member: discord.Member | None,
    name_source: str,
) -> str:
    """Pick the name to write on the card.

    Three sources are supported:
        - "in_game" (default): the OCR Foxhole name from the verification
          screenshot (``player_info["name"]``), falling back to the Discord
          username if no OCR data is present.
        - "display": the member's server display name (nick / global / username).
        - "username": the raw Discord username (@handle, lowercase).

    Args:
        request (VerificationRequest): Verification request.
        member (discord.Member | None): Approved member, if still in the guild.
        name_source (str): One of "in_game", "display" or "username".

    Returns:
        str: The chosen, sanitized name.
    """
    if name_source == NAME_SOURCE_DISPLAY and member is not None:
        return sanitize_name(member.display_name)
    if name_source == NAME_SOURCE_USERNAME:
        return sanitize_name(request.username)
    # Default / "in_game": OCR Foxhole name, fall back to the Discord username.
    return sanitize_name(_in_game_name(request) or request.username)


def _in_game_name(request: VerificationRequest) -> str | None:
    """Read the OCR-extracted in-game name from the request, if present.

    Args:
        request (VerificationRequest): Verification request.

    Returns:
        str | None: The in-game name, or None if no usable OCR data exists.
    """
    info = getattr(request, "player_info", None)
    if isinstance(info, dict):
        name = info.get("name")
        if isinstance(name, str) and name.strip():
            return name
    return None


def sanitize_name(name: str) -> str:
    """Collapse whitespace and clamp the name length.

    Args:
        name (str): Raw name.

    Returns:
        str: Cleaned name safe to draw.
    """
    cleaned = _CONTROL_CHARS.sub(" ", name).strip()
    return cleaned[:MAX_NAME_LENGTH]


def parse_box(config: dict[str, Any]) -> tuple[int, int, int, int] | None:
    """Read and validate the text box coordinates from config.

    Args:
        config (dict[str, Any]): Cog configuration.

    Returns:
        tuple[int, int, int, int] | None: (x1, y1, x2, y2), or None if invalid.
    """
    x1 = config.get(ConfigKey.WELCOME_CARD_BOX_X1)
    y1 = config.get(ConfigKey.WELCOME_CARD_BOX_Y1)
    x2 = config.get(ConfigKey.WELCOME_CARD_BOX_X2)
    y2 = config.get(ConfigKey.WELCOME_CARD_BOX_Y2)

    if (
        not isinstance(x1, int)
        or not isinstance(y1, int)
        or not isinstance(x2, int)
        or not isinstance(y2, int)
    ):
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def parse_color(value: str | None) -> tuple[int, int, int]:
    """Parse a hex color into an RGB tuple, defaulting to black.

    Args:
        value (str | None): Hex color (#RRGGBB or RRGGBB).

    Returns:
        tuple[int, int, int]: RGB tuple.
    """
    if not value:
        return DEFAULT_COLOR
    hex_color = value.strip().lstrip("#")
    if len(hex_color) != 6:
        return DEFAULT_COLOR
    try:
        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )
    except ValueError:
        return DEFAULT_COLOR


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the rendering font at the requested size.

    Args:
        size (int): Font size in points.

    Returns:
        ImageFont.FreeTypeFont | ImageFont.ImageFont: Loaded font.
    """
    try:
        return ImageFont.truetype(_FONT_NAME, size=size)
    except OSError:
        # Fallback: scalable default font (Pillow >= 10.1).
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    box_width: int,
    box_height: int,
    max_font_size: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Find the largest font size whose text fits inside the box.

    Args:
        draw (ImageDraw.ImageDraw): Drawing context for measuring.
        text (str): Text to render.
        box_width (int): Available width in pixels.
        box_height (int): Available height in pixels.
        max_font_size (int): Upper bound for the font size.

    Returns:
        ImageFont.FreeTypeFont | ImageFont.ImageFont: Best-fitting font.
    """
    size = max(max_font_size, MIN_FONT_SIZE)
    font = _load_font(size)
    while size > MIN_FONT_SIZE:
        font = _load_font(size)
        left, top, right, bottom = draw.textbbox((0, 0), text or " ", font=font)
        if (right - left) <= box_width and (bottom - top) <= box_height:
            break
        size -= 2
    return font


def render_welcome_card(
    *,
    template_bytes: bytes,
    name: str,
    box: tuple[int, int, int, int],
    color: tuple[int, int, int] = DEFAULT_COLOR,
    max_font_size: int = DEFAULT_MAX_FONT_SIZE,
) -> bytes:
    """Render the name centered inside the box on the template image.

    Args:
        template_bytes (bytes): Source template image bytes.
        name (str): Name to draw.
        box (tuple[int, int, int, int]): Text rectangle (x1, y1, x2, y2).
        color (tuple[int, int, int]): Text RGB color.
        max_font_size (int): Maximum font size; shrinks to fit.

    Returns:
        bytes: PNG-encoded rendered image.

    Raises:
        ValueError: If the template exceeds the pixel safety limit.
    """
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    with Image.open(io.BytesIO(template_bytes)) as source:
        image = source.convert("RGBA")

    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    box_width = x2 - x1
    box_height = y2 - y1

    font = _fit_font(
        draw=draw,
        text=name,
        box_width=box_width,
        box_height=box_height,
        max_font_size=max_font_size,
    )

    # Center the text within the box using its measured bounding box.
    left, top, right, bottom = draw.textbbox((0, 0), name or " ", font=font)
    text_width = right - left
    text_height = bottom - top
    pos_x = x1 + (box_width - text_width) / 2 - left
    pos_y = y1 + (box_height - text_height) / 2 - top
    if name:
        draw.text((pos_x, pos_y), name, font=font, fill=color)

    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def fetch_template(
    *,
    url: str,
    client: httpx.AsyncClient | None = None,
) -> bytes | None:
    """Fetch a template image from a URL with size validation.

    Args:
        url (str): Template image URL.
        client (httpx.AsyncClient | None): Optional client (for testing/reuse).

    Returns:
        bytes | None: Image bytes, or None on any failure.
    """
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
    try:
        response = await http.get(url)
        if response.status_code != 200:
            logger.warning(f"Welcome card template fetch returned {response.status_code}: {url}")
            return None
        content = response.content
        if len(content) > MAX_IMAGE_BYTES:
            logger.warning(f"Welcome card template too large ({len(content)} bytes): {url}")
            return None
        return content
    except Exception as exc:
        logger.warning(f"Failed to fetch welcome card template {url}: {exc}")
        return None
    finally:
        if owns_client:
            await http.aclose()


async def post_welcome_card(
    *,
    guild: discord.Guild,
    config: dict[str, Any],
    request: VerificationRequest,
    member: discord.Member | None,
) -> None:
    """Render and post the welcome card for an approved regular member.

    Only regular (member) verifications produce a card; ally verifications are
    skipped. Best-effort: any misconfiguration or failure is logged and swallowed
    so the approval flow is never affected.

    Args:
        guild (discord.Guild): Guild where the approval happened.
        config (dict[str, Any]): Cog configuration.
        request (VerificationRequest): Approved verification request.
        member (discord.Member | None): Approved member, if still present.
    """
    try:
        # The welcome card is only posted for regular members, not allies.
        if request.verification_type != VerificationType.REGULAR:
            return

        if not config.get(ConfigKey.WELCOME_CARD_ENABLED):
            return

        channel_id = config.get(ConfigKey.WELCOME_CARD_CHANNEL)
        template_url = config.get(ConfigKey.WELCOME_CARD_TEMPLATE_URL)
        box = parse_box(config)
        if not channel_id or not template_url or box is None:
            logger.debug(f"[{guild.name}] Welcome card enabled but not fully configured")
            return

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            logger.warning(f"[{guild.name}] Welcome card channel {channel_id} not found")
            return

        template_bytes = await fetch_template(url=template_url)
        if template_bytes is None:
            return

        name_source = config.get(ConfigKey.WELCOME_CARD_NAME_SOURCE) or NAME_SOURCE_IN_GAME
        name = resolve_card_name(request=request, member=member, name_source=name_source)
        color = parse_color(config.get(ConfigKey.WELCOME_CARD_FONT_COLOR))
        max_font_size = config.get(ConfigKey.WELCOME_CARD_MAX_FONT_SIZE) or DEFAULT_MAX_FONT_SIZE

        # Pillow is synchronous and CPU-bound; keep the event loop responsive.
        image_bytes = await asyncio.to_thread(
            render_welcome_card,
            template_bytes=template_bytes,
            name=name,
            box=box,
            color=color,
            max_font_size=max_font_size,
        )

        file = discord.File(io.BytesIO(image_bytes), filename=OUTPUT_FILENAME)
        await channel.send(file=file)
    except Exception as exc:
        logger.exception(f"[{guild.name}] Failed to post welcome card: {exc}")
