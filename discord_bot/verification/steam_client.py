"""Client for checking Steam profile privacy status."""

import logging
import re

import httpx

from discord_bot.verification.models import SteamProfileCheckResult

logger = logging.getLogger(__name__)

# Valid domain for Steam profile URLs
STEAM_PROFILE_DOMAIN = "steamcommunity.com"

# Valid path shapes: /id/<vanity> or /profiles/<steamid64>
STEAM_PROFILE_URL_PATTERN = re.compile(
    r"\Ahttps://steamcommunity\.com/(id/[A-Za-z0-9_-]{2,64}|profiles/\d{17})/?\Z"
)

_PRIVACY_STATE_PATTERN = re.compile(r"<privacyState>(.*?)</privacyState>")

_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 3


def get_steam_profile_display_id(url: str) -> str | None:
    """Extract the vanity name or SteamID64 from a Steam profile URL for display.

    Args:
        url (str): Steam profile URL.

    Returns:
        str | None: The vanity name or SteamID64 (without the "id/" or "profiles/"
            prefix), or None if the URL isn't a valid Steam profile URL.
    """
    if not url:
        return None

    match = STEAM_PROFILE_URL_PATTERN.match(url)
    if not match:
        return None

    return match.group(1).split("/", 1)[1]


def is_valid_steam_profile_url(url: str) -> bool:
    """Verify that a URL is a valid Steam community profile URL.

    Args:
        url (str): URL to verify.

    Returns:
        bool: True if it is a valid Steam profile URL.
    """
    if not url:
        return False

    return bool(STEAM_PROFILE_URL_PATTERN.match(url))


async def check_steam_profile_private(
    url: str,
    timeout_seconds: int = 15,
    guild_name: str = "Unknown",
) -> SteamProfileCheckResult:
    """Check whether a Steam profile is public or private.

    Args:
        url (str): Steam profile URL to check.
        timeout_seconds (int): Timeout in seconds.
        guild_name (str): Guild name for logs.

    Returns:
        SteamProfileCheckResult: Result of the privacy check.
    """
    if not is_valid_steam_profile_url(url):
        return SteamProfileCheckResult(
            success=False,
            error_message="Invalid Steam profile URL",
        )

    current_url = f"{url.rstrip('/')}/?xml=1"

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                response = await client.get(current_url)

                if response.status_code not in _REDIRECT_STATUS_CODES:
                    break

                location = response.headers.get("location")
                if not location:
                    break

                next_url = httpx.URL(location, base=response.url)
                if next_url.scheme != "https" or next_url.host != STEAM_PROFILE_DOMAIN:
                    return SteamProfileCheckResult(
                        success=False,
                        error_message="Redirected outside of the allowed domain",
                    )
                current_url = str(next_url)
            else:
                return SteamProfileCheckResult(
                    success=False,
                    error_message="Too many redirects",
                )

            if response.url.host != STEAM_PROFILE_DOMAIN:
                return SteamProfileCheckResult(
                    success=False,
                    error_message="Redirected outside of the allowed domain",
                )

            if response.status_code != 200:
                return SteamProfileCheckResult(
                    success=False,
                    error_message=f"Failed to fetch Steam profile (HTTP {response.status_code})",
                )

            match = _PRIVACY_STATE_PATTERN.search(response.text)
            if not match:
                return SteamProfileCheckResult(
                    success=False,
                    error_message="Could not determine profile privacy state",
                )

            is_private = match.group(1).strip().lower() != "public"
            return SteamProfileCheckResult(success=True, is_private=is_private)

    except httpx.HTTPError as e:
        logger.error(f"[{guild_name}] Error checking Steam profile: {e}")
        return SteamProfileCheckResult(success=False, error_message=str(e))
    except Exception as e:
        logger.exception(f"[{guild_name}] Unexpected error checking Steam profile: {e}")
        return SteamProfileCheckResult(success=False, error_message=str(e))
