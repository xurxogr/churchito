"""Client for external verification API."""

import asyncio
import logging
import time

import httpx

from discord_bot.common.utils.shared_http_client import SharedAsyncClient
from discord_bot.verification.models import VerificationAPIResponse, VerificationAPIResult

logger = logging.getLogger(__name__)

# Screenshots above this size are rejected before reaching the OCR API
MAX_IMAGE_BYTES = 25 * 1024 * 1024

# Bound concurrent verifications: each one buffers two screenshots plus the
# multipart body, so a burst must not stack them all in memory at once
_API_SEMAPHORE = asyncio.Semaphore(2)

_shared_client = SharedAsyncClient()


def _get_client() -> httpx.AsyncClient:
    """Return the shared HTTP client, creating it on first use.

    Returns:
        httpx.AsyncClient: Shared client with a reusable connection pool.
    """
    return _shared_client.client()


async def close_client() -> None:
    """Close the shared HTTP client, if one was created."""
    await _shared_client.aclose()


async def _download_screenshot(
    client: httpx.AsyncClient,
    url: str,
    label: str,
    timeout_seconds: int,
) -> bytes | VerificationAPIResult:
    """Download one screenshot, aborting as soon as it exceeds the size cap.

    Streaming keeps an oversized body from being buffered whole in memory:
    the declared length is refused from the headers when possible and the
    read stops at the limit otherwise.

    Args:
        client (httpx.AsyncClient): Shared HTTP client.
        url (str): Image URL (Discord CDN).
        label (str): Image label for error messages (e.g., "image 1").
        timeout_seconds (int): Timeout in seconds.

    Returns:
        bytes | VerificationAPIResult: Image bytes, or the failure result to return.
    """
    async with client.stream("GET", url, timeout=timeout_seconds) as response:
        if response.status_code != 200:
            return VerificationAPIResult(
                success=False,
                status_code=response.status_code,
                error_message=f"Failed to download {label}",
            )

        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
            return VerificationAPIResult(
                success=False,
                status_code=0,
                error_message=f"{label.capitalize()} too large ({declared} bytes)",
            )

        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > MAX_IMAGE_BYTES:
                return VerificationAPIResult(
                    success=False,
                    status_code=0,
                    error_message=f"{label.capitalize()} too large (>{MAX_IMAGE_BYTES} bytes)",
                )
            chunks.append(chunk)
        return b"".join(chunks)


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
        url (str): Verification endpoint URL.
        api_key (str | None): API key (optional).
        image1_url (str): URL of the first image (Discord CDN).
        image2_url (str): URL of the second image (Discord CDN).
        timeout_seconds (int): Timeout in seconds.
        guild_name (str): Guild name for logs.

    Returns:
        VerificationAPIResult: API call result with success status and response data.
    """
    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        async with _API_SEMAPHORE:
            client = _get_client()

            # Download images from Discord CDN in parallel, stopping each
            # download at the size limit instead of buffering it whole
            t0 = time.perf_counter()
            download1, download2 = await asyncio.gather(
                _download_screenshot(
                    client=client,
                    url=image1_url,
                    label="image 1",
                    timeout_seconds=timeout_seconds,
                ),
                _download_screenshot(
                    client=client,
                    url=image2_url,
                    label="image 2",
                    timeout_seconds=timeout_seconds,
                ),
            )
            t1 = time.perf_counter()
            logger.debug(f"[{guild_name}] Images downloaded in {t1 - t0:.2f}s")

            if isinstance(download1, VerificationAPIResult):
                return download1
            if isinstance(download2, VerificationAPIResult):
                return download2
            image1_data = download1
            image2_data = download2

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
                timeout=timeout_seconds,
            )
            t3 = time.perf_counter()
            logger.debug(f"[{guild_name}] OCR API call took {t3 - t2:.2f}s")

            status_code = response.status_code

            if status_code == 200:
                data = response.json()
                return VerificationAPIResult(
                    success=True,
                    status_code=status_code,
                    response=VerificationAPIResponse.model_validate(data),
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
