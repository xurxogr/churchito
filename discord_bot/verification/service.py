"""Service for user verification operations."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.verification.enums import VerificationStatus, VerificationType
from discord_bot.verification.models import VerificationRequest

logger = logging.getLogger(__name__)


class VerificationService:
    """Service for verification CRUD operations.

    Handles the creation, update and query of user
    verification requests.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the verification service.

        Args:
            session (AsyncSession): Database session
        """
        self._session = session

    async def create_request(
        self,
        guild_id: int,
        user_id: int,
        username: str,
        guild_name: str,
        verification_type: VerificationType,
    ) -> VerificationRequest:
        """Create a new verification request.

        Args:
            guild_id (int): Guild ID
            user_id (int): User ID
            username (str): Discord username
            guild_name (str): Guild name
            verification_type (VerificationType): Verification type

        Returns:
            VerificationRequest: Created request
        """
        request = VerificationRequest(
            guild_id=guild_id,
            user_id=user_id,
            username=username,
            verification_type=verification_type,
            status=VerificationStatus.PENDING_SCREENSHOTS,
        )
        self._session.add(request)
        await self._session.flush()
        logger.info(
            f"[{guild_name}] Verification request created: "
            f"{username}, type={verification_type} (ID: {request.id})"
        )
        return request

    async def get_request(self, request_id: int) -> VerificationRequest | None:
        """Get a request by ID.

        Args:
            request_id (int): Request ID

        Returns:
            VerificationRequest | None: Request or None if it doesn't exist
        """
        result = await self._session.execute(
            select(VerificationRequest).where(VerificationRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def get_by_public_id(self, public_id: str) -> VerificationRequest | None:
        """Get a request by public_id.

        Args:
            public_id (str): Public request ID (NanoID)

        Returns:
            VerificationRequest | None: Request or None if it doesn't exist
        """
        result = await self._session.execute(
            select(VerificationRequest).where(VerificationRequest.public_id == public_id)
        )
        return result.scalar_one_or_none()

    async def get_pending_by_user(self, guild_id: int, user_id: int) -> VerificationRequest | None:
        """Get pending request for a user.

        Searches for requests with PENDING_SCREENSHOTS or PENDING_REVIEW status.

        Args:
            guild_id (int): Guild ID
            user_id (int): User ID

        Returns:
            VerificationRequest | None: Pending request or None
        """
        result = await self._session.execute(
            select(VerificationRequest).where(
                VerificationRequest.guild_id == guild_id,
                VerificationRequest.user_id == user_id,
                VerificationRequest.status.in_(
                    [
                        VerificationStatus.PENDING_SCREENSHOTS,
                        VerificationStatus.PENDING_REVIEW,
                    ]
                ),
            )
        )
        return result.scalar_one_or_none()

    async def get_any_pending_by_user(self, user_id: int) -> VerificationRequest | None:
        """Get any pending request for a user in any guild.

        Searches for requests with PENDING_SCREENSHOTS status (awaiting screenshots).
        Useful for recovering verifications when the bot restarts.

        Args:
            user_id (int): User ID

        Returns:
            VerificationRequest | None: Pending request or None
        """
        result = await self._session.execute(
            select(VerificationRequest)
            .where(
                VerificationRequest.user_id == user_id,
                VerificationRequest.status == VerificationStatus.PENDING_SCREENSHOTS,
            )
            .order_by(VerificationRequest.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_all_pending_screenshots(self) -> list[VerificationRequest]:
        """Get all requests awaiting screenshots.

        Useful for restoring in-memory state when the bot restarts.

        Returns:
            list[VerificationRequest]: List of pending requests
        """
        result = await self._session.execute(
            select(VerificationRequest).where(
                VerificationRequest.status == VerificationStatus.PENDING_SCREENSHOTS,
            )
        )
        return list(result.scalars().all())

    async def get_all_pending(self) -> list[VerificationRequest]:
        """Get all pending requests (screenshots or review).

        Useful for cleaning up verifications from users who left the server.

        Returns:
            list[VerificationRequest]: List of pending requests
        """
        result = await self._session.execute(
            select(VerificationRequest).where(
                VerificationRequest.status.in_(
                    [
                        VerificationStatus.PENDING_SCREENSHOTS,
                        VerificationStatus.PENDING_REVIEW,
                    ]
                ),
            )
        )
        return list(result.scalars().all())

    async def get_pending_for_guild(self, guild_id: int) -> list[VerificationRequest]:
        """Get all pending requests for a guild.

        Includes both PENDING_SCREENSHOTS and PENDING_REVIEW.
        Ordered by creation date (oldest first).

        Args:
            guild_id (int): Guild ID

        Returns:
            list[VerificationRequest]: List of pending requests
        """
        result = await self._session.execute(
            select(VerificationRequest)
            .where(
                VerificationRequest.guild_id == guild_id,
                VerificationRequest.status.in_(
                    [
                        VerificationStatus.PENDING_SCREENSHOTS,
                        VerificationStatus.PENDING_REVIEW,
                    ]
                ),
            )
            .order_by(VerificationRequest.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_pending_with_mod_messages(self) -> list[VerificationRequest]:
        """Get pending requests that have a moderation message.

        Includes both PENDING_SCREENSHOTS and PENDING_REVIEW since the
        moderation message is created when the user starts verification.

        Returns:
            list[VerificationRequest]: List of requests with mod message
        """
        result = await self._session.execute(
            select(VerificationRequest).where(
                VerificationRequest.status.in_(
                    [
                        VerificationStatus.PENDING_SCREENSHOTS,
                        VerificationStatus.PENDING_REVIEW,
                    ]
                ),
                VerificationRequest.mod_message_id.isnot(None),
            )
        )
        return list(result.scalars().all())

    async def get_user_history(self, guild_id: int, user_id: int) -> list[VerificationRequest]:
        """Get verification history for a user.

        Args:
            guild_id (int): Guild ID
            user_id (int): User ID

        Returns:
            list[VerificationRequest]: List of all requests
        """
        result = await self._session.execute(
            select(VerificationRequest)
            .where(
                VerificationRequest.guild_id == guild_id,
                VerificationRequest.user_id == user_id,
            )
            .order_by(VerificationRequest.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_screenshots(
        self, request_id: int, url1: str, url2: str, guild_name: str
    ) -> VerificationRequest | None:
        """Update request with screenshots.

        Changes status to PENDING_REVIEW.

        Args:
            request_id (int): Request ID
            url1 (str): URL of the first screenshot
            url2 (str): URL of the second screenshot
            guild_name (str): Guild name

        Returns:
            VerificationRequest | None: Updated request or None
        """
        request = await self.get_request(request_id)
        if not request:
            return None

        request.screenshot_1_url = url1
        request.screenshot_2_url = url2
        request.status = VerificationStatus.PENDING_REVIEW
        request.screenshots_submitted_at = datetime.now(UTC)
        await self._session.flush()

        logger.info(f"[{guild_name}] Screenshots updated: {request.username} (ID: {request_id})")
        return request

    async def set_mod_message_id(
        self,
        request_id: int,
        message_id: int,
    ) -> None:
        """Save moderation message ID.

        Args:
            request_id (int): Request ID
            message_id (int): Message ID in the moderation channel
        """
        request = await self.get_request(request_id)
        if not request:
            return

        request.mod_message_id = message_id
        await self._session.flush()

    async def set_player_info(
        self,
        request_id: int,
        player_info: dict[str, str],
    ) -> None:
        """Save player information extracted by OCR.

        Args:
            request_id (int): Request ID
            player_info (dict[str, str]): Player data (name, regiment, level, etc.)
        """
        request = await self.get_request(request_id)
        if not request:
            return

        request.player_info = player_info
        await self._session.flush()

    async def approve(
        self,
        request_id: int,
        reviewer_id: int,
        reviewer_username: str,
        guild_name: str,
    ) -> VerificationRequest | None:
        """Approve a verification request.

        Args:
            request_id (int): Request ID
            reviewer_id (int): Moderator ID
            reviewer_username (str): Moderator name
            guild_name (str): Guild name

        Returns:
            VerificationRequest | None: Updated request or None
        """
        request = await self.get_request(request_id)
        if not request:
            return None

        request.status = VerificationStatus.APPROVED
        request.reviewed_by_id = reviewer_id
        request.reviewed_by_username = reviewer_username
        request.reviewed_at = datetime.now(UTC)
        await self._session.flush()

        logger.info(
            f"[{guild_name}] Request {request_id} approved: "
            f"user={request.username}, moderator={reviewer_username}"
        )
        return request

    async def reject(
        self,
        request_id: int,
        reviewer_id: int,
        reviewer_username: str,
        reason: str,
        guild_name: str,
    ) -> VerificationRequest | None:
        """Reject a verification request.

        Args:
            request_id (int): Request ID
            reviewer_id (int): Moderator ID
            reviewer_username (str): Moderator name
            reason (str): Rejection reason
            guild_name (str): Guild name

        Returns:
            VerificationRequest | None: Updated request or None
        """
        request = await self.get_request(request_id)
        if not request:
            return None

        request.status = VerificationStatus.REJECTED
        request.reviewed_by_id = reviewer_id
        request.reviewed_by_username = reviewer_username
        request.rejection_reason = reason
        request.reviewed_at = datetime.now(UTC)
        await self._session.flush()

        logger.info(
            f"[{guild_name}] Request {request_id} rejected: "
            f"user={request.username}, moderator={reviewer_username}, reason={reason}"
        )
        return request

    async def cancel(self, request_id: int, guild_name: str) -> VerificationRequest | None:
        """Cancel a verification request.

        Used when the user leaves the server.

        Args:
            request_id (int): Request ID
            guild_name (str): Guild name

        Returns:
            VerificationRequest | None: Updated request or None
        """
        request = await self.get_request(request_id)
        if not request:
            return None

        request.status = VerificationStatus.CANCELLED
        await self._session.flush()

        logger.info(f"[{guild_name}] Request {request_id} cancelled: user={request.username}")
        return request

    async def revert_to_pending_review(
        self, request_id: int, guild_name: str
    ) -> VerificationRequest | None:
        """Revert a rejected request to pending review.

        Used to allow manual review of auto-rejections.

        Args:
            request_id (int): Request ID
            guild_name (str): Guild name

        Returns:
            VerificationRequest | None: Updated request or None
        """
        request = await self.get_request(request_id)
        if not request:
            return None

        if request.status != VerificationStatus.REJECTED:
            return None

        request.status = VerificationStatus.PENDING_REVIEW
        request.reviewed_by_id = None
        request.reviewed_by_username = None
        request.rejection_reason = None
        request.reviewed_at = None
        await self._session.flush()

        logger.info(
            f"[{guild_name}] Request {request_id} reverted to pending review: "
            f"user={request.username}"
        )
        return request

    async def get_latest_by_user(self, guild_id: int, user_id: int) -> VerificationRequest | None:
        """Get the latest request from a user.

        Args:
            guild_id (int): Guild ID
            user_id (int): User ID

        Returns:
            VerificationRequest | None: Latest request or None
        """
        result = await self._session.execute(
            select(VerificationRequest)
            .where(
                VerificationRequest.guild_id == guild_id,
                VerificationRequest.user_id == user_id,
            )
            .order_by(VerificationRequest.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
