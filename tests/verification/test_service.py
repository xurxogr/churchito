"""Tests for VerificationService."""

from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.verification.enums import VerificationStatus, VerificationType
from discord_bot.verification.service import VerificationService


class TestVerificationService:
    """Tests for VerificationService."""

    async def test_create_request(self, test_session: AsyncSession) -> None:
        """Test request creation."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        assert request.id is not None
        assert request.guild_id == 123
        assert request.user_id == 456
        assert request.username == "TestUser"
        assert request.verification_type == VerificationType.REGULAR
        assert request.status == VerificationStatus.PENDING_SCREENSHOTS

    async def test_create_request_ally(self, test_session: AsyncSession) -> None:
        """Test ally request creation."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )

        assert request.verification_type == VerificationType.ALLY

    async def test_get_request(self, test_session: AsyncSession) -> None:
        """Test getting request by ID."""
        service = VerificationService(test_session)

        created = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        retrieved = await service.get_request(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.username == "TestUser"

    async def test_get_request_not_found(self, test_session: AsyncSession) -> None:
        """Test getting non-existent request."""
        service = VerificationService(test_session)
        result = await service.get_request(99999)
        assert result is None

    async def test_get_pending_by_user(self, test_session: AsyncSession) -> None:
        """Test getting pending request by user."""
        service = VerificationService(test_session)

        await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        pending = await service.get_pending_by_user(guild_id=123, user_id=456)
        assert pending is not None
        assert pending.user_id == 456

    async def test_get_pending_by_user_no_pending(self, test_session: AsyncSession) -> None:
        """Test getting pending request when there are none."""
        service = VerificationService(test_session)
        pending = await service.get_pending_by_user(guild_id=123, user_id=456)
        assert pending is None

    async def test_get_pending_by_user_ignores_completed(self, test_session: AsyncSession) -> None:
        """Test that get_pending_by_user ignores completed requests."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.approve(
            request_id=request.id,
            reviewer_id=789,
            reviewer_username="Mod",
            guild_name="Test Guild",
        )

        pending = await service.get_pending_by_user(guild_id=123, user_id=456)
        assert pending is None

    async def test_get_any_pending_by_user(self, test_session: AsyncSession) -> None:
        """Test getting any pending request from a user."""
        service = VerificationService(test_session)

        # Create request in a guild
        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        # Search without specifying guild
        pending = await service.get_any_pending_by_user(456)
        assert pending is not None
        assert pending.id == request.id
        assert pending.guild_id == 123

    async def test_get_any_pending_by_user_no_pending(self, test_session: AsyncSession) -> None:
        """Test get_any_pending_by_user when there are no pending requests."""
        service = VerificationService(test_session)
        pending = await service.get_any_pending_by_user(456)
        assert pending is None

    async def test_get_any_pending_by_user_ignores_pending_review(
        self, test_session: AsyncSession
    ) -> None:
        """Test that get_any_pending_by_user only returns PENDING_SCREENSHOTS."""
        service = VerificationService(test_session)

        # Create request and update to PENDING_REVIEW
        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.update_screenshots(
            request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
        )

        # Should not find because it already has screenshots (PENDING_REVIEW)
        pending = await service.get_any_pending_by_user(456)
        assert pending is None

    async def test_get_any_pending_by_user_returns_most_recent(
        self, test_session: AsyncSession
    ) -> None:
        """Test that get_any_pending_by_user returns the most recent."""
        service = VerificationService(test_session)

        # Create request in guild 111
        await service.create_request(
            guild_id=111,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        # Create request in guild 222 (more recent)
        request2 = await service.create_request(
            guild_id=222,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )

        pending = await service.get_any_pending_by_user(456)
        assert pending is not None
        assert pending.id == request2.id
        assert pending.guild_id == 222

    async def test_get_all_pending_screenshots(self, test_session: AsyncSession) -> None:
        """Test getting all requests awaiting screenshots."""
        service = VerificationService(test_session)

        # Create multiple requests
        await service.create_request(
            guild_id=111,
            user_id=456,
            username="User1",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.create_request(
            guild_id=222,
            user_id=789,
            username="User2",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )

        pending = await service.get_all_pending_screenshots()
        assert len(pending) == 2

    async def test_get_all_pending_screenshots_empty(self, test_session: AsyncSession) -> None:
        """Test get_all_pending_screenshots when there are no requests."""
        service = VerificationService(test_session)
        pending = await service.get_all_pending_screenshots()
        assert pending == []

    async def test_get_all_pending_screenshots_ignores_other_statuses(
        self, test_session: AsyncSession
    ) -> None:
        """Test that get_all_pending_screenshots ignores other statuses."""
        service = VerificationService(test_session)

        # Create request and approve it
        request1 = await service.create_request(
            guild_id=111,
            user_id=456,
            username="User1",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.approve(
            request_id=request1.id,
            reviewer_id=999,
            reviewer_username="Mod",
            guild_name="Test Guild",
        )

        # Create request and update to PENDING_REVIEW
        request2 = await service.create_request(
            guild_id=222,
            user_id=789,
            username="User2",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )
        await service.update_screenshots(
            request_id=request2.id, url1="url1", url2="url2", guild_name="Test Guild"
        )

        # Create request pending screenshots
        await service.create_request(
            guild_id=333,
            user_id=101,
            username="User3",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        pending = await service.get_all_pending_screenshots()
        assert len(pending) == 1
        assert pending[0].user_id == 101

    async def test_get_user_history(self, test_session: AsyncSession) -> None:
        """Test getting user history."""
        service = VerificationService(test_session)

        request1 = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.approve(
            request_id=request1.id,
            reviewer_id=789,
            reviewer_username="Mod",
            guild_name="Test Guild",
        )

        await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )

        history = await service.get_user_history(guild_id=123, user_id=456)
        assert len(history) == 2
        assert history[0].verification_type == VerificationType.ALLY
        assert history[1].verification_type == VerificationType.REGULAR

    async def test_get_user_history_empty(self, test_session: AsyncSession) -> None:
        """Test empty history."""
        service = VerificationService(test_session)
        history = await service.get_user_history(guild_id=123, user_id=456)
        assert history == []

    async def test_update_screenshots(self, test_session: AsyncSession) -> None:
        """Test updating screenshots."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        updated = await service.update_screenshots(
            request.id,
            "http://example.com/1.png",
            "http://example.com/2.png",
            "Test Guild",
        )

        assert updated is not None
        assert updated.screenshot_1_url == "http://example.com/1.png"
        assert updated.screenshot_2_url == "http://example.com/2.png"
        assert updated.status == VerificationStatus.PENDING_REVIEW
        assert updated.screenshots_submitted_at is not None

    async def test_update_screenshots_not_found(self, test_session: AsyncSession) -> None:
        """Test updating screenshots for non-existent request."""
        service = VerificationService(test_session)
        result = await service.update_screenshots(
            request_id=99999, url1="url1", url2="url2", guild_name="Test Guild"
        )
        assert result is None

    async def test_set_mod_message_id(self, test_session: AsyncSession) -> None:
        """Test saving moderation message ID."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        await service.set_mod_message_id(request_id=request.id, message_id=111)

        updated = await service.get_request(request.id)
        assert updated is not None
        assert updated.mod_message_id == 111

    async def test_set_mod_message_id_not_found(self, test_session: AsyncSession) -> None:
        """Test set_mod_message_id for non-existent request."""
        service = VerificationService(test_session)
        # Should not fail, just return without doing anything
        await service.set_mod_message_id(request_id=99999, message_id=111)

    async def test_approve(self, test_session: AsyncSession) -> None:
        """Test request approval."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        approved = await service.approve(
            request_id=request.id,
            reviewer_id=789,
            reviewer_username="ModUser",
            guild_name="Test Guild",
        )

        assert approved is not None
        assert approved.status == VerificationStatus.APPROVED
        assert approved.reviewed_by_id == 789
        assert approved.reviewed_by_username == "ModUser"
        assert approved.reviewed_at is not None

    async def test_approve_not_found(self, test_session: AsyncSession) -> None:
        """Test approving non-existent request."""
        service = VerificationService(test_session)
        result = await service.approve(
            request_id=99999,
            reviewer_id=789,
            reviewer_username="Mod",
            guild_name="Test Guild",
        )
        assert result is None

    async def test_reject(self, test_session: AsyncSession) -> None:
        """Test request rejection."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        rejected = await service.reject(
            request_id=request.id,
            reviewer_id=789,
            reviewer_username="ModUser",
            reason="Invalid screenshots",
            guild_name="Test Guild",
        )

        assert rejected is not None
        assert rejected.status == VerificationStatus.REJECTED
        assert rejected.reviewed_by_id == 789
        assert rejected.reviewed_by_username == "ModUser"
        assert rejected.rejection_reason == "Invalid screenshots"
        assert rejected.reviewed_at is not None

    async def test_reject_not_found(self, test_session: AsyncSession) -> None:
        """Test rejecting non-existent request."""
        service = VerificationService(test_session)
        result = await service.reject(
            request_id=99999,
            reviewer_id=789,
            reviewer_username="Mod",
            reason="reason",
            guild_name="Test Guild",
        )
        assert result is None

    async def test_cancel(self, test_session: AsyncSession) -> None:
        """Test request cancellation."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        cancelled = await service.cancel(request_id=request.id, guild_name="Test Guild")

        assert cancelled is not None
        assert cancelled.status == VerificationStatus.CANCELLED

    async def test_cancel_not_found(self, test_session: AsyncSession) -> None:
        """Test cancelling non-existent request."""
        service = VerificationService(test_session)
        result = await service.cancel(request_id=99999, guild_name="Test Guild")
        assert result is None

    async def test_different_guilds_isolated(self, test_session: AsyncSession) -> None:
        """Test that different guilds have isolated data."""
        service = VerificationService(test_session)

        await service.create_request(
            guild_id=111,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        await service.create_request(
            guild_id=222,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )

        pending_111 = await service.get_pending_by_user(guild_id=111, user_id=456)
        pending_222 = await service.get_pending_by_user(guild_id=222, user_id=456)

        assert pending_111 is not None
        assert pending_222 is not None
        assert pending_111.verification_type == VerificationType.REGULAR
        assert pending_222.verification_type == VerificationType.ALLY

    async def test_revert_to_pending_review(self, test_session: AsyncSession) -> None:
        """Test reverting rejected request to pending review."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        # Reject first
        await service.reject(
            request_id=request.id,
            reviewer_id=789,
            reviewer_username="Auto",
            reason="Automatic reason",
            guild_name="Test Guild",
        )

        # Revert to pending review
        reverted = await service.revert_to_pending_review(
            request_id=request.id, guild_name="Test Guild"
        )

        assert reverted is not None
        assert reverted.status == VerificationStatus.PENDING_REVIEW
        assert reverted.reviewed_by_id is None
        assert reverted.reviewed_by_username is None
        assert reverted.rejection_reason is None
        assert reverted.reviewed_at is None

    async def test_revert_to_pending_review_not_rejected(self, test_session: AsyncSession) -> None:
        """Test that cannot revert request that is not rejected."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        # Try to revert without rejecting first
        result = await service.revert_to_pending_review(
            request_id=request.id, guild_name="Test Guild"
        )

        assert result is None

    async def test_revert_to_pending_review_not_found(self, test_session: AsyncSession) -> None:
        """Test reverting non-existent request."""
        service = VerificationService(test_session)
        result = await service.revert_to_pending_review(request_id=99999, guild_name="Test Guild")
        assert result is None

    async def test_get_latest_by_user(self, test_session: AsyncSession) -> None:
        """Test getting latest request from a user."""
        service = VerificationService(test_session)

        # Create first request
        request1 = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.cancel(request_id=request1.id, guild_name="Test Guild")

        # Create second request
        request2 = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )

        latest = await service.get_latest_by_user(guild_id=123, user_id=456)

        assert latest is not None
        assert latest.id == request2.id
        assert latest.verification_type == VerificationType.ALLY

    async def test_get_latest_by_user_not_found(self, test_session: AsyncSession) -> None:
        """Test getting latest request from user with no requests."""
        service = VerificationService(test_session)
        result = await service.get_latest_by_user(guild_id=123, user_id=456)
        assert result is None

    async def test_get_pending_with_mod_messages(self, test_session: AsyncSession) -> None:
        """Test getting pending requests with moderation message."""
        service = VerificationService(test_session)

        # Create request with mod_message_id and PENDING_REVIEW status
        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.update_screenshots(
            request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
        )
        await service.set_mod_message_id(request_id=request.id, message_id=789)

        pending = await service.get_pending_with_mod_messages()
        assert len(pending) == 1
        assert pending[0].mod_message_id == 789

    async def test_get_pending_with_mod_messages_empty(self, test_session: AsyncSession) -> None:
        """Test get_pending_with_mod_messages when there are no requests."""
        service = VerificationService(test_session)
        pending = await service.get_pending_with_mod_messages()
        assert pending == []

    async def test_get_pending_with_mod_messages_ignores_without_mod_message(
        self, test_session: AsyncSession
    ) -> None:
        """Test that ignores requests without mod_message_id."""
        service = VerificationService(test_session)

        # Create request without mod_message_id
        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.update_screenshots(
            request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
        )
        # Do not set mod_message_id

        pending = await service.get_pending_with_mod_messages()
        assert pending == []

    async def test_get_pending_with_mod_messages_includes_pending_screenshots(
        self, test_session: AsyncSession
    ) -> None:
        """Test that includes requests in PENDING_SCREENSHOTS status with mod_message."""
        service = VerificationService(test_session)

        # Create request in PENDING_SCREENSHOTS with mod_message_id
        # (the mod message is created when the user starts verification)
        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.set_mod_message_id(request_id=request.id, message_id=789)
        # Do not update screenshots, stays in PENDING_SCREENSHOTS

        pending = await service.get_pending_with_mod_messages()
        assert len(pending) == 1
        assert pending[0].mod_message_id == 789
        assert pending[0].status == VerificationStatus.PENDING_SCREENSHOTS

    async def test_get_pending_with_mod_messages_ignores_approved(
        self, test_session: AsyncSession
    ) -> None:
        """Test that ignores approved requests."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.update_screenshots(
            request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
        )
        await service.set_mod_message_id(request_id=request.id, message_id=789)
        await service.approve(
            request_id=request.id,
            reviewer_id=999,
            reviewer_username="Mod",
            guild_name="Test Guild",
        )

        pending = await service.get_pending_with_mod_messages()
        assert pending == []

    async def test_set_player_info(self, test_session: AsyncSession) -> None:
        """Test saving player information."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        player_info = {"name": "TestPlayer", "level": "25", "regiment": "TestReg"}
        await service.set_player_info(request_id=request.id, player_info=player_info)

        updated = await service.get_request(request.id)
        assert updated is not None
        assert updated.player_info == player_info

    async def test_set_player_info_not_found(self, test_session: AsyncSession) -> None:
        """Test set_player_info for non-existent request."""
        service = VerificationService(test_session)
        # Should not fail, just return without doing anything
        await service.set_player_info(request_id=99999, player_info={"name": "Test"})
