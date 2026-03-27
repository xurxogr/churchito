"""Client for external verification API."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class VerificationAPIResponse:
    """Verification API response."""

    name: str
    level: int
    regiment: str
    faction: str  # 'colonial' or 'wardens'
    shard: str  # 'ABLE' or 'CHARLIE'
    ingame_time: str  # "268, 07:41"
    war: int
    current_ingame_time: str  # "278, 08:34"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationAPIResponse":
        """Create instance from dictionary."""
        return cls(
            name=data.get("name", ""),
            level=data.get("level", 0),
            regiment=data.get("regiment", ""),
            faction=data.get("faction", ""),
            shard=data.get("shard", ""),
            ingame_time=data.get("ingame_time", ""),
            war=data.get("war", 0),
            current_ingame_time=data.get("current_ingame_time", ""),
        )


@dataclass
class VerificationAPIResult:
    """Verification API call result."""

    success: bool
    status_code: int
    response: VerificationAPIResponse | None = None
    error_message: str | None = None


async def call_verification_api(
    url: str,
    api_key: str | None,
    image1_url: str,
    image2_url: str,
    timeout_seconds: int = 30,
    guild_name: str = "Unknown",
) -> VerificationAPIResult:
    """Call the verification API with the images.

    Args:
        url: Verification endpoint URL
        api_key: API key (optional)
        image1_url: URL of the first image (Discord CDN)
        image2_url: URL of the second image (Discord CDN)
        timeout_seconds: Timeout in seconds
        guild_name: Guild name for logs

    Returns:
        VerificationAPIResult with the call result
    """
    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            # Download images from Discord CDN in parallel
            t0 = time.perf_counter()
            resp1, resp2 = await asyncio.gather(
                client.get(image1_url),
                client.get(image2_url),
            )
            t1 = time.perf_counter()
            logger.debug(f"[{guild_name}] Images downloaded in {t1 - t0:.2f}s")

            if resp1.status_code != 200:
                return VerificationAPIResult(
                    success=False,
                    status_code=resp1.status_code,
                    error_message="Failed to download image 1",
                )
            image1_data = resp1.content

            if resp2.status_code != 200:
                return VerificationAPIResult(
                    success=False,
                    status_code=resp2.status_code,
                    error_message="Failed to download image 2",
                )
            image2_data = resp2.content

            logger.debug(
                f"[{guild_name}] Image sizes: "
                f"{len(image1_data) / 1024:.1f}KB, {len(image2_data) / 1024:.1f}KB"
            )

            # Create multipart form data
            files = {
                "image1": ("screenshot1.png", image1_data, "image/png"),
                "image2": ("screenshot2.png", image2_data, "image/png"),
            }

            # POST to verification API
            t2 = time.perf_counter()
            response = await client.post(
                url,
                files=files,
                headers=headers,
            )
            t3 = time.perf_counter()
            logger.debug(f"[{guild_name}] OCR API call took {t3 - t2:.2f}s")

            status_code = response.status_code

            if status_code == 200:
                data = response.json()
                return VerificationAPIResult(
                    success=True,
                    status_code=status_code,
                    response=VerificationAPIResponse.from_dict(data),
                )
            else:
                error_text = response.text
                return VerificationAPIResult(
                    success=False,
                    status_code=status_code,
                    error_message=error_text[:500],
                )

    except httpx.HTTPError as e:
        logger.error(f"[{guild_name}] Error calling verification API: {e}")
        return VerificationAPIResult(
            success=False,
            status_code=0,
            error_message=str(e),
        )
    except Exception as e:
        logger.exception(f"[{guild_name}] Unexpected error calling verification API: {e}")
        return VerificationAPIResult(
            success=False,
            status_code=0,
            error_message=str(e),
        )
