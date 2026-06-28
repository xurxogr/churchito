"""Tests for VerificationCog."""

from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_bot.bot import DiscordBot
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.database import DatabaseService
from discord_bot.common.utils import delete_message, has_any_role
from discord_bot.verification.cog import VerificationCog
from discord_bot.verification.enums import ConfigKey, VerificationStatus, VerificationType
from discord_bot.verification.service import VerificationService


class AsyncIteratorMock:
    """Mock for async iterators like channel.history()."""

    def __init__(self, items: list[Any]) -> None:  # noqa: D107
        self.items = items

    def __aiter__(self) -> "AsyncIteratorMock":  # noqa: D105
        self._index = 0
        return self

    async def __anext__(self) -> Any:  # noqa: D105
        if self._index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self._index]
        self._index += 1
        return item


@pytest.fixture
def mock_discord_bot(test_database: DatabaseService) -> MagicMock:
    """Create mock bot with database."""
    bot = MagicMock(spec=DiscordBot)
    bot.database = test_database
    bot.guilds = []
    bot.add_view = MagicMock()
    bot.get_guild = MagicMock(return_value=None)
    bot.wait_until_ready = AsyncMock()
    # Mock settings for verification API
    bot.settings = MagicMock()
    bot.settings.verification = MagicMock()
    bot.settings.verification.api_url = ""
    bot.settings.verification.api_key = ""
    bot.settings.verification.api_timeout = 30
    return bot


@pytest.fixture
def verification_cog(mock_discord_bot: MagicMock) -> VerificationCog:
    """Create cog instance for tests."""
    cog = VerificationCog(mock_discord_bot)
    # Mock _is_cog_enabled to return True by default (cogs are disabled by default now)
    object.__setattr__(cog, "_is_cog_enabled", AsyncMock(return_value=True))
    return cog


class TestFormatMessage:
    """Tests for _format_message."""

    def test_format_all_placeholders(self, verification_cog: VerificationCog) -> None:
        """Test replacement of all placeholders."""
        template = (
            "Hello {username}! Welcome to {server_name}."
            "Your verification ({verification_type}) was {reason}."
            "Mention: {user_mention}"
        )

        result = verification_cog._format_message(
            template,
            username="TestUser",
            user_mention="<@123>",
            server_name="My Server",
            verification_type="Normal",
            reason="approved",
        )

        assert result == (
            "Hello TestUser! Welcome to My Server."
            "Your verification (Normal) was approved."
            "Mention: <@123>"
        )

    def test_format_ally_type(self, verification_cog: VerificationCog) -> None:
        """Test that verification_type is used correctly."""
        template = "Type: {verification_type}"
        result = verification_cog._format_message(template, verification_type="Ally")
        assert result == "Type: Ally"

    def test_format_regular_type(self, verification_cog: VerificationCog) -> None:
        """Test that verification_type is used correctly."""
        template = "Type: {verification_type}"
        result = verification_cog._format_message(template, verification_type="Normal")
        assert result == "Type: Normal"

    def test_format_empty_placeholders(self, verification_cog: VerificationCog) -> None:
        """Test with placeholder passed as None."""
        template = "User: {username}"
        result = verification_cog._format_message(template, username=None)
        assert result == "User: "

    def test_format_unmatched_placeholder(self, verification_cog: VerificationCog) -> None:
        """Test that placeholders not passed are kept as is."""
        template = "User: {username}"
        result = verification_cog._format_message(template)
        assert result == "User: {username}"

    def test_format_no_placeholders(self, verification_cog: VerificationCog) -> None:
        """Test message without placeholders."""
        template = "Simple message without placeholders"
        result = verification_cog._format_message(template)
        assert result == template

    def test_format_dynamic_kwargs(self, verification_cog: VerificationCog) -> None:
        """Test that accepts any dynamic placeholder."""
        template = "Status: {status}, Moderator: {moderator}"
        result = verification_cog._format_message(template, status="Approved", moderator="Admin")
        assert result == "Status: Approved, Moderator: Admin"


class TestHasAnyRole:
    """Tests for has_any_role utility."""

    def test_has_any_role_with_matching_role(self) -> None:
        """Test with matching role."""
        member = MagicMock(spec=discord.Member)
        role1 = MagicMock(spec=discord.Role)
        role1.id = 111
        role2 = MagicMock(spec=discord.Role)
        role2.id = 222
        member.roles = [role1, role2]

        result = has_any_role(member=member, role_ids=[222, 333])
        assert result is True

    def test_has_any_role_without_matching_role(self) -> None:
        """Test without matching role."""
        member = MagicMock(spec=discord.Member)
        role1 = MagicMock(spec=discord.Role)
        role1.id = 111
        member.roles = [role1]

        result = has_any_role(member=member, role_ids=[222, 333])
        assert result is False

    def test_has_any_role_empty_list_with_permission(self) -> None:
        """Test empty list - uses manage_guild permissions."""
        member = MagicMock(spec=discord.Member)
        member.guild_permissions = MagicMock()
        member.guild_permissions.manage_guild = True

        result = has_any_role(member=member, role_ids=[])
        assert result is True

    def test_has_any_role_empty_list_without_permission(self) -> None:
        """Test empty list without permissions."""
        member = MagicMock(spec=discord.Member)
        member.guild_permissions = MagicMock()
        member.guild_permissions.manage_guild = False

        result = has_any_role(member=member, role_ids=[])
        assert result is False


class TestHandleVerificationStart:
    """Tests for handle_verification_start."""

    async def test_no_guild(self, verification_cog: VerificationCog) -> None:
        """Test without guild."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None

        await verification_cog.handle_verification_start(
            interaction=interaction, verification_type=VerificationType.REGULAR
        )

        # Should not do anything
        interaction.response.defer.assert_not_called()

    async def test_already_pending(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test with already pending verification."""
        # Create pending request using the same database as the cog
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()

        # Mock interaction
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.guild.name = "Test Guild"
        interaction.user = MagicMock(spec=discord.User)
        interaction.user.id = 456
        interaction.user.name = "TestUser"
        interaction.user.display_name = "TestUser"
        interaction.user.mention = "<@456>"
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = {
                "already_pending_message": "You already have a pending request.",
                "verification_type_regular_display": "Normal",
            }

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            interaction.followup.send.assert_called_once()
            call_args = interaction.followup.send.call_args
            assert "pending" in call_args[0][0].lower()

    async def test_pending_in_other_server(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test with pending verification in another server."""
        # Create pending request in guild 111
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.create_request(
                guild_id=111,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()

        # Try to verify in guild 222
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 222  # Different guild
        interaction.guild.name = "Other Guild"
        interaction.user = MagicMock(spec=discord.User)
        interaction.user.id = 456  # Same user
        interaction.user.name = "TestUser"
        interaction.user.display_name = "TestUser"
        interaction.user.mention = "<@456>"
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = {
                "pending_in_other_server_message": "You have verification in another server.",
                "verification_type_regular_display": "Normal",
            }

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            interaction.followup.send.assert_called_once()
            call_args = interaction.followup.send.call_args
            assert "another server" in call_args[0][0].lower()

    async def test_dm_disabled(self, verification_cog: VerificationCog) -> None:
        """Test with DMs disabled."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 999
        interaction.guild.name = "Test Guild"
        interaction.user = MagicMock(spec=discord.User)
        interaction.user.id = 888
        interaction.user.name = "TestUser"
        interaction.user.display_name = "TestUser"
        interaction.user.mention = "<@888>"
        interaction.user.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = {
                "already_pending_message": "Pending",
                "dm_instructions_message": "Instructions {username}",
                "dm_disabled_message": "DMs disabled",
                "verification_type_regular_display": "Normal",
            }

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            interaction.followup.send.assert_called()
            call_args = interaction.followup.send.call_args
            assert "DMs disabled" in str(call_args)


class TestHandleAccept:
    """Tests for handle_accept."""

    async def test_no_guild(self, verification_cog: VerificationCog) -> None:
        """Test without guild."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None

        await verification_cog.handle_accept(interaction=interaction, public_id="test1")

        interaction.response.defer.assert_not_called()

    async def test_not_mod(self, verification_cog: VerificationCog) -> None:
        """Test without moderator permissions."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = False
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = {"mod_roles": []}

            await verification_cog.handle_accept(interaction=interaction, public_id="test1")

            interaction.response.send_message.assert_called_once()
            call_kwargs = interaction.response.send_message.call_args.kwargs
            assert "permission" in call_kwargs["content"].lower()
            assert call_kwargs["ephemeral"] is True

    async def test_request_not_found(self, verification_cog: VerificationCog) -> None:
        """Test with non-existent request."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "Mod"
        interaction.user.display_name = "Mod"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = {"mod_roles": []}

            await verification_cog.handle_accept(interaction=interaction, public_id="nonexistent")

            interaction.followup.send.assert_called_once()
            call_args = interaction.followup.send.call_args
            assert "not found" in call_args.kwargs["content"].lower()


class TestHandleReject:
    """Tests for handle_reject."""

    async def test_no_guild(self, verification_cog: VerificationCog) -> None:
        """Test without guild."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None

        await verification_cog.handle_reject(
            interaction=interaction, public_id="test1", reason="reason"
        )

        interaction.response.defer.assert_not_called()

    async def test_not_mod(self, verification_cog: VerificationCog) -> None:
        """Test without moderator permissions."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = False
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = {"mod_roles": []}

            await verification_cog.handle_reject(
                interaction=interaction, public_id="test1", reason="reason"
            )

            interaction.response.send_message.assert_called_once()
            call_kwargs = interaction.response.send_message.call_args.kwargs
            assert "permission" in call_kwargs["content"].lower()
            assert call_kwargs["ephemeral"] is True


class TestShowRejectionSelect:
    """Tests for show_rejection_select."""

    async def test_no_guild(self, verification_cog: VerificationCog) -> None:
        """Test without guild."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await verification_cog.show_rejection_select(interaction=interaction, public_id="test1")

        interaction.response.send_message.assert_not_called()

    async def test_with_configured_reasons(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test with configured reasons."""
        # Create request in the database
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            public_id = request.public_id

        # Mock moderator role
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        # Mock user as Member with mod role
        mock_user = MagicMock(spec=discord.Member)
        mock_user.roles = [mock_role]

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [999],
            "rejection_reason_1": "Reason 1",
            "rejection_reason_2": "Reason 2",
            "rejection_reason_3": "",
            "rejection_reason_4": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.show_rejection_select(
                interaction=interaction, public_id=public_id
            )

            interaction.response.send_message.assert_called_once()
            call_kwargs = interaction.response.send_message.call_args[1]
            assert call_kwargs["ephemeral"] is True
            assert call_kwargs["view"] is not None

    async def test_with_no_configured_reasons(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test without configured reasons - uses defaults."""
        # Create request in the database
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            public_id = request.public_id

        # Mock moderator role
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        # Mock user as Member with mod role
        mock_user = MagicMock(spec=discord.Member)
        mock_user.roles = [mock_role]

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [999],
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.show_rejection_select(
                interaction=interaction, public_id=public_id
            )

            interaction.response.send_message.assert_called_once()

    async def test_shard_placeholder_replaced(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that placeholder {shard} is replaced in REJECT_WRONG_SHARD."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await session.commit()
            public_id = request.public_id

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        mock_user = MagicMock(spec=discord.Member)
        mock_user.roles = [mock_role]

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        config_values: dict[str, Any] = {
            "mod_roles": [999],
            "reject_wrong_shard": "User in wrong shard (expected: {shard})",
            "verification_shard": "ABLE",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.show_rejection_select(
                interaction=interaction, public_id=public_id
            )

            interaction.response.send_message.assert_called_once()
            call_kwargs = interaction.response.send_message.call_args[1]
            # Verify that the view has options with replaced shard
            view = call_kwargs["view"]
            assert view is not None

    async def test_shard_placeholder_skipped_when_no_shard_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that REJECT_WRONG_SHARD is omitted if no shard configured."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await session.commit()
            public_id = request.public_id

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        mock_user = MagicMock(spec=discord.Member)
        mock_user.roles = [mock_role]

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        config_values: dict[str, Any] = {
            "mod_roles": [999],
            "reject_wrong_shard": "User in wrong shard (expected: {shard})",
            # No verification_shard configured
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.show_rejection_select(
                interaction=interaction, public_id=public_id
            )

            # Should work without error (reason is omitted)
            interaction.response.send_message.assert_called_once()

    async def test_not_mod(self, verification_cog: VerificationCog) -> None:
        """Test that user without mod role cannot see the selector."""
        # Mock user without mod role
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 111  # Different role from mod

        mock_user = MagicMock(spec=discord.Member)
        mock_user.roles = [mock_role]
        mock_user.guild_permissions = MagicMock()
        mock_user.guild_permissions.administrator = False

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [999],
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.show_rejection_select(interaction=interaction, public_id="test1")

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "You do not have permission" in call_args[1]["content"]
            assert call_args[1]["ephemeral"] is True

    async def test_request_from_different_guild(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that rejects request from another guild (cross-guild security)."""
        # Create request in guild 999 (different from interaction guild)
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=999,  # Different guild
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            public_id = request.public_id

        # Mock moderator role
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        # Mock user as Member with mod role
        mock_user = MagicMock(spec=discord.Member)
        mock_user.roles = [mock_role]

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123  # Different guild from request
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [999],
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.show_rejection_select(
                interaction=interaction, public_id=public_id
            )

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            # Should reject as if request not found
            assert "not found" in call_args[1]["content"].lower()
            assert call_args[1]["ephemeral"] is True


class TestOnMemberRemove:
    """Tests for on_member_remove."""

    async def test_cancels_pending_verification(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that cancels pending verifications."""
        # Create pending request using the same database as the cog
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        # Simulate that the user is in pending_dm_verifications
        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Mock member
        member = MagicMock(spec=discord.Member)
        member.id = 456
        member.name = "TestUser"
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 123
        member.guild.name = "Test Guild"

        await verification_cog.on_member_remove(member)

        # Verify that was removed from pending
        assert 456 not in verification_cog._pending_dm_verifications

        # Verify that was cancelled in database (new session)
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.CANCELLED

    async def test_no_pending_verification(self, verification_cog: VerificationCog) -> None:
        """Test when there is no pending verification."""
        member = MagicMock(spec=discord.Member)
        member.id = 999
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 123

        # Should not fail
        await verification_cog.on_member_remove(member)

    async def test_updates_mod_message_on_leave(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that updates moderation message when user leaves."""
        # Create request with mod_message_id
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)
            await session.commit()

        # Mock member with guild that has moderation channel
        member = MagicMock(spec=discord.Member)
        member.id = 456
        member.name = "TestUser"
        member.guild = MagicMock(spec=discord.Guild)
        member.guild.id = 123
        member.guild.name = "Test Guild"

        # Mock moderation channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [MagicMock(description="Test content\n⏳ Pending review")]
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_message.edit = AsyncMock()
        member.guild.get_channel = MagicMock(return_value=mock_channel)

        # Mock the update_mod_message_cancelled function
        with patch("discord_bot.verification.cog.update_mod_message_cancelled") as mock_update:
            mock_update.return_value = None
            await verification_cog.on_member_remove(member)

            # Verify that update_mod_message_cancelled was called
            mock_update.assert_called_once()
            call_args = mock_update.call_args
            assert call_args[1]["guild"] == member.guild


class TestRestorePendingVerifications:
    """Tests for restoring pending verifications."""

    async def test_restore_pending_verifications(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that restores pending verifications from DB."""
        # Create pending verifications in the database
        async with test_database.session() as session:
            service = VerificationService(session)
            request1 = await service.create_request(
                guild_id=111,
                user_id=456,
                username="User1",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            request2 = await service.create_request(
                guild_id=222,
                user_id=789,
                username="User2",
                guild_name="Test Guild",
                verification_type=VerificationType.ALLY,
            )
            await session.commit()
            request1_id = request1.id
            request2_id = request2.id

        # Clear state in memory
        verification_cog._pending_dm_verifications.clear()

        # Restore
        await verification_cog._restore_pending_verifications()

        # Verify that were restored
        assert 456 in verification_cog._pending_dm_verifications
        assert 789 in verification_cog._pending_dm_verifications
        assert verification_cog._pending_dm_verifications[456] == (111, request1_id)
        assert verification_cog._pending_dm_verifications[789] == (222, request2_id)

    async def test_restore_ignores_pending_review(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that does not restore verifications in PENDING_REVIEW state."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=111,
                user_id=456,
                username="User1",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            # Update to PENDING_REVIEW
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()

        verification_cog._pending_dm_verifications.clear()
        await verification_cog._restore_pending_verifications()

        # Should not restore because it already has screenshots
        assert 456 not in verification_cog._pending_dm_verifications


class TestCleanupStaleVerifications:
    """Tests for cleanup of stale verifications on startup."""

    async def test_cancels_verification_when_user_not_in_guild(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that cancels verifications if user is no longer in the server."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        # Add to pending_dm_verifications to verify it gets cleaned
        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Mock guild without the member
        mock_guild = MagicMock()
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = None  # User is not present
        mock_guild.get_channel.return_value = None  # Without mod channel
        verification_cog.bot.get_guild.return_value = mock_guild

        await verification_cog._cleanup_stale_verifications()

        # Verify that was cancelled in the database
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.CANCELLED

        # Verify that was cleaned from memory
        assert 456 not in verification_cog._pending_dm_verifications

    async def test_skips_verification_when_guild_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that ignores verifications if guild is not available."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=999,  # Guild that doesn't exist
                user_id=456,
                username="TestUser",
                guild_name="Unknown Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            public_id = request.public_id

        # Bot doesn't find the guild
        verification_cog.bot.get_guild.return_value = None

        await verification_cog._cleanup_stale_verifications()

        # Verify that was NOT cancelled (guild not available)
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_SCREENSHOTS

    async def test_skips_verification_when_user_still_in_guild(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that does not cancel verifications if user is still in server."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            public_id = request.public_id

        # Mock guild with member present
        mock_member = MagicMock(spec=discord.Member)
        mock_member.id = 456
        mock_guild = MagicMock()
        mock_guild.id = 123
        mock_guild.get_member.return_value = mock_member  # User is present
        verification_cog.bot.get_guild.return_value = mock_guild

        await verification_cog._cleanup_stale_verifications()

        # Verify that was NOT cancelled
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_SCREENSHOTS

    async def test_handles_mod_message_update_error(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that continues if mod message update fails."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)
            await session.commit()
            public_id = request.public_id

        # Mock guild without the member
        mock_guild = MagicMock()
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = None
        mock_guild.get_channel.return_value = None
        verification_cog.bot.get_guild.return_value = mock_guild

        # Mock update_mod_message_cancelled to fail
        with patch(
            "discord_bot.verification.cog.update_mod_message_cancelled",
            side_effect=Exception("Discord API error"),
        ):
            # Should not throw exception
            await verification_cog._cleanup_stale_verifications()

        # Verify that was cancelled in the database despite the error
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.CANCELLED


class TestInitializeTrackers:
    """Tests for tracker initialization on startup."""

    async def test_initializes_tracker_for_guild_with_pending(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that initializes tracker for guilds with pending verifications."""
        # Create pending request and configuration
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            # Save configuration with mod_notification_channel
            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "mod_notification_channel", 888)
            await config_service.set_value(
                123, "verification", "tracker_title", "📋 Pending Verifications"
            )
            await session.commit()

        # Mock guild
        mock_tracker_message = MagicMock()
        mock_tracker_message.id = 9999

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.send = AsyncMock(return_value=mock_tracker_message)
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([]))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        verification_cog.bot.get_guild.return_value = mock_guild

        await verification_cog._initialize_trackers()

        # Verify that the tracker message was sent
        mock_mod_channel.send.assert_called_once()

    async def test_skips_guild_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that ignores guilds not found."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.create_request(
                guild_id=999,
                user_id=456,
                username="TestUser",
                guild_name="Unknown Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()

        # Bot doesn't find the guild
        verification_cog.bot.get_guild.return_value = None

        # Should not throw exception
        await verification_cog._initialize_trackers()

    async def test_skips_disabled_cog(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that ignores guilds with disabled cog."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        verification_cog.bot.get_guild.return_value = mock_guild

        # Cog disabled
        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog._initialize_trackers()

            # Should not call get_all_config (because cog is disabled)
            mock_guild.get_channel.assert_not_called()

    async def test_no_pending_returns_early(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that returns early if there are no pending verifications."""
        # Without pending verifications

        # Should not throw exception
        await verification_cog._initialize_trackers()


class TestOnMessage:
    """Tests for on_message (DM screenshots)."""

    async def test_ignores_guild_messages(self, verification_cog: VerificationCog) -> None:
        """Test that ignores guild messages."""
        message = MagicMock(spec=discord.Message)
        message.guild = MagicMock(spec=discord.Guild)

        await verification_cog.on_message(message)

        # Should not process anything

    async def test_ignores_bot_messages(self, verification_cog: VerificationCog) -> None:
        """Test that ignores bot messages."""
        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = True

        await verification_cog.on_message(message)

    async def test_responds_to_user_without_pending(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that responds to users without pending verification."""
        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 999
        message.reply = AsyncMock()

        # Configure mock bot to not find common server
        verification_cog.bot.guilds = []

        # Mock to not find in database
        with patch.object(
            verification_cog, "_get_pending_verification", new_callable=AsyncMock
        ) as mock_get_pending:
            mock_get_pending.return_value = None

            await verification_cog.on_message(message)

            # Should respond with default message
            message.reply.assert_called_once()
            args = message.reply.call_args[0]
            assert "You don't have any verification in progress" in args[0]

    async def test_responds_to_user_without_pending_with_config(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that responds with common server config."""
        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 999
        message.reply = AsyncMock()

        # Mock common server
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_member = MagicMock(return_value=MagicMock())
        verification_cog.bot.guilds = [mock_guild]

        config_values = {
            "no_pending_verification_message": "Custom message no verification",
        }

        with (
            patch.object(
                verification_cog, "_get_pending_verification", new_callable=AsyncMock
            ) as mock_get_pending,
            patch.object(
                verification_cog, "_is_cog_enabled", new_callable=AsyncMock
            ) as mock_enabled,
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
        ):
            mock_get_pending.return_value = None
            mock_enabled.return_value = True
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            message.reply.assert_called_once()
            args = message.reply.call_args[0]
            assert "Custom message no verification" in args[0]

    async def test_no_response_when_forbidden(self, verification_cog: VerificationCog) -> None:
        """Test that does not fail if cannot respond to user."""
        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 999
        message.reply = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Forbidden"))

        verification_cog.bot.guilds = []

        with patch.object(
            verification_cog, "_get_pending_verification", new_callable=AsyncMock
        ) as mock_get_pending:
            mock_get_pending.return_value = None

            # Should not throw exception
            await verification_cog.on_message(message)

    async def test_restores_pending_from_database(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that restores pending verification from the database."""
        # Create pending verification in DB
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        # The user is NOT in _pending_dm_verifications
        assert 456 not in verification_cog._pending_dm_verifications

        # Find pending verification
        result = await verification_cog._get_pending_verification(456)

        # Should find in DB and restore in memory
        assert result is not None
        assert result == (123, request_id)
        assert 456 in verification_cog._pending_dm_verifications
        assert verification_cog._pending_dm_verifications[456] == (123, request_id)

    async def test_returns_memory_before_database(self, verification_cog: VerificationCog) -> None:
        """Test that looks in memory first before going to the DB."""
        # Add to memory
        verification_cog._pending_dm_verifications[456] = (123, 999)

        # Find pending verification (should not go to DB)
        result = await verification_cog._get_pending_verification(456)

        assert result == (123, 999)

    async def test_wrong_image_count(self, verification_cog: VerificationCog) -> None:
        """Test with incorrect number of images."""
        verification_cog._pending_dm_verifications[456] = (123, 1)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        # Only 1 image
        attachment = MagicMock()
        attachment.content_type = "image/png"
        message.attachments = [attachment]

        config_values = {
            "wrong_images_message": "You must send 2 images",
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            message.channel.send.assert_called_once()
            # User still in pending
            assert 456 in verification_cog._pending_dm_verifications

    async def test_non_image_attachments_ignored(self, verification_cog: VerificationCog) -> None:
        """Test that non-image attachments are ignored."""
        verification_cog._pending_dm_verifications[456] = (123, 1)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        # 2 files but they are not images
        attachment1 = MagicMock()
        attachment1.content_type = "application/pdf"
        attachment2 = MagicMock()
        attachment2.content_type = "text/plain"
        message.attachments = [attachment1, attachment2]

        config_values = {
            "wrong_images_message": "You must send 2 images",
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            # Should ask for images since none were detected
            message.channel.send.assert_called_once()

    async def test_valid_screenshots_processed(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test successful processing of screenshots."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test Guild"
        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        # 2 valid images
        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values = {
            "screenshots_received_message": "Screenshots received",
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            # User removed from pending
            assert 456 not in verification_cog._pending_dm_verifications
            # Confirmation sent
            message.channel.send.assert_called()

        # Verify state in DB
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_REVIEW
            assert (
                updated.screenshot_1_url == "https://cdn.discordapp.com/attachments/123/456/1.png"
            )
            assert (
                updated.screenshot_2_url == "https://cdn.discordapp.com/attachments/123/456/2.jpg"
            )

    async def test_invalid_discord_url_rejected(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that non-Discord CDN URLs are rejected."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        # URLs from external domain (not Discord CDN)
        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://example.com/image1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://example.com/image2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "wrong_images_message": "Invalid URLs",
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            # Sent error message
            message.channel.send.assert_called_once()
            # User still in pending (was not processed)
            assert 456 in verification_cog._pending_dm_verifications

    async def test_auto_reject_on_api_422(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test auto-reject when API returns 422 (invalid images)."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import VerificationAPIResult

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            # Add mod_message_id so auto-reject is processed
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Mock mod message
        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        # Mock member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        # Mock mod channel (after guild so we can link them)
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        # Mock bot user
        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        # Mock settings with API configured
        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,
            "reject_wrong_captures": "Invalid captures",
            "rejection_message": "Your verification was rejected: {reason}",
            "delete_processed_messages": True,
        }

        # Mock API returns 422
        api_result = VerificationAPIResult(
            success=False,
            status_code=422,
            error_message="Invalid images",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify state in DB - should be rejected
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.REJECTED
            assert updated.reviewed_by_username == "Auto"

    async def test_auto_approve_when_checks_pass(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test auto-approval when all verifications pass."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Mock mod message
        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        # Mock role
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        # Mock member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        # Mock mod channel (after guild so we can link them)
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        # Mock bot user
        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Verification approved",
            "delete_processed_messages": True,
        }

        # Mock API returns successful response that passes all verifications
        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",  # Without regiment
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify state in DB - should be approved
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED
            assert updated.reviewed_by_username == "Auto"

    async def test_auto_reject_when_checks_fail(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test auto-reject when verifications fail (e.g. has regiment)."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Mock mod message
        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        # Mock member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        # Mock mod channel (after guild so we can link them)
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        # Mock bot user
        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "reject_has_regiment": "You already belong to a regiment",
            "rejection_message": "Your verification was rejected: {reason}",
            "delete_processed_messages": True,
        }

        # Mock API returns response with regiment (fails verification for REGULAR)
        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="82DK",  # Has regiment - should be rejected for REGULAR
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify state in DB - should be rejected
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.REJECTED
            assert updated.reviewed_by_username == "Auto"


class TestHandleAcceptHappyPath:
    """Tests for handle_accept successful flow."""

    async def test_accept_approves_and_adds_roles(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test successful approval with roles."""
        # Create request pending review
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request.id,
                "https://cdn.discordapp.com/attachments/123/456/1.png",
                "https://cdn.discordapp.com/attachments/123/456/2.png",
                "Test Guild",
            )
            await session.commit()
            public_id = request.public_id

        # Mock role
        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        # Mock member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_guild.get_channel = MagicMock(return_value=None)

        # Mock interaction
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, public_id=public_id)

            # Role added
            mock_member.add_roles.assert_called_once_with(mock_role)
            # DM sent
            mock_member.send.assert_called_once()
            # Confirmation
            interaction.followup.send.assert_called()

        # Verify state in DB
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED
            assert updated.reviewed_by_id == 789

    async def test_accept_posts_welcome_card(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that approval invokes the welcome card poster with the approved member."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request.id,
                "https://cdn.discordapp.com/attachments/123/456/1.png",
                "https://cdn.discordapp.com/attachments/123/456/2.png",
                "Test Guild",
            )
            await session.commit()
            public_id = request.public_id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved!",
            "mod_notification_channel": None,
            "welcome_card_enabled": True,
        }

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.post_welcome_card",
                new_callable=AsyncMock,
            ) as mock_post_card,
        ):
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, public_id=public_id)

            mock_post_card.assert_awaited_once()
            _, kwargs = mock_post_card.call_args
            assert kwargs["guild"] is mock_guild
            assert kwargs["config"] is config_values
            assert kwargs["member"] is mock_member
            assert kwargs["request"].public_id == public_id

    async def test_accept_already_processed(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test approval of already processed request."""
        # Create already approved request
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await service.approve(
                request_id=request.id,
                reviewer_id=111,
                reviewer_username="OtherMod",
                guild_name="Test Guild",
            )
            await session.commit()
            public_id = request.public_id

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, public_id=public_id)

            call_args = interaction.followup.send.call_args
            assert "already been processed" in call_args.kwargs["content"].lower()


class TestHandleRejectHappyPath:
    """Tests for handle_reject successful flow."""

    async def test_reject_updates_status_and_notifies(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test successful rejection."""
        # Create request pending review
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await session.commit()
            public_id = request.public_id

        # Mock member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "rejection_message": "Rejected: {reason}",
            "mod_notification_channel": None,
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Ally",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_reject(
                interaction=interaction, public_id=public_id, reason="Invalid captures"
            )

            # DM sent with reason
            mock_member.send.assert_called_once()
            sent_message = mock_member.send.call_args.kwargs["content"]
            assert "Invalid captures" in sent_message

        # Verify state in DB
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.REJECTED
            assert updated.rejection_reason == "Invalid captures"


class TestHealthCheck:
    """Tests for health check."""

    async def test_check_verification_message_no_channel(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test healthcheck without configured channel (cog enabled)."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        # Enable cog but DO NOT configure channel
        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        # Should not fail - returns early on line 85
        await verification_cog._check_verification_message(mock_guild)

    async def test_check_verification_message_disabled(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test healthcheck disabled."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        # Configure interval = 0
        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "health_check_interval", 0)
            await session.commit()

        # Should not do anything
        await verification_cog._check_verification_message(mock_guild)

    async def test_run_health_check_iterates_guilds(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that healthcheck iterates over guilds."""
        mock_guild1 = MagicMock(spec=discord.Guild)
        mock_guild1.id = 111
        mock_guild2 = MagicMock(spec=discord.Guild)
        mock_guild2.id = 222

        object.__setattr__(verification_cog.bot, "guilds", [mock_guild1, mock_guild2])

        with (
            patch.object(
                verification_cog, "_get_health_check_interval", new_callable=AsyncMock
            ) as mock_interval,
            patch.object(
                verification_cog, "_check_verification_message", new_callable=AsyncMock
            ) as mock_check,
        ):
            mock_interval.return_value = 30  # Health check enabled

            await verification_cog._run_health_check(force_all=True)

            assert mock_check.call_count == 2

    async def test_run_health_check_handles_exception(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that healthcheck handles exceptions per guild."""
        mock_guild1 = MagicMock(spec=discord.Guild)
        mock_guild1.id = 111
        mock_guild2 = MagicMock(spec=discord.Guild)
        mock_guild2.id = 222

        object.__setattr__(verification_cog.bot, "guilds", [mock_guild1, mock_guild2])

        with (
            patch.object(
                verification_cog, "_get_health_check_interval", new_callable=AsyncMock
            ) as mock_interval,
            patch.object(
                verification_cog, "_check_verification_message", new_callable=AsyncMock
            ) as mock_check,
        ):
            mock_interval.return_value = 30
            # First guild fails, second should continue
            mock_check.side_effect = [Exception("Error"), None]

            await verification_cog._run_health_check(force_all=True)

            # Both were called
            assert mock_check.call_count == 2

    async def test_run_health_check_skips_disabled_guilds(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that healthcheck skips guilds with interval 0."""
        mock_guild1 = MagicMock(spec=discord.Guild)
        mock_guild1.id = 111
        mock_guild2 = MagicMock(spec=discord.Guild)
        mock_guild2.id = 222

        object.__setattr__(verification_cog.bot, "guilds", [mock_guild1, mock_guild2])

        with (
            patch.object(
                verification_cog, "_get_health_check_interval", new_callable=AsyncMock
            ) as mock_interval,
            patch.object(
                verification_cog, "_check_verification_message", new_callable=AsyncMock
            ) as mock_check,
        ):
            # Guild 1 desactivado, Guild 2 activado
            mock_interval.side_effect = [0, 30]

            await verification_cog._run_health_check(force_all=True)

            # Only guild 2 was verified
            assert mock_check.call_count == 1
            mock_check.assert_called_once_with(guild=mock_guild2)

    async def test_run_health_check_respects_interval(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that healthcheck respects the interval per guild."""
        from datetime import UTC, datetime, timedelta

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 111

        object.__setattr__(verification_cog.bot, "guilds", [mock_guild])

        with (
            patch.object(
                verification_cog, "_get_health_check_interval", new_callable=AsyncMock
            ) as mock_interval,
            patch.object(
                verification_cog, "_check_verification_message", new_callable=AsyncMock
            ) as mock_check,
        ):
            mock_interval.return_value = 30  # 30 minutes

            # Simulate verified 10 minutes ago
            verification_cog._last_health_check[111] = datetime.now(UTC) - timedelta(minutes=10)

            await verification_cog._run_health_check()

            # Should not verify (only 10 of 30 minutes passed)
            assert mock_check.call_count == 0

            # Simulate verified 35 minutes ago
            verification_cog._last_health_check[111] = datetime.now(UTC) - timedelta(minutes=35)

            await verification_cog._run_health_check()

            # Now it should verify
            assert mock_check.call_count == 1

    async def test_run_health_check_updates_last_check(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that healthcheck updates the timestamp when verifying."""
        from datetime import datetime

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 111

        object.__setattr__(verification_cog.bot, "guilds", [mock_guild])

        with (
            patch.object(
                verification_cog, "_get_health_check_interval", new_callable=AsyncMock
            ) as mock_interval,
            patch.object(verification_cog, "_check_verification_message", new_callable=AsyncMock),
        ):
            mock_interval.return_value = 30

            # Without previous timestamp
            assert 111 not in verification_cog._last_health_check

            await verification_cog._run_health_check(force_all=True)

            # Should now have timestamp
            assert 111 in verification_cog._last_health_check
            assert isinstance(verification_cog._last_health_check[111], datetime)

    async def test_get_health_check_interval_returns_configured_value(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that _get_health_check_interval returns the configured value."""
        guild_id = 123

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id, "verification", True)
            await config_service.set_value(guild_id, "verification", "health_check_interval", 15)
            await session.commit()

        interval = await verification_cog._get_health_check_interval(guild_id)
        assert interval == 15

    async def test_get_health_check_interval_returns_default(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that _get_health_check_interval returns 30 by default."""
        guild_id = 456

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id, "verification", True)
            await session.commit()

        interval = await verification_cog._get_health_check_interval(guild_id)
        assert interval == 30

    async def test_get_health_check_interval_returns_zero_when_disabled(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that _get_health_check_interval returns 0 when cog is disabled."""
        guild_id = 789

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(guild_id, "verification", False)
            await session.commit()

        interval = await verification_cog._get_health_check_interval(guild_id)
        assert interval == 0

    async def test_check_verification_message_no_panel_message_id(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test healthcheck without panel message ID."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        # Configure channel but not panel message ID
        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await session.commit()

        await verification_cog._check_verification_message(mock_guild)

    async def test_check_verification_message_channel_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test healthcheck with channel not found."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=None)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await session.commit()

        # Should return early with warning (lines 89-90)
        await verification_cog._check_verification_message(mock_guild)

    async def test_check_verification_message_message_not_found_restores(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test health check restores panel when message does not exist."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        with patch.object(
            verification_cog, "_create_verification_message", new_callable=AsyncMock
        ) as mock_create:
            await verification_cog._check_verification_message(mock_guild)
            mock_create.assert_called_once()

    async def test_check_verification_message_forbidden(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test healthcheck with denied permissions (lines 167-168)."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Forbidden")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        # Should not fail - handles Forbidden with warning (lines 167-168)
        await verification_cog._check_verification_message(mock_guild)

    async def test_check_verification_message_no_components_restores(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test healthcheck restores panel without buttons."""
        mock_message = MagicMock()
        mock_message.components = []  # Without components

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        # Mock mod channel with proper permissions
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_permissions = MagicMock()
        mock_permissions.send_messages = True
        mock_mod_channel.permissions_for = MagicMock(return_value=mock_permissions)

        def get_channel(channel_id: int) -> MagicMock:
            if channel_id == 222:
                return mock_mod_channel
            return mock_channel

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(side_effect=get_channel)
        mock_guild.get_member = MagicMock(return_value=MagicMock())

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "mod_notification_channel", 222)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        with (
            patch(
                "discord_bot.verification.panel.delete_message", new_callable=AsyncMock
            ) as mock_delete,
            patch.object(
                verification_cog, "_create_verification_message", new_callable=AsyncMock
            ) as mock_create,
        ):
            await verification_cog._check_verification_message(mock_guild)
            # Should delete old panel before recreating
            mock_delete.assert_called_once()
            mock_create.assert_called_once()

    async def test_check_verification_message_disabled_no_components_does_not_recreate(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that does NOT recreate panel when verification disabled and no buttons."""
        mock_message = MagicMock()
        mock_message.components = []  # No components (expected for disabled state)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            # verification_enabled = False (disabled)
            await config_service.set_value(123, "verification", "verification_enabled", False)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        with patch.object(
            verification_cog, "_create_verification_message", new_callable=AsyncMock
        ) as mock_create:
            await verification_cog._check_verification_message(mock_guild)
            # Should NOT recreate - disabled panel without buttons is correct state
            mock_create.assert_not_called()

    async def test_check_verification_message_auto_creates_when_no_panel(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that panel is created automatically if it does not exist."""
        mock_channel = MagicMock(spec=discord.TextChannel)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            # Only channel configured, without existing panel
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await session.commit()

        with patch.object(
            verification_cog, "_create_verification_message", new_callable=AsyncMock
        ) as mock_create:
            await verification_cog._check_verification_message(mock_guild)
            mock_create.assert_called_once()

    async def test_check_verification_message_moves_when_channel_changes(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that moves panel when channel changes."""
        # Old channel (where panel was)
        mock_old_channel = MagicMock(spec=discord.TextChannel)
        mock_old_channel.name = "old-verification"
        mock_old_message = MagicMock()
        mock_old_channel.fetch_message = AsyncMock(return_value=mock_old_message)
        mock_old_message.delete = AsyncMock()

        # New channel (where panel should go)
        mock_new_channel = MagicMock(spec=discord.TextChannel)
        mock_new_channel.name = "new-verification"

        def get_channel(channel_id: int) -> MagicMock | None:
            if channel_id == 111:
                return mock_old_channel
            if channel_id == 222:
                return mock_new_channel
            return None

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(side_effect=get_channel)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            # Configured channel: 222 (new)
            await config_service.set_value(123, "verification", "verification_channel", 222)
            # Existing panel in channel 111 (old)
            await config_service.set_value(123, "verification", "_panel_message_id", 999)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        with patch.object(
            verification_cog, "_create_verification_message", new_callable=AsyncMock
        ) as mock_create:
            await verification_cog._check_verification_message(mock_guild)

            # Should delete old panel
            mock_old_message.delete.assert_called_once()
            # Should create new panel
            mock_create.assert_called_once()


class TestDeleteMessage:
    """Tests for delete_message utility."""

    async def test_delete_message_success(self) -> None:
        """Test successful message deletion."""
        mock_message = MagicMock()
        mock_message.delete = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.name = "old-channel"
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        result = await delete_message(guild=mock_guild, channel_id=111, message_id=999)

        assert result is True
        mock_message.delete.assert_called_once()

    async def test_delete_message_channel_not_found(self) -> None:
        """Test deletion when channel does not exist."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=None)

        result = await delete_message(guild=mock_guild, channel_id=111, message_id=999)

        assert result is False

    async def test_delete_message_not_found(self) -> None:
        """Test deletion when message no longer exists."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        result = await delete_message(guild=mock_guild, channel_id=111, message_id=999)

        assert result is False

    async def test_delete_message_forbidden(self) -> None:
        """Test deletion without permissions."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Forbidden")
        )

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        result = await delete_message(guild=mock_guild, channel_id=111, message_id=999)

        assert result is False


class TestCreateVerificationMessage:
    """Tests for _create_verification_message."""

    async def test_create_verification_message_success(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test successful panel creation with moderation channel configured."""
        mock_new_message = MagicMock()
        mock_new_message.id = 12345

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.name = "verification"
        mock_channel.send = AsyncMock(return_value=mock_new_message)

        # Mock moderation channel
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 222

        # Mock bot permissions in moderation channel
        mock_permissions = MagicMock()
        mock_permissions.send_messages = True
        mock_mod_channel.permissions_for = MagicMock(return_value=mock_permissions)

        # Mock bot member
        mock_bot_member = MagicMock(spec=discord.Member)
        mock_bot_member.id = 999

        # Configure bot.user.id
        mock_user = MagicMock()
        mock_user.id = 999
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)
        mock_guild.get_member = MagicMock(return_value=mock_bot_member)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)

            # Configure required values
            await config_service.set_value(123, "verification", "mod_notification_channel", 222)
            await config_service.set_value(123, "verification", "verify_button_text", "Verify")
            await config_service.set_value(123, "verification", "verify_ally_button_text", "Ally")
            await config_service.set_value(
                123, "verification", "verification_panel_message", "Welcome"
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()
            # Verify that was sent with view (buttons enabled)
            call_kwargs = mock_channel.send.call_args.kwargs
            assert call_kwargs["view"] is not None

    async def test_create_verification_message_disabled_no_mod_channel(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test panel disabled when there is no moderation channel."""
        mock_new_message = MagicMock()
        mock_new_message.id = 12345

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.name = "verification"
        mock_channel.send = AsyncMock(return_value=mock_new_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)

            # DO NOT configure mod_notification_channel
            await config_service.set_value(
                123,
                "verification",
                "verification_disabled_message",
                "Verification is disabled",
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()
            # Verify that was sent without view (buttons disabled)
            call_kwargs = mock_channel.send.call_args.kwargs
            assert "view" not in call_kwargs
            # Content is now in the embed
            assert "embed" in call_kwargs
            assert "disabled" in call_kwargs["embed"].description

    async def test_create_verification_message_forbidden(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test creation with denied permissions in verification channel."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Forbidden"))

        # Mock moderation channel
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 222

        # Mock bot permissions
        mock_permissions = MagicMock()
        mock_permissions.send_messages = True
        mock_mod_channel.permissions_for = MagicMock(return_value=mock_permissions)

        # Mock bot member
        mock_bot_member = MagicMock(spec=discord.Member)
        mock_bot_member.id = 999

        # Configure bot.user.id
        mock_user = MagicMock()
        mock_user.id = 999
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)
        mock_guild.get_member = MagicMock(return_value=mock_bot_member)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)

            # Configure required values
            await config_service.set_value(123, "verification", "mod_notification_channel", 222)
            await config_service.set_value(123, "verification", "verify_button_text", "Verify")
            await config_service.set_value(123, "verification", "verify_ally_button_text", "Ally")
            await config_service.set_value(
                123, "verification", "verification_panel_message", "Welcome"
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            # Should not fail
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

    async def test_create_verification_message_with_embed_and_view(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test panel creation with embed and image (line 227)."""
        mock_new_message = MagicMock()
        mock_new_message.id = 12345

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.name = "verification"
        mock_channel.send = AsyncMock(return_value=mock_new_message)

        # Mock moderation channel
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 222

        # Mock bot permissions in moderation channel
        mock_permissions = MagicMock()
        mock_permissions.send_messages = True
        mock_mod_channel.permissions_for = MagicMock(return_value=mock_permissions)

        # Mock bot member
        mock_bot_member = MagicMock(spec=discord.Member)
        mock_bot_member.id = 999

        # Configure bot.user.id
        mock_user = MagicMock()
        mock_user.id = 999
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)
        mock_guild.get_member = MagicMock(return_value=mock_bot_member)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)

            # Configure with image URL to create embed
            await config_service.set_value(123, "verification", "mod_notification_channel", 222)
            await config_service.set_value(123, "verification", "verify_button_text", "Verify")
            await config_service.set_value(123, "verification", "verify_ally_button_text", "Ally")
            await config_service.set_value(
                123,
                "verification",
                "verification_panel_message",
                "Welcome\nhttps://example.com/image.png",
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()
            # Verify that was sent with embed and view
            call_kwargs = mock_channel.send.call_args.kwargs
            assert "embed" in call_kwargs
            assert call_kwargs["view"] is not None

    async def test_create_verification_message_with_embed_only(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test panel creation with embed without buttons (line 229)."""
        mock_new_message = MagicMock()
        mock_new_message.id = 12345

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.name = "verification"
        mock_channel.send = AsyncMock(return_value=mock_new_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        # Without moderation channel configured

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)

            # DO NOT configure mod_notification_channel (disabled)
            # But DO put image URL to create embed
            await config_service.set_value(
                123,
                "verification",
                "verification_disabled_message",
                "Verification disabled\nhttps://example.com/image.png",
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()
            # Verify that was sent with embed only (without view)
            call_kwargs = mock_channel.send.call_args.kwargs
            assert "embed" in call_kwargs
            assert "view" not in call_kwargs or call_kwargs.get("view") is None


class TestHandleVerificationStartHappyPath:
    """Tests for handle_verification_start successful flow."""

    async def test_starts_verification_successfully(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test successful verification start."""
        # Mock mod channel
        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_channel.send = AsyncMock(return_value=mock_mod_message)

        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        # Mock user
        mock_user = MagicMock(spec=discord.User)
        mock_user.id = 456
        mock_user.name = "NewUser"
        mock_user.mention = "<@456>"
        mock_user.send = AsyncMock()

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "already_pending_message": "Pending",
            "dm_instructions_message": "Instructions for {username}",
            "mod_notification_channel": 888,
            "mod_message_template": "New verification from {username}",
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Ally",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            # DM sent
            mock_user.send.assert_called_once()
            # Message to mods sent (+ tracker message)
            assert mock_mod_channel.send.call_count >= 1
            # Confirmation
            interaction.followup.send.assert_called()

        # Verify that the request was created
        async with test_database.session() as session:
            service = VerificationService(session)
            pending = await service.get_pending_by_user(123, 456)
            assert pending is not None
            assert pending.status == VerificationStatus.PENDING_SCREENSHOTS


class TestRoleOperations:
    """Tests for role operations."""

    async def test_accept_role_add_forbidden(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test approval when adding role fails."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await session.commit()
            public_id = request.public_id

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Forbidden"))
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            # Should not fail even if the role fails
            await verification_cog.handle_accept(interaction=interaction, public_id=public_id)

            interaction.followup.send.assert_called()

    async def test_accept_role_remove_forbidden(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test approval when removing role fails."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await session.commit()
            public_id = request.public_id

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Forbidden")
        )
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [999],
            "approval_message_regular": "Approved!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, public_id=public_id)

            interaction.followup.send.assert_called()

    async def test_accept_dm_forbidden(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test approval when DM fails."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await session.commit()
            public_id = request.public_id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Forbidden"))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            # Should not fail
            await verification_cog.handle_accept(interaction=interaction, public_id=public_id)

            interaction.followup.send.assert_called()


class TestModMessageEditing:
    """Tests for editing moderation messages."""

    async def test_accept_edits_mod_message(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that accept edits the moderation message."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            public_id = request.public_id

        pending_status = "🔍 **Status:** Pending review"

        # Create mock of existing embed with proper copy behavior
        mock_embed_copy = MagicMock()
        mock_embed_copy.description = f"Request\n\n{pending_status}"
        mock_embed_copy.title = None
        mock_embed_copy.fields = []
        mock_embed_copy.color = None

        mock_embed = MagicMock()
        mock_embed.description = f"Request\n\n{pending_status}"
        mock_embed.copy = MagicMock(return_value=mock_embed_copy)

        mock_mod_message = MagicMock()
        mock_mod_message.embeds = [mock_embed]
        mock_mod_message.edit = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved!",
            "mod_notification_channel": 888,
            "status_pending_review": pending_status,
            "status_approved": "✅ **Status:** Approved by {moderator}",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, public_id=public_id)

            mock_mod_message.edit.assert_called_once()
            edit_kwargs = mock_mod_message.edit.call_args[1]
            # Content is now in the first embed
            assert "embeds" in edit_kwargs
            main_embed = edit_kwargs["embeds"][0]
            assert "Approved" in (main_embed.description or "")
            assert edit_kwargs["view"] is None

    async def test_accept_mod_message_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test accept when mod message does not exist."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            public_id = request.public_id

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved!",
            "mod_notification_channel": 888,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            # Should not fail
            await verification_cog.handle_accept(interaction=interaction, public_id=public_id)

            interaction.followup.send.assert_called()

    async def test_reject_edits_mod_message(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that reject edits the moderation message."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            public_id = request.public_id

        pending_status = "🔍 **Status:** Pending review"

        # Create mock of existing embed with proper copy behavior
        mock_embed_copy = MagicMock()
        mock_embed_copy.description = f"Request\n\n{pending_status}"
        mock_embed_copy.title = None
        mock_embed_copy.fields = []
        mock_embed_copy.color = None

        mock_embed = MagicMock()
        mock_embed.description = f"Request\n\n{pending_status}"
        mock_embed.copy = MagicMock(return_value=mock_embed_copy)

        mock_mod_message = MagicMock()
        mock_mod_message.embeds = [mock_embed]
        mock_mod_message.edit = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "rejection_message": "Rejected: {reason}",
            "mod_notification_channel": 888,
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Ally",
            "status_pending_review": pending_status,
            "status_rejected": "❌ **Status:** Rejected by {moderator}\n**Reason:** {reason}",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_reject(
                interaction=interaction, public_id=public_id, reason="Invalid captures"
            )

            mock_mod_message.edit.assert_called_once()
            edit_kwargs = mock_mod_message.edit.call_args[1]
            # Content is now in the first embed
            assert "embeds" in edit_kwargs
            main_embed = edit_kwargs["embeds"][0]
            assert "Rejected" in (main_embed.description or "")
            assert "Invalid captures" in (main_embed.description or "")


class TestUpdateModMessageForReview:
    """Tests for _update_mod_message_for_review."""

    async def test_update_with_history(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test update with verification history."""
        # Create history
        async with test_database.session() as session:
            service = VerificationService(session)
            # Previous approved request
            old_request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(old_request.id, "old1", "old2", "Test Guild")
            await service.approve(
                request_id=old_request.id,
                reviewer_id=111,
                reviewer_username="OldMod",
                guild_name="Test Guild",
            )

            # Current request
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.ALLY,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()

            # Refresh request
            refreshed = await service.get_request(request.id)
            assert refreshed is not None
            request = refreshed

            mock_mod_message = MagicMock()
            mock_mod_message.edit = AsyncMock()

            mock_channel = MagicMock(spec=discord.TextChannel)
            mock_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

            config = {
                "mod_message_template": "Template {username}",
                "verification_type_regular_display": "Normal",
                "verification_type_ally_display": "Ally",
                "accept_button_text": "Accept",
                "reject_button_text": "Reject",
            }

            await verification_cog._update_mod_message_for_review(
                channel=mock_channel,
                request=request,
                verification_service=service,
                config=config,
            )

            mock_mod_message.edit.assert_called_once()
            edit_kwargs = mock_mod_message.edit.call_args[1]
            # Content is now in the first embed
            assert "embeds" in edit_kwargs
            main_embed = edit_kwargs["embeds"][0]
            # History is now a field, not part of description
            history_field = next(
                (f for f in main_embed.fields if f.name == "History"),
                None,
            )
            assert history_field is not None

    async def test_update_message_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test update when message does not exist."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            refreshed = await service.get_request(request.id)
            assert refreshed is not None
            request = refreshed

            mock_channel = MagicMock(spec=discord.TextChannel)
            mock_channel.fetch_message = AsyncMock(
                side_effect=discord.NotFound(MagicMock(), "Not found")
            )

            config = {
                "mod_message_template": "Template {username}",
                "verification_type_regular_display": "Normal",
                "verification_type_ally_display": "Ally",
                "accept_button_text": "Accept",
                "reject_button_text": "Reject",
            }

            # Should not fail
            await verification_cog._update_mod_message_for_review(
                channel=mock_channel,
                request=request,
                verification_service=service,
                config=config,
            )


class TestOnMessageScreenshots:
    """Additional tests for on_message with screenshots."""

    async def test_request_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test when request does not exist in DB."""
        # Register pending but without creating in DB
        verification_cog._pending_dm_verifications[456] = (123, 99999)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=None))

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values = {
            "request_not_found_message": "Error: Your request was not found.",
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            # Should send error
            message.channel.send.assert_called()
            call_args = message.channel.send.call_args
            assert "error" in call_args.kwargs["content"].lower()


class TestCogLifecycle:
    """Tests for cog_load and cog_unload."""

    async def test_cog_load_starts_health_check(self, mock_discord_bot: MagicMock) -> None:
        """Test that cog_load starts health check."""
        cog = VerificationCog(mock_discord_bot)

        # Mock the task
        cog.health_check_loop = MagicMock()
        cog.health_check_loop.start = MagicMock()

        await cog.cog_load()

        mock_discord_bot.add_view.assert_called_once()
        cog.health_check_loop.start.assert_called_once()
        assert cog._health_check_started is True

    async def test_cog_unload_stops_health_check(self, mock_discord_bot: MagicMock) -> None:
        """Test that cog_unload stops health check."""
        cog = VerificationCog(mock_discord_bot)
        cog._health_check_started = True

        cog.health_check_loop = MagicMock()
        cog.health_check_loop.cancel = MagicMock()

        await cog.cog_unload()

        cog.health_check_loop.cancel.assert_called_once()
        assert cog._health_check_started is False


class TestHealthCheckTaskMethods:
    """Tests for health check task loop methods."""

    async def test_health_check_loop_calls_run_health_check(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that the loop calls _run_health_check."""
        with patch.object(
            verification_cog, "_run_health_check", new_callable=AsyncMock
        ) as mock_run:
            await verification_cog.health_check_loop()

            mock_run.assert_called_once()

    async def test_before_health_check_waits_and_runs(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that before_health_check waits for the bot and runs health check."""
        with patch.object(
            verification_cog, "_run_health_check", new_callable=AsyncMock
        ) as mock_run:
            await verification_cog.before_health_check()

            wait_until_ready_mock = cast(AsyncMock, verification_cog.bot.wait_until_ready)
            wait_until_ready_mock.assert_called_once()
            # Should execute health check immediately
            mock_run.assert_called_once()


class TestGetAllConfig:
    """Tests for _get_all_config."""

    async def test_get_all_config_returns_values(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that _get_all_config returns configured values."""
        from discord_bot.common.services.config_service import ConfigService

        async with test_database.session() as session:
            config_service = ConfigService(session=session)
            await config_service.set_value(
                guild_id=123,
                cog_name="verification",
                key="verify_button_text",
                value="My Button",
            )
            await session.commit()

        result = await verification_cog._get_all_config(guild_id=123)
        assert result.get("verify_button_text") == "My Button"

    async def test_get_all_config_returns_empty_dict_for_missing(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that _get_all_config returns empty dict for guild without config."""
        result = await verification_cog._get_all_config(guild_id=999)
        assert isinstance(result, dict)


class TestHandleAcceptAllyRoles:
    """Tests for handle_accept with ally verification."""

    async def test_accept_ally_uses_ally_roles(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that accepting ally uses ally roles."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.ALLY,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
            )
            await session.commit()
            public_id = request.public_id

        mock_ally_role = MagicMock(spec=discord.Role)
        mock_ally_role.id = 777

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_ally_role)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "regular_roles_add": [111],
            "regular_roles_remove": [],
            "ally_roles_add": [777],
            "ally_roles_remove": [222],
            "approval_message_ally": "Approved as ally!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, public_id=public_id)

            # Should use ally role, not regular
            mock_member.add_roles.assert_called_once_with(mock_ally_role)


class TestHandleRejectEdgeCases:
    """Tests for handle_reject edge cases."""

    async def test_reject_request_not_found(self, verification_cog: VerificationCog) -> None:
        """Test rejection with non-existent request."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "Mod"
        interaction.user.display_name = "Mod"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_reject(
                interaction=interaction, public_id="nonexistent", reason="reason"
            )

            call_args = interaction.followup.send.call_args
            assert "not found" in call_args.kwargs["content"].lower()

    async def test_reject_already_processed(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test rejection of already processed request."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await service.reject(
                request_id=request.id,
                reviewer_id=111,
                reviewer_username="OtherMod",
                reason="Already rejected",
                guild_name="Test Guild",
            )
            await session.commit()
            public_id = request.public_id

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
        }
        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_reject(
                interaction=interaction, public_id=public_id, reason="reason"
            )

            call_args = interaction.followup.send.call_args
            assert "already been processed" in call_args.kwargs["content"].lower()

    async def test_reject_dm_forbidden(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test rejection when DM fails."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await session.commit()
            public_id = request.public_id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Forbidden"))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "rejection_message": "Rejected: {reason}",
            "mod_notification_channel": None,
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Ally",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            # Should not fail even if DM fails
            await verification_cog.handle_reject(
                interaction=interaction, public_id=public_id, reason="Invalid captures"
            )

            interaction.followup.send.assert_called()

    async def test_reject_mod_message_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test rejection when mod message does not exist."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            public_id = request.public_id

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "mod_roles": [],
            "rejection_message": "Rejected: {reason}",
            "mod_notification_channel": 888,
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Ally",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            # Should not fail
            await verification_cog.handle_reject(
                interaction=interaction, public_id=public_id, reason="Invalid captures"
            )

            interaction.followup.send.assert_called()


class TestOnMessageUpdateModMessage:
    """Tests for on_message updating moderation message."""

    async def test_screenshots_updates_mod_message(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that screenshots updates mod message."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=777)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.edit = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        # Mock for tracker message
        mock_tracker_message = MagicMock()
        mock_tracker_message.id = 9999
        mock_mod_channel.send = AsyncMock(return_value=mock_tracker_message)
        # Mock history for tracker positioning
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([]))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, object] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "mod_message_template": "Verification from {username}",
            "verification_type_regular_display": "Normal",
            "verification_type_ally_display": "Ally",
            "accept_button_text": "Accept",
            "reject_button_text": "Reject",
            "tracker_title": "📋 Pending Verifications",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.on_message(message)

            # Mod message was edited
            mock_mod_message.edit.assert_called_once()


class TestUpdateModMessageNoMessageId:
    """Tests for _update_mod_message_for_review without mod_message_id."""

    async def test_early_return_when_no_mod_message_id(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that returns early without mod_message_id."""
        async with test_database.session() as session:
            service = VerificationService(session)
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
            # DO NOT set mod_message_id
            await session.commit()
            refreshed = await service.get_request(request.id)
            assert refreshed is not None
            request = refreshed

            mock_channel = MagicMock(spec=discord.TextChannel)
            mock_channel.fetch_message = AsyncMock()

            await verification_cog._update_mod_message_for_review(
                mock_channel, request, service, {}
            )

            # Should not try to fetch
            mock_channel.fetch_message.assert_not_called()


class TestSetupAndTeardown:
    """Tests for module setup and teardown functions."""

    async def test_setup_registers_schema_and_adds_cog(self, mock_discord_bot: MagicMock) -> None:
        """Test that setup registers schema and adds cog."""
        from discord_bot.common.services.config_schema_service import (
            get_config_schema_service,
        )
        from discord_bot.verification.cog import setup

        mock_discord_bot.add_cog = AsyncMock()

        await setup(mock_discord_bot)

        # Verify that the cog was added
        mock_discord_bot.add_cog.assert_called_once()

        # Verify that the schema was registered
        schema_service = get_config_schema_service()
        schema = schema_service.get_schema("verification")
        assert schema is not None

    async def test_teardown_unregisters_schema(self, mock_discord_bot: MagicMock) -> None:
        """Test that teardown unregisters the schema."""
        from discord_bot.common.services.config_schema_service import (
            get_config_schema_service,
        )
        from discord_bot.verification.cog import setup, teardown

        mock_discord_bot.add_cog = AsyncMock()

        # First setup
        await setup(mock_discord_bot)

        # Then teardown
        await teardown(mock_discord_bot)

        # Schema should no longer exist
        schema_service = get_config_schema_service()
        schema = schema_service.get_schema("verification")
        assert schema is None


class TestOnConfigChanged:
    """Tests for on_config_changed."""

    async def test_updates_panel_on_relevant_key(self, verification_cog: VerificationCog) -> None:
        """Test that updates panel when a relevant key changes."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test Guild"

        with patch.object(
            verification_cog, "_check_verification_message", new_callable=AsyncMock
        ) as mock_check:
            await verification_cog.on_config_changed(mock_guild, ["verification_channel"])

            mock_check.assert_called_once_with(guild=mock_guild, recreate=True)

    async def test_ignores_irrelevant_key(self, verification_cog: VerificationCog) -> None:
        """Test that ignores keys not related to the panel."""
        mock_guild = MagicMock(spec=discord.Guild)

        with patch.object(
            verification_cog, "_check_verification_message", new_callable=AsyncMock
        ) as mock_check:
            await verification_cog.on_config_changed(mock_guild, ["some_other_key"])

            mock_check.assert_not_called()


class TestCheckVerificationMessageRecreate:
    """Tests for _check_verification_message with recreate=True."""

    async def test_no_channel_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test when there is no configured channel."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        with patch(
            "discord_bot.verification.cog.delete_message", new_callable=AsyncMock
        ) as mock_delete:
            await verification_cog._check_verification_message(guild=mock_guild, recreate=True)

            # Should not try to delete panel if no channel
            mock_delete.assert_not_called()

    async def test_channel_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test when the channel does not exist."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=None)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "verification_channel", 999)
            await session.commit()

        with patch(
            "discord_bot.verification.cog.delete_message", new_callable=AsyncMock
        ) as mock_delete:
            await verification_cog._check_verification_message(guild=mock_guild, recreate=True)

            mock_delete.assert_not_called()

    async def test_deletes_old_and_creates_new(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that deletes old panel and creates new one."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await config_service.set_value(123, "verification", "verification_channel", 111)
            await config_service.set_value(123, "verification", "_panel_message_id", 777)
            await config_service.set_value(123, "verification", "_panel_channel_id", 111)
            await session.commit()

        with (
            patch(
                "discord_bot.verification.panel.delete_message", new_callable=AsyncMock
            ) as mock_delete,
            patch.object(
                verification_cog, "_create_verification_message", new_callable=AsyncMock
            ) as mock_create,
        ):
            await verification_cog._check_verification_message(guild=mock_guild, recreate=True)

            mock_delete.assert_called_once()
            mock_create.assert_called_once()


class TestCreateVerificationMessagePermissions:
    """Tests for _create_verification_message with different permission states."""

    async def test_disabled_manually(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test panel with manually disabled verification."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.send = AsyncMock(return_value=MagicMock(id=888))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "verification_enabled", False)
            await config_service.set_value(
                123, "verification", "verification_disabled_message", "Disabled"
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()
            call_kwargs = mock_channel.send.call_args.kwargs
            # The message is now an embed
            assert "embed" in call_kwargs
            assert "Disabled" in (call_kwargs["embed"].description or "")

    async def test_mod_channel_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test panel when moderation channel does not exist."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.send = AsyncMock(return_value=MagicMock(id=888))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=None)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "verification_enabled", True)
            await config_service.set_value(123, "verification", "mod_notification_channel", 999)
            await config_service.set_value(
                123, "verification", "verification_disabled_message", "Channel not found"
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()

    async def test_no_send_permissions(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test panel when bot does not have send permissions."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 111
        mock_channel.send = AsyncMock(return_value=MagicMock(id=888))

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.name = "mod-channel"

        mock_permissions = MagicMock()
        mock_permissions.send_messages = False
        mock_mod_channel.permissions_for = MagicMock(return_value=mock_permissions)

        mock_bot_member = MagicMock(spec=discord.Member)
        mock_bot_member.id = 999

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)
        mock_guild.get_member = MagicMock(return_value=mock_bot_member)

        mock_user = MagicMock()
        mock_user.id = 999
        object.__setattr__(verification_cog.bot, "user", mock_user)

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_value(123, "verification", "verification_enabled", True)
            await config_service.set_value(123, "verification", "mod_notification_channel", 222)
            await config_service.set_value(
                123, "verification", "verification_disabled_message", "No permissions"
            )

            config = await config_service.get_all_config(guild_id=123, cog_name="verification")
            await verification_cog._create_verification_message(
                guild=mock_guild,
                channel=mock_channel,
                config=config,
                config_service=config_service,
                session=session,
            )

            mock_channel.send.assert_called_once()


class TestHandleVerificationStartExtended:
    """Additional tests for handle_verification_start."""

    async def test_verification_disabled(self, verification_cog: VerificationCog) -> None:
        """Test start when verification is disabled."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.name = "TestUser"
        interaction.user.display_name = "TestUser"
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "verification_enabled": False,
            "verification_disabled_message": "Verification is disabled",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args
            assert "disabled" in args[0][0]

    async def test_already_verified_regular(self, verification_cog: VerificationCog) -> None:
        """Test start when user already has regular verification role."""
        mock_role = MagicMock()
        mock_role.id = 100

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.name = "TestUser"
        interaction.user.display_name = "TestUser"
        interaction.user.roles = [mock_role]
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "verification_enabled": True,
            "blocking_roles": [100, 200],
            "already_verified_message": "You are already verified",
        }

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = config_values

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args
            assert "You are already verified" in args[0][0]

    async def test_already_verified_ally(self, verification_cog: VerificationCog) -> None:
        """Test start when user already has ally verification role."""
        mock_role = MagicMock()
        mock_role.id = 200

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.name = "TestUser"
        interaction.user.display_name = "TestUser"
        interaction.user.roles = [mock_role]
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "verification_enabled": True,
            "blocking_roles": [100, 200],
            "already_verified_message": "You are already verified as ally",
        }

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = config_values

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.ALLY
            )

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args
            assert "You are already verified" in args[0][0]

    async def test_already_verified_cross_regular_to_ally(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that user with regular role cannot verify as ally."""
        mock_role = MagicMock()
        mock_role.id = 100  # Regular member role

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.name = "TestUser"
        interaction.user.display_name = "TestUser"
        interaction.user.roles = [mock_role]
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "verification_enabled": True,
            "blocking_roles": [100, 200],
            "already_verified_message": "You are already verified",
        }

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = config_values

            # Try to verify as ally while having member role
            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.ALLY
            )

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args
            assert "You are already verified" in args[0][0]

    async def test_already_verified_cross_ally_to_regular(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that user with ally role cannot verify as regular."""
        mock_role = MagicMock()
        mock_role.id = 200  # Ally role

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.user.name = "TestUser"
        interaction.user.display_name = "TestUser"
        interaction.user.roles = [mock_role]
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values: dict[str, object] = {
            "verification_enabled": True,
            "blocking_roles": [100, 200],
            "already_verified_message": "You are already verified",
        }

        mock_mod_channel = MagicMock(spec=discord.TextChannel)

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel", return_value=mock_mod_channel),
        ):
            mock_config.return_value = config_values

            # Try to verify as regular while having ally role
            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args
            assert "You are already verified" in args[0][0]


class TestOnInteraction:
    """Tests for on_interaction listener."""

    async def test_ignores_non_component_interaction(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that ignores interactions that are not component interactions."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.application_command

        with patch.object(verification_cog, "handle_accept", new_callable=AsyncMock) as mock_accept:
            await verification_cog.on_interaction(interaction)

            mock_accept.assert_not_called()

    async def test_handles_accept_button(self, verification_cog: VerificationCog) -> None:
        """Test handling of accept button."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:accept:123"}

        with patch.object(verification_cog, "handle_accept", new_callable=AsyncMock) as mock_accept:
            await verification_cog.on_interaction(interaction)

            mock_accept.assert_called_once_with(interaction=interaction, public_id="123")

    async def test_handles_reject_button(self, verification_cog: VerificationCog) -> None:
        """Test handling of reject button."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:reject:test456"}

        with patch.object(
            verification_cog, "show_rejection_select", new_callable=AsyncMock
        ) as mock_reject:
            await verification_cog.on_interaction(interaction)

            mock_reject.assert_called_once_with(interaction=interaction, public_id="test456")

    async def test_handles_any_string_accept_id(self, verification_cog: VerificationCog) -> None:
        """Test that accepts any string as public_id."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:accept:anystring"}

        with patch.object(verification_cog, "handle_accept", new_callable=AsyncMock) as mock_accept:
            await verification_cog.on_interaction(interaction)

            # Now accepts any string as public_id
            mock_accept.assert_called_once_with(interaction=interaction, public_id="anystring")

    async def test_handles_any_string_reject_id(self, verification_cog: VerificationCog) -> None:
        """Test that accepts any string as public_id for reject."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:reject:some_nanoid"}

        with patch.object(
            verification_cog, "show_rejection_select", new_callable=AsyncMock
        ) as mock_reject:
            await verification_cog.on_interaction(interaction)

            mock_reject.assert_called_once_with(interaction=interaction, public_id="some_nanoid")

    async def test_ignores_unrelated_custom_id(self, verification_cog: VerificationCog) -> None:
        """Test that ignores unrelated custom_ids."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "other:button:123"}

        with (
            patch.object(verification_cog, "handle_accept", new_callable=AsyncMock) as mock_accept,
            patch.object(
                verification_cog, "show_rejection_select", new_callable=AsyncMock
            ) as mock_reject,
        ):
            await verification_cog.on_interaction(interaction)

            mock_accept.assert_not_called()
            mock_reject.assert_not_called()

    async def test_handles_no_data(self, verification_cog: VerificationCog) -> None:
        """Test handling when interaction.data is None."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = None
        interaction.response.is_done.return_value = False

        with patch.object(verification_cog, "handle_accept", new_callable=AsyncMock) as mock_accept:
            await verification_cog.on_interaction(interaction)

            mock_accept.assert_not_called()


class TestOnCogToggled:
    """Tests for on_cog_toggled."""

    async def test_enabled_creates_panel(self, verification_cog: VerificationCog) -> None:
        """Test that enabling the cog creates the panel."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.name = "Test Guild"

        with patch.object(
            verification_cog, "_check_verification_message", new_callable=AsyncMock
        ) as mock_check:
            await verification_cog.on_cog_toggled(guild, enabled=True)

            mock_check.assert_called_once_with(guild=guild, recreate=True)

    async def test_disabled_deletes_panel(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that disabling the cog deletes the panel."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.name = "Test Guild"

        # Configure existing panel
        async with test_database.session() as session:
            config_service = ConfigService(session=session)
            await config_service.set_value(
                guild_id=123, cog_name="verification", key=ConfigKey.PANEL_MESSAGE_ID, value=999
            )
            await config_service.set_value(
                guild_id=123, cog_name="verification", key=ConfigKey.PANEL_CHANNEL_ID, value=888
            )
            await session.commit()

        with patch(
            "discord_bot.verification.cog.delete_message", new_callable=AsyncMock
        ) as mock_delete:
            mock_delete.return_value = True
            await verification_cog.on_cog_toggled(guild, enabled=False)

            mock_delete.assert_called_once_with(guild=guild, channel_id=888, message_id=999)

    async def test_disabled_no_panel_configured(self, verification_cog: VerificationCog) -> None:
        """Test disable when there is no panel configured."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.name = "Test Guild"

        # Should not fail
        await verification_cog.on_cog_toggled(guild, enabled=False)


class TestCheckVerificationMessageCogDisabled:
    """Tests for _check_verification_message when cog is disabled."""

    async def test_returns_early_when_cog_disabled(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that returns early if cog is disabled."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123

        # Explicitly disable the cog (enabled by default)
        async with test_database.session() as session:
            config_service = ConfigService(session=session)
            await config_service.set_cog_enabled(
                guild_id=123, cog_name="verification", enabled=False
            )
            await session.commit()

        with patch.object(
            verification_cog, "_create_verification_message", new_callable=AsyncMock
        ) as mock_create:
            await verification_cog._check_verification_message(guild, recreate=False)

            # Should not create message if cog is disabled
            mock_create.assert_not_called()


class TestGetAllConfigWithService:
    """Tests for _get_all_config with provided config_service."""

    async def test_uses_provided_config_service(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that uses the provided config_service."""
        async with test_database.session() as session:
            config_service = ConfigService(session=session)

            # Call with provided config_service
            result = await verification_cog._get_all_config(
                guild_id=123, config_service=config_service
            )

            assert isinstance(result, dict)


class TestGetModChannelEdgeCases:
    """Tests for _get_mod_channel edge cases."""

    def test_bot_user_none(self, verification_cog: VerificationCog) -> None:
        """Test when bot.user is None."""
        with patch.object(verification_cog.bot, "user", None):
            guild = MagicMock(spec=discord.Guild)
            mod_channel = MagicMock(spec=discord.TextChannel)
            guild.get_channel = MagicMock(return_value=mod_channel)

            config = {"mod_notification_channel": 123}

            result = verification_cog._get_mod_channel(guild, config)

            assert result is None

    def test_bot_member_not_found(self, verification_cog: VerificationCog) -> None:
        """Test when bot is not a member of the guild."""
        mock_user = MagicMock()
        mock_user.id = 999

        with patch.object(verification_cog.bot, "user", mock_user):
            guild = MagicMock(spec=discord.Guild)
            mod_channel = MagicMock(spec=discord.TextChannel)
            guild.get_channel = MagicMock(return_value=mod_channel)
            guild.get_member = MagicMock(return_value=None)

            config = {"mod_notification_channel": 123}

            result = verification_cog._get_mod_channel(guild, config)

            assert result is None


class TestValidateModActionEdgeCases:
    """Tests for _validate_mod_action edge cases."""

    async def test_no_guild(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test when there is no guild."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None

        async with test_database.session() as session:
            result = await verification_cog._validate_mod_action(
                interaction=interaction,
                public_id="test1",
                session=session,
                permission_error_key=ConfigKey.NO_PERMISSION_APPROVE_MESSAGE,
                permission_error_default="No permissions",
            )

        assert result is None

    async def test_user_not_member(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test when user is not a Member."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.user = MagicMock(spec=discord.User)  # User, no Member

        async with test_database.session() as session:
            result = await verification_cog._validate_mod_action(
                interaction=interaction,
                public_id="test1",
                session=session,
                permission_error_key=ConfigKey.NO_PERMISSION_APPROVE_MESSAGE,
                permission_error_default="No permissions",
            )

        assert result is None


class TestHandleVerificationStartCogDisabled:
    """Tests for handle_verification_start when cog is disabled."""

    async def test_cog_disabled_returns_early(self, verification_cog: VerificationCog) -> None:
        """Test that returns early if cog is disabled."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()

        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            # Should not defer if cog is disabled
            interaction.response.defer.assert_not_called()

    async def test_mod_channel_not_accessible(self, verification_cog: VerificationCog) -> None:
        """Test when moderation channel is not accessible."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 456
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values = {
            "verification_enabled": True,
            "mod_notification_channel": 999,
            "verification_disabled_message": "System not available",
        }

        with (
            patch.object(
                verification_cog, "_is_cog_enabled", new_callable=AsyncMock
            ) as mock_enabled,
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch.object(verification_cog, "_get_mod_channel") as mock_mod_channel,
        ):
            mock_enabled.return_value = True
            mock_config.return_value = config_values
            mock_mod_channel.return_value = None  # Channel not accessible

            await verification_cog.handle_verification_start(
                interaction=interaction, verification_type=VerificationType.REGULAR
            )

            # Should send system unavailable message
            interaction.followup.send.assert_called_once()


class TestOnMessageCogDisabled:
    """Tests for on_message when cog is disabled."""

    async def test_cog_disabled_returns_early(self, verification_cog: VerificationCog) -> None:
        """Test that returns early if cog is disabled."""
        verification_cog._pending_dm_verifications[456] = (123, 1)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog.on_message(message)

            # Should not send anything if cog is disabled
            message.channel.send.assert_not_called()


class TestUpdateModMessageWithRejectionReason:
    """Tests for _update_mod_message_for_review with rejection history."""

    async def test_history_includes_rejection_reason(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that history includes the rejection reason."""
        # Create a previously rejected verification
        async with test_database.session() as session:
            service = VerificationService(session)
            old_request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(old_request.id, "url1", "url2", "Test Guild")
            await service.reject(old_request.id, 789, "ModUser", "Incorrect captures", "Test Guild")
            await session.commit()

        # Create new verification with mod_message_id
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id, url1="url3", url2="url4", guild_name="Test Guild"
            )
            request.mod_message_id = 777  # Required so method doesn't return early
            await session.commit()
            public_id = request.public_id

        # Mock moderation message
        mod_message = MagicMock()
        mod_message.content = "Original message"
        mod_message.edit = AsyncMock()

        # Mock channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mod_message)

        config_values: dict[str, Any] = {
            "mod_message_template": "{username} - {status}",
            "status_pending_review": "Pending",
            "accept_button_text": "Accept",
            "reject_button_text": "Reject",
        }

        async with test_database.session() as session:
            service = VerificationService(session)
            fetched_request = await service.get_by_public_id(public_id)
            assert fetched_request is not None

            await verification_cog._update_mod_message_for_review(
                channel=mock_channel,
                request=fetched_request,
                verification_service=service,
                config=config_values,
            )

            # Verify that edited message contains rejection reason
            call_args = mod_message.edit.call_args
            # Content is now in the first embed
            assert "embeds" in call_args.kwargs
            main_embed = call_args.kwargs["embeds"][0]
            # History is now a field with the rejection reason
            history_field = next(
                (f for f in main_embed.fields if f.name == "History"),
                None,
            )
            assert history_field is not None
            assert "Incorrect captures" in history_field.value


class TestHandleAcceptCogDisabled:
    """Tests for handle_accept when cog is disabled."""

    async def test_cog_disabled_returns_early(self, verification_cog: VerificationCog) -> None:
        """Test that returns early if cog is disabled."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()

        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog.handle_accept(interaction, public_id="test1")

            # Should not do anything if cog is disabled
            interaction.response.defer.assert_not_called()


class TestHandleAcceptRoleNotFound:
    """Tests for handle_accept when role is not found."""

    async def test_role_add_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test when a role to add does not exist in the guild."""
        from discord_bot.verification.enums import VerificationType

        # Create request
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await session.commit()
            public_id = request.public_id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)  # Role not found
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values = {
            "mod_roles": [],
            "regular_roles_add": [999],  # This role does not exist
            "regular_roles_remove": [],
            "approval_message_regular": "Approved!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, public_id=public_id)

            # Should not try to add roles since it does not exist
            mock_member.add_roles.assert_not_called()

    async def test_role_remove_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test when a role to remove does not exist in the guild."""
        from discord_bot.verification.enums import VerificationType

        # Create request
        async with test_database.session() as session:
            service = VerificationService(session)
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
            await session.commit()
            public_id = request.public_id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.remove_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)  # Role not found
        mock_guild.get_channel = MagicMock(return_value=None)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [999],  # This role does not exist
            "approval_message_regular": "Approved!",
            "mod_notification_channel": None,
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, public_id=public_id)

            # Should not try to remove roles since it does not exist
            mock_member.remove_roles.assert_not_called()


class TestHandleAcceptDeleteModMessage:
    """Tests for handle_accept deleting moderation message."""

    async def test_deletes_mod_message_when_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that deletes mod message when configured."""
        from discord_bot.verification.enums import VerificationType

        # Create request with mod_message_id
        async with test_database.session() as session:
            service = VerificationService(session)
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
            request.mod_message_id = 777
            await session.commit()
            public_id = request.public_id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.add_roles = AsyncMock()
        mock_member.send = AsyncMock()

        mock_mod_message = MagicMock()
        mock_mod_message.delete = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=None)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values = {
            "mod_roles": [],
            "regular_roles_add": [],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved!",
            "mod_notification_channel": 888,
            "delete_processed_messages": True,  # Configured to delete
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_accept(interaction=interaction, public_id=public_id)

            # Should delete the message
            mock_mod_message.delete.assert_called_once()


class TestShowRejectionSelectCogDisabled:
    """Tests for show_rejection_select when cog is disabled."""

    async def test_cog_disabled_returns_early(self, verification_cog: VerificationCog) -> None:
        """Test that returns early if cog is disabled."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog.show_rejection_select(interaction, public_id="test1")

            # Should not send anything if cog is disabled
            interaction.response.send_message.assert_not_called()


class TestHandleRejectCogDisabled:
    """Tests for handle_reject when cog is disabled."""

    async def test_cog_disabled_returns_early(self, verification_cog: VerificationCog) -> None:
        """Test that returns early if cog is disabled."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 123
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()

        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog.handle_reject(
                interaction=interaction, public_id="test1", reason="Test"
            )

            # Should not do anything if the cog is disabled
            interaction.response.defer.assert_not_called()


class TestHandleRejectDeleteModMessage:
    """Tests for handle_reject deleting moderation message."""

    async def test_deletes_mod_message_when_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that deletes mod message when configured."""
        from discord_bot.verification.enums import VerificationType

        # Create request with mod_message_id
        async with test_database.session() as session:
            service = VerificationService(session)
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
            request.mod_message_id = 777
            await session.commit()
            public_id = request.public_id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_mod_message = MagicMock()
        mock_mod_message.delete = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        config_values = {
            "mod_roles": [],
            "rejection_message": "Your verification was rejected: {reason}",
            "verification_type_regular_display": "Normal",
            "mod_notification_channel": 888,
            "delete_processed_messages": True,  # Configured to delete
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_reject(
                interaction, public_id, reason="Incorrect captures"
            )

            # Should delete the message
            mock_mod_message.delete.assert_called_once()


class TestHandleReview:
    """Tests for handle_review (review of auto-rejects)."""

    async def test_review_no_guild(self, verification_cog: VerificationCog) -> None:
        """Test that checks there is a guild."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = None

        await verification_cog.handle_review(interaction, public_id="test1")

    async def test_review_not_mod(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that requires moderator permissions."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = False
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        # Enable cog
        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        config_values = {
            "mod_roles": [999],  # User does not have this role
            "no_permission_reject_message": "You do not have permission",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_review(interaction, public_id="test1")

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert call_args.kwargs["ephemeral"] is True

    async def test_review_not_auto_rejected(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that only allows reviewing auto-rejections."""
        # Create manually rejected request (not Auto)
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.reject(
                request_id=request.id,
                reviewer_id=789,
                reviewer_username="ModUser",
                reason="Manual reason",
                guild_name="Test Guild",
            )
            await session.commit()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        config_values: dict[str, Any] = {"mod_roles": []}

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_review(interaction, public_id=request.public_id)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "was not auto-rejected" in call_args.kwargs["content"]
            assert call_args.kwargs["ephemeral"] is True

    async def test_review_not_latest(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that only allows reviewing the latest verification."""
        # Create two requests, reject both
        async with test_database.session() as session:
            service = VerificationService(session)
            request1 = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.reject(request1.id, 0, "Auto", "Auto reason", "Test Guild")

            request2 = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.ALLY,
            )
            await service.reject(request2.id, 0, "Auto", "Another auto reason", "Test Guild")
            await session.commit()
            old_request_public_id = request1.public_id

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        config_values: dict[str, Any] = {"mod_roles": []}

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            # Try to review the old request
            await verification_cog.handle_review(interaction, old_request_public_id)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "latest verification" in call_args.kwargs["content"]
            assert call_args.kwargs["ephemeral"] is True

    async def test_review_success(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test successful review of auto-reject."""
        # Create auto-rejected request
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            # Reject with Auto
            await service.reject(
                request_id=request.id,
                reviewer_id=0,
                reviewer_username="Auto",
                reason="Auto reasonmatica",
                guild_name="Test Guild",
            )
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        # Mock moderation message
        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.description = "Request from TestUser\n❌ Auto-rejected"
        mock_mod_message.embeds = [mock_embed]
        mock_mod_message.edit = AsyncMock()

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        # Mock for tracker message
        mock_tracker_message = MagicMock()
        mock_tracker_message.id = 9999
        mock_mod_channel.send = AsyncMock(return_value=mock_tracker_message)
        # Mock history for tracker positioning
        mock_mod_channel.history = MagicMock(return_value=AsyncIteratorMock([]))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.name = "ModUser"
        interaction.user.display_name = "ModUser"
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        config_values = {
            "mod_roles": [],
            "mod_notification_channel": 888,
            "status_pending_review": "⏳ Pending",
            "status_rejected": "❌ Auto-rejected",
            "accept_button_text": "Accept",
            "reject_button_text": "Reject",
            "tracker_title": "📋 Pending Verifications",
        }

        # Save mod_message_id in the request
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.set_mod_message_id(request_id, 999)
            await session.commit()

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_review(interaction, public_id)

            # Verify successful response
            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "manual review" in call_args.kwargs["content"]
            assert call_args.kwargs["ephemeral"] is True

            # Verify that the moderation message was edited
            mock_mod_message.edit.assert_called_once()
            edit_kwargs = mock_mod_message.edit.call_args.kwargs
            assert edit_kwargs["view"] is not None  # Has buttons

        # Verify state in DB
        async with test_database.session() as session:
            service = VerificationService(session)
            updated_request = await service.get_by_public_id(public_id)
            assert updated_request is not None
            assert updated_request.status == VerificationStatus.PENDING_REVIEW
            assert updated_request.reviewed_by_id is None
            assert updated_request.reviewed_by_username is None

    async def test_review_cog_disabled(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that handle_review returns if cog is disabled."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        # Mock cog disabled
        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = False

            await verification_cog.handle_review(interaction, public_id="test1")

            # Should not call send_message
            interaction.response.send_message.assert_not_called()

    async def test_review_request_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that handle_review handles request not found."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        # Enable cog
        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        config_values: dict[str, Any] = {
            "mod_roles": [],
            "request_not_found_message": "Request does not exist",
        }

        with patch.object(
            verification_cog, "_get_all_config", new_callable=AsyncMock
        ) as mock_config:
            mock_config.return_value = config_values

            await verification_cog.handle_review(interaction, public_id="nonexistent")

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "does not exist" in call_args.kwargs["content"]
            assert call_args.kwargs["ephemeral"] is True


class TestAutoProcessingEdgeCases:
    """Tests for auto-processing edge cases."""

    async def test_api_error_non_422_shows_error(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that non-422 API errors show error message."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import VerificationAPIResult

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild
        mock_mod_channel.send = AsyncMock(return_value=mock_mod_message)

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.NONE,  # No auto-process
        }

        # Mock API returns 500 (internal error)
        api_result = VerificationAPIResult(
            success=False,
            status_code=500,
            error_message="Internal server error",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that the request stayed in PENDING_REVIEW
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_REVIEW

    async def test_player_info_template_formatted(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that player_info_template is formatted correctly."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild
        mock_mod_channel.send = AsyncMock(return_value=mock_mod_message)

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.NONE,
            "player_info_template": "Name: {name}, Level: {level}",
        }

        api_response = VerificationAPIResponse(
            name="TestPlayer",
            level=15,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that the request stayed in PENDING_REVIEW
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_REVIEW

    async def test_legacy_boolean_true_auto_mode(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test compatibility with boolean True value for verification_automatic."""
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": True,  # Legacy boolean
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved",
            "delete_processed_messages": True,
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that was auto-approved (True = BOTH)
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED

    async def test_auto_approve_ally_uses_ally_roles(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that ally auto-approval uses ally roles."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.ALLY,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_ally_role = MagicMock(spec=discord.Role)
        mock_ally_role.id = 888
        mock_ally_role.name = "Ally"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_ally_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "ally_roles_add": [888],
            "ally_roles_remove": [],
            "approval_message_ally": "Welcome ally",
            "delete_processed_messages": True,
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="82DK",  # Has regiment - OK for ally
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that was auto-approved
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED

        # Verify that ally role was added
        mock_member.add_roles.assert_called_once_with(mock_ally_role)

    async def test_auto_approve_forbidden_on_add_roles(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that Forbidden on add_roles does not break the flow."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.name = "TestUser"
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Missing permissions")
        )
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved",
            "delete_processed_messages": True,
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            # Should not throw exception
            await verification_cog.on_message(message)

        # Verify that the request was approved anyway
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED

    async def test_auto_approve_forbidden_on_send_dm(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that Forbidden on send DM does not break the flow."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Cannot send DM"))
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved",
            "delete_processed_messages": True,
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that the request was approved
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED

    async def test_auto_approve_no_delete_edits_message(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that auto-approval without delete_processed_messages edits the message."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved",
            "delete_processed_messages": False,  # Don't delete, edit
            "status_pending_review": "⏳ Pending",
            "status_approved": "✅ Approved by {moderator}",
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that was edited instead of deleted
        mock_mod_message.delete.assert_not_called()
        mock_mod_message.edit.assert_called_once()

    async def test_auto_reject_no_delete_edits_with_review_button(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that auto-reject without delete adds review button."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import VerificationAPIResult

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,
            "reject_wrong_captures": "Invalid captures",
            "rejection_message": "Rejected: {reason}",
            "delete_processed_messages": False,  # Don't delete
            "status_pending_review": "⏳ Pending",
            "status_rejected": "❌ Rejected: {reason}",
            "auto_reject_review_window": 30,  # 30 minutes for review
            "review_button_text": "Revisar",
        }

        api_result = VerificationAPIResult(
            success=False,
            status_code=422,
            error_message="Invalid images",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that was edited with view
        mock_mod_message.delete.assert_not_called()
        mock_mod_message.edit.assert_called_once()
        edit_kwargs = mock_mod_message.edit.call_args.kwargs
        assert edit_kwargs["view"] is not None

    async def test_auto_reject_forbidden_on_send_dm(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that Forbidden on rejection DM does not break the flow."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import VerificationAPIResult

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Cannot send DM"))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,
            "reject_wrong_captures": "Invalid captures",
            "rejection_message": "Rejected: {reason}",
            "delete_processed_messages": True,
        }

        api_result = VerificationAPIResult(
            success=False,
            status_code=422,
            error_message="Invalid images",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that the request was rejected
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.REJECTED

    async def test_ready_for_manual_approval_reject_only_mode(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test ready for manual approval when mode is REJECT_ONLY."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_mod_role = MagicMock(spec=discord.Role)
        mock_mod_role.mention = "<@&999>"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_mod_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild
        mock_mod_channel.send = AsyncMock(return_value=mock_mod_message)

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,  # Only rejects, doesn't approve
            "mod_roles": [999],
            "status_pending_review": "⏳ Pending",
            "status_ready_for_approval": "✅ Listo - {roles}",
        }

        # API returns successful response that passes all verifications
        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that request stayed in PENDING_REVIEW (not auto-approved)
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_REVIEW

    async def test_auto_approve_forbidden_on_remove_roles(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that Forbidden on remove_roles does not break the flow."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_role_add = MagicMock(spec=discord.Role)
        mock_role_add.id = 999
        mock_role_add.name = "Verified"

        mock_role_remove = MagicMock(spec=discord.Role)
        mock_role_remove.id = 888
        mock_role_remove.name = "Unverified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.name = "TestUser"
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Missing permissions")
        )

        def get_role_side_effect(role_id: int) -> MagicMock | None:
            if role_id == 999:
                return mock_role_add
            elif role_id == 888:
                return mock_role_remove
            return None

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(side_effect=get_role_side_effect)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [888],  # Has roles to remove
            "approval_message_regular": "Approved",
            "delete_processed_messages": True,
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            # Should not throw exception
            await verification_cog.on_message(message)

        # Verify that the request was approved
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.APPROVED

    async def test_auto_approve_no_pending_status_appends(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that without status_pending_review it appends at the end."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved",
            "delete_processed_messages": False,
            "status_pending_review": "",  # Without pending status
            "status_approved": "✅ Approved by {moderator}",
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that was edited
        mock_mod_message.edit.assert_called_once()

    async def test_auto_reject_no_review_window(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test auto-reject without review window (view=None)."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import VerificationAPIResult

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,
            "reject_wrong_captures": "Invalid captures",
            "rejection_message": "Rejected: {reason}",
            "delete_processed_messages": False,
            "status_pending_review": "⏳ Pending",
            "status_rejected": "❌ Rejected: {reason}",
            "auto_reject_review_window": 0,  # Without review window
        }

        api_result = VerificationAPIResult(
            success=False,
            status_code=422,
            error_message="Invalid images",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that was edited without view
        mock_mod_message.edit.assert_called_once()
        edit_kwargs = mock_mod_message.edit.call_args.kwargs
        assert edit_kwargs["view"] is None

    async def test_auto_reject_no_pending_status_appends(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that without status_pending_review it appends at end for reject."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import VerificationAPIResult

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,
            "reject_wrong_captures": "Invalid captures",
            "rejection_message": "Rejected: {reason}",
            "delete_processed_messages": False,
            "status_pending_review": "",  # Without pending status
            "status_rejected": "❌ Rejected: {reason}",
            "auto_reject_review_window": 0,
        }

        api_result = VerificationAPIResult(
            success=False,
            status_code=422,
            error_message="Invalid images",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that was edited
        mock_mod_message.edit.assert_called_once()


class TestOnInteractionReview:
    """Tests for on_interaction with review button."""

    async def test_review_button_invalid_id(self, verification_cog: VerificationCog) -> None:
        """Test handling of invalid ID in review button."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:review:invalid"}
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        # Enable cog
        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = True

            # Should not throw exception
            await verification_cog.on_interaction(interaction)

    async def test_review_button_missing_parts(self, verification_cog: VerificationCog) -> None:
        """Test handling of custom_id with missing parts."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:review"}  # Without request_id

        with patch.object(
            verification_cog, "_is_cog_enabled", new_callable=AsyncMock
        ) as mock_enabled:
            mock_enabled.return_value = True

            # Should not throw exception
            await verification_cog.on_interaction(interaction)

    async def test_review_button_valid_id(self, verification_cog: VerificationCog) -> None:
        """Test handling of valid ID in review button."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "verification:review:42"}

        with (
            patch.object(
                verification_cog, "_is_cog_enabled", new_callable=AsyncMock
            ) as mock_enabled,
            patch.object(
                verification_cog, "handle_review", new_callable=AsyncMock
            ) as mock_handle_review,
        ):
            mock_enabled.return_value = True

            await verification_cog.on_interaction(interaction)

            mock_handle_review.assert_called_once_with(interaction=interaction, public_id="42")


class TestGetPendingVerification:
    """Tests for _get_pending_verification."""

    async def test_returns_none_when_no_pending(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that returns None when no pending verification."""
        result = await verification_cog._get_pending_verification(user_id=99999)
        assert result is None


class TestHandleReviewRevertFails:
    """Tests for handle_review when revert fails."""

    async def test_revert_fails(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test handling when revert_to_pending_review fails."""
        # Create auto-rejected request
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.reject(
                request_id=request.id,
                reviewer_id=0,
                reviewer_username="Auto",
                reason="Auto reason",
                guild_name="Test Guild",
            )
            await session.commit()
            public_id = request.public_id

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 789
        interaction.user.roles = []
        interaction.user.guild_permissions = MagicMock()
        interaction.user.guild_permissions.manage_guild = True
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        async with test_database.session() as session:
            from discord_bot.common.services.config_service import ConfigService

            config_service = ConfigService(session)
            await config_service.set_cog_enabled(123, "verification", True)
            await session.commit()

        config_values: dict[str, Any] = {"mod_roles": []}

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.VerificationService.revert_to_pending_review",
                new_callable=AsyncMock,
            ) as mock_revert,
        ):
            mock_config.return_value = config_values
            mock_revert.return_value = False  # Revert fails

            await verification_cog.handle_review(interaction, public_id)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "Could not revert" in call_args.kwargs["content"]


class TestLegacyBooleanAutoMode:
    """Tests for compatibility with legacy boolean verification_automatic."""

    async def test_legacy_false_disables_auto(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that legacy False disables auto-processing."""
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = []

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild
        mock_mod_channel.send = AsyncMock(return_value=mock_mod_message)

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": False,  # Legacy boolean False
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Should not auto-approve, stays in PENDING_REVIEW
        async with test_database.session() as session:
            service = VerificationService(session)
            updated = await service.get_by_public_id(public_id)
            assert updated is not None
            assert updated.status == VerificationStatus.PENDING_REVIEW


class TestStatusReplacementInFormatted:
    """Tests for status replacement when it IS in formatted."""

    async def test_auto_approve_replaces_pending_status(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that auto-approval replaces the pending status."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import (
            VerificationAPIResponse,
            VerificationAPIResult,
        )

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Message already has pending status
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.description = "Request from TestUser\n\n⏳ Pending review"

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = [mock_embed]

        mock_role = MagicMock(spec=discord.Role)
        mock_role.id = 999
        mock_role.name = "Verified"

        mock_member = MagicMock(spec=discord.Member)
        mock_member.display_name = "TestUser"
        mock_member.send = AsyncMock()
        mock_member.add_roles = AsyncMock()
        mock_member.remove_roles = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)
        mock_guild.get_role = MagicMock(return_value=mock_role)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.BOTH,
            "regular_roles_add": [999],
            "regular_roles_remove": [],
            "approval_message_regular": "Approved",
            "delete_processed_messages": False,
            "mod_message_template": "Request from {username}\n\n{status}",  # Template with status
            "status_pending_review": "⏳ Pending review",
            "status_approved": "✅ Approved by {moderator}",
        }

        api_response = VerificationAPIResponse(
            name="TestUser",
            level=10,
            regiment="",
            faction="colonial",
            shard="ABLE",
            ingame_time="100, 00:00",
            war_number=100,
            current_ingame_time="100, 01:00",
        )
        api_result = VerificationAPIResult(
            success=True,
            status_code=200,
            response=api_response,
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that was edited
        mock_mod_message.edit.assert_called_once()

    async def test_auto_reject_replaces_pending_status(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that auto-rejection replaces pending status."""
        from discord_bot.verification.enums import AutoProcessMode
        from discord_bot.verification.models import VerificationAPIResult

        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.set_mod_message_id(request_id=request.id, message_id=999)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Message already has pending status
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.description = "Request from TestUser\n\n⏳ Pending"

        mock_mod_message = MagicMock()
        mock_mod_message.id = 999
        mock_mod_message.delete = AsyncMock()
        mock_mod_message.edit = AsyncMock()
        mock_mod_message.embeds = [mock_embed]

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.id = 888
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_channel.guild = mock_guild

        mock_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        object.__setattr__(verification_cog.bot, "get_guild", MagicMock(return_value=mock_guild))

        mock_user = MagicMock()
        mock_user.id = 111
        object.__setattr__(verification_cog.bot, "user", mock_user)

        mock_settings = MagicMock()
        mock_settings.verification.api_url = "https://api.example.com"
        mock_settings.verification.api_key = "test-key"
        mock_settings.verification.api_timeout = 30
        object.__setattr__(verification_cog.bot, "settings", mock_settings)

        message = MagicMock(spec=discord.Message)
        message.guild = None
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 456
        message.author.name = "TestUser"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()

        attachment1 = MagicMock()
        attachment1.content_type = "image/png"
        attachment1.url = "https://cdn.discordapp.com/attachments/123/456/1.png"
        attachment2 = MagicMock()
        attachment2.content_type = "image/jpeg"
        attachment2.url = "https://cdn.discordapp.com/attachments/123/456/2.jpg"
        message.attachments = [attachment1, attachment2]

        config_values: dict[str, Any] = {
            "screenshots_received_message": "Screenshots received",
            "mod_notification_channel": 888,
            "verification_automatic": AutoProcessMode.REJECT_ONLY,
            "reject_wrong_captures": "Invalid captures",
            "rejection_message": "Rejected: {reason}",
            "delete_processed_messages": False,
            "mod_message_template": "Request from {username}\n\n{status}",  # Template with status
            "status_pending_review": "⏳ Pending",
            "status_rejected": "❌ Rejected: {reason}",
            "auto_reject_review_window": 0,
        }

        api_result = VerificationAPIResult(
            success=False,
            status_code=422,
            error_message="Invalid images",
        )

        with (
            patch.object(
                verification_cog, "_get_all_config", new_callable=AsyncMock
            ) as mock_config,
            patch(
                "discord_bot.verification.handlers.flow.call_verification_api",
                new_callable=AsyncMock,
            ) as mock_api,
        ):
            mock_config.return_value = config_values
            mock_api.return_value = api_result

            await verification_cog.on_message(message)

        # Verify that was edited
        mock_mod_message.edit.assert_called_once()


class TestUpdateModMessageForManualReview:
    """Tests for update_mod_message_for_manual_review."""

    @pytest.mark.asyncio
    async def test_replaces_auto_rejected_status_with_pending_review(
        self, mock_discord_guild: MagicMock
    ) -> None:
        """Test that replaces auto-rejected status with pending review status."""
        request = MagicMock()
        request.mod_message_id = 999
        request.username = "TestUser"
        request.user_id = 456
        request.verification_type = VerificationType.REGULAR
        request.rejection_reason = "Invalid captures"

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.guild = mock_discord_guild

        # Create a properly configured mock embed
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed.description = "User info\n\n❌ **Status:** Rejected by Auto: Invalid captures"
        mock_embed.title = "Verification Request"
        mock_embed.fields = []
        mock_embed.color = discord.Color.red()

        # Make copy() return a new mock with the same properties
        mock_embed_copy = MagicMock(spec=discord.Embed)
        mock_embed_copy.description = mock_embed.description
        mock_embed_copy.title = mock_embed.title
        mock_embed_copy.fields = []
        mock_embed.copy.return_value = mock_embed_copy

        mock_mod_message = MagicMock(spec=discord.Message)
        mock_mod_message.embeds = [mock_embed]
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_message.edit = AsyncMock()

        mock_discord_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        config: dict[str, Any] = {
            "mod_notification_channel": 888,
            "status_pending_review": "⏳ Pending review",
            "status_rejected": "❌ **Status:** Rejected by {moderator}: {reason}",
            "accept_button_text": "Accept",
            "reject_button_text": "Reject",
        }

        from discord_bot.verification.handlers import update_mod_message_for_manual_review

        await update_mod_message_for_manual_review(
            guild=mock_discord_guild,
            request=request,
            config=config,
            public_id="test1",
        )

        mock_mod_message.edit.assert_called_once()
        # Verify the view has accept/reject buttons
        call_kwargs = mock_mod_message.edit.call_args.kwargs
        assert "view" in call_kwargs
        assert call_kwargs["view"] is not None

    @pytest.mark.asyncio
    async def test_returns_early_when_no_embeds(self, mock_discord_guild: MagicMock) -> None:
        """Test that returns early when message has no embeds."""
        request = MagicMock()
        request.mod_message_id = 999
        request.username = "TestUser"
        request.user_id = 456
        request.verification_type = VerificationType.REGULAR
        request.rejection_reason = "Invalid captures"

        mock_mod_channel = MagicMock(spec=discord.TextChannel)
        mock_mod_channel.guild = mock_discord_guild

        mock_mod_message = MagicMock(spec=discord.Message)
        mock_mod_message.embeds = []
        mock_mod_channel.fetch_message = AsyncMock(return_value=mock_mod_message)
        mock_mod_message.edit = AsyncMock()

        mock_discord_guild.get_channel = MagicMock(return_value=mock_mod_channel)

        config: dict[str, Any] = {
            "mod_notification_channel": 888,
            "status_pending_review": "⏳ Pending review",
            "status_rejected": "❌ **Status:** Rejected by {moderator}: {reason}",
        }

        from discord_bot.verification.handlers import update_mod_message_for_manual_review

        await update_mod_message_for_manual_review(
            guild=mock_discord_guild,
            request=request,
            config=config,
            public_id="test1",
        )

        # Should not edit because no embeds
        mock_mod_message.edit.assert_not_called()


class TestGetLockedOptions:
    """Tests for get_locked_options."""

    def test_returns_empty_dict(self, verification_cog: VerificationCog) -> None:
        """Test that returns an empty dictionary."""
        result = verification_cog.get_locked_options()
        assert result == {}


class TestIsCogEnabled:
    """Tests for _is_cog_enabled."""

    async def test_returns_true_when_enabled(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that returns True when cog is enabled."""
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_cog_enabled(
                guild_id=123, cog_name="verification", enabled=True
            )
            await session.commit()

        cog = VerificationCog(verification_cog.bot)
        result = await cog._is_cog_enabled(123)
        assert result is True

    async def test_returns_false_when_disabled(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that returns False when cog is disabled."""
        cog = VerificationCog(verification_cog.bot)
        result = await cog._is_cog_enabled(999)
        assert result is False


class TestCreatePanelEmbed:
    """Tests for _create_panel_embed."""

    def test_creates_embed_with_text(self, verification_cog: VerificationCog) -> None:
        """Test that creates an embed with the provided text."""
        text = "Verification panel"
        embed = verification_cog._create_panel_embed(text)
        assert embed is not None
        assert isinstance(embed, discord.Embed)


class TestRebuildSingleEmbed:
    """Tests for _rebuild_single_embed."""

    async def test_returns_false_without_mod_message_id(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that returns False if there is no mod_message_id."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_request = MagicMock()
        mock_request.mod_message_id = None

        result = await verification_cog._rebuild_single_embed(
            guild=mock_guild,
            channel=mock_channel,
            request=mock_request,
            config={},
        )
        assert result is False

    async def test_returns_false_when_message_not_found(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that returns False if the message does not exist."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test Guild"

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))

        mock_request = MagicMock()
        mock_request.mod_message_id = 789

        result = await verification_cog._rebuild_single_embed(
            guild=mock_guild,
            channel=mock_channel,
            request=mock_request,
            config={},
        )
        assert result is False

    async def test_rebuilds_embed_successfully(self, verification_cog: VerificationCog) -> None:
        """Test that rebuilds the embed correctly."""
        mock_member = MagicMock(spec=discord.Member)
        mock_member.mention = "<@456>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_embed = MagicMock()
        mock_embed.description = "User: Test\n⏳ Status: Waiting"

        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [mock_embed]
        mock_message.edit = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_request = MagicMock()
        mock_request.id = 1
        mock_request.mod_message_id = 789
        mock_request.username = "TestUser"
        mock_request.user_id = 456
        mock_request.guild_id = 123
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.created_at = datetime.now(UTC)
        mock_request.player_info = None

        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "sections": [{"type": "text", "content": "User: {username}\n{status}"}]
            },
            ConfigKey.MOD_EMBED_ALLY: {
                "sections": [{"type": "text", "content": "User: {username}\n{status}"}]
            },
            ConfigKey.STATUS_AWAITING_SCREENSHOTS: "⏳ Awaiting screenshots",
            ConfigKey.ACCEPT_BUTTON_TEXT: "Accept",
            ConfigKey.REJECT_BUTTON_TEXT: "Reject",
        }

        # Mock database session for history lookup
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(verification_cog.bot.database, "session", return_value=mock_session),
            patch("discord_bot.verification.cog.VerificationService") as mock_service_class,
        ):
            mock_service = MagicMock()
            mock_service.get_user_history = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            result = await verification_cog._rebuild_single_embed(
                guild=mock_guild,
                channel=mock_channel,
                request=mock_request,
                config=config,
            )

        assert result is True
        mock_message.edit.assert_called_once()

    async def test_preserves_screenshot_embeds(self, verification_cog: VerificationCog) -> None:
        """Test that preserves screenshot embeds."""
        mock_member = MagicMock(spec=discord.Member)
        mock_member.mention = "<@456>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        main_embed = MagicMock()
        main_embed.description = "User: Test\n⏳ Status"
        main_embed.image = MagicMock()
        main_embed.image.url = None  # Main embed has no image

        screenshot_embed1 = MagicMock()
        screenshot_embed1.image = MagicMock()
        screenshot_embed1.image.url = "https://example.com/screenshot1.png"

        screenshot_embed2 = MagicMock()
        screenshot_embed2.image = MagicMock()
        screenshot_embed2.image.url = "https://example.com/screenshot2.png"

        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [main_embed, screenshot_embed1, screenshot_embed2]
        mock_message.edit = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_request = MagicMock()
        mock_request.id = 1
        mock_request.mod_message_id = 789
        mock_request.username = "TestUser"
        mock_request.user_id = 456
        mock_request.guild_id = 123
        mock_request.verification_type = VerificationType.ALLY
        mock_request.status = VerificationStatus.PENDING_REVIEW
        mock_request.created_at = datetime.now(UTC)
        mock_request.player_info = None

        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "sections": [{"type": "text", "content": "User: {username}\n{status}"}]
            },
            ConfigKey.MOD_EMBED_ALLY: {
                "sections": [{"type": "text", "content": "User: {username}\n{status}"}]
            },
            ConfigKey.STATUS_PENDING_REVIEW: "⏳ Pending",
            ConfigKey.ACCEPT_BUTTON_TEXT: "Accept",
            ConfigKey.REJECT_BUTTON_TEXT: "Reject",
        }

        # Mock database session for history lookup
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(verification_cog.bot.database, "session", return_value=mock_session),
            patch("discord_bot.verification.cog.VerificationService") as mock_service_class,
        ):
            mock_service = MagicMock()
            mock_service.get_user_history = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            result = await verification_cog._rebuild_single_embed(
                guild=mock_guild,
                channel=mock_channel,
                request=mock_request,
                config=config,
            )

        assert result is True
        call_args = mock_message.edit.call_args
        embeds = call_args.kwargs.get("embeds", [])
        assert len(embeds) == 3

    async def test_handles_empty_embeds(self, verification_cog: VerificationCog) -> None:
        """Test that handles messages without embeds."""
        mock_member = MagicMock(spec=discord.Member)
        mock_member.mention = "<@456>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = []
        mock_message.edit = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_request = MagicMock()
        mock_request.id = 1
        mock_request.mod_message_id = 789
        mock_request.username = "TestUser"
        mock_request.user_id = 456
        mock_request.guild_id = 123
        mock_request.verification_type = VerificationType.REGULAR
        mock_request.status = VerificationStatus.PENDING_SCREENSHOTS
        mock_request.created_at = datetime.now(UTC)
        mock_request.player_info = None

        config: dict[str, Any] = {
            ConfigKey.MOD_EMBED_REGULAR: {
                "sections": [{"type": "text", "content": "User: {username}\n{status}"}]
            },
            ConfigKey.MOD_EMBED_ALLY: {
                "sections": [{"type": "text", "content": "User: {username}\n{status}"}]
            },
            ConfigKey.STATUS_AWAITING_SCREENSHOTS: "⏳ Waiting",
        }

        # Mock database session for history lookup
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch.object(verification_cog.bot.database, "session", return_value=mock_session),
            patch("discord_bot.verification.cog.VerificationService") as mock_service_class,
        ):
            mock_service = MagicMock()
            mock_service.get_user_history = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            result = await verification_cog._rebuild_single_embed(
                guild=mock_guild,
                channel=mock_channel,
                request=mock_request,
                config=config,
            )

        assert result is True
        mock_message.edit.assert_called_once()


class TestRebuildPendingEmbedsForGuild:
    """Tests for _rebuild_pending_embeds_for_guild."""

    async def test_no_pending_for_guild(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that does nothing if there are no verifications for the guild."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        await verification_cog._rebuild_pending_embeds_for_guild(mock_guild)

    async def test_rebuilds_only_guild_verifications(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that only rebuilds verifications of the specified guild."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id,
                url1="https://cdn.discordapp.com/test1.png",
                url2="https://cdn.discordapp.com/test2.png",
                guild_name="Test Guild",
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)

            request2 = await service.create_request(
                guild_id=999,
                user_id=789,
                username="OtherUser",
                guild_name="Other Guild",
                verification_type=VerificationType.ALLY,
            )
            await service.update_screenshots(
                request_id=request2.id,
                url1="https://cdn.discordapp.com/other1.png",
                url2="https://cdn.discordapp.com/other2.png",
                guild_name="Other Guild",
            )
            await service.set_mod_message_id(request_id=request2.id, message_id=999)
            await session.commit()

        mock_member = MagicMock(spec=discord.Member)
        mock_member.mention = "<@456>"

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member = MagicMock(return_value=mock_member)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [MagicMock(description="User: Test\n⏳ Pending")]
        mock_message.edit = AsyncMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        config: dict[str, Any] = {
            ConfigKey.MOD_NOTIFICATION_CHANNEL: 888,
            ConfigKey.MOD_EMBED_REGULAR: {
                "sections": [{"type": "text", "content": "User: {username}\n{status}"}]
            },
            ConfigKey.MOD_EMBED_ALLY: {
                "sections": [{"type": "text", "content": "User: {username}\n{status}"}]
            },
            ConfigKey.STATUS_PENDING_REVIEW: "⏳ Pending",
            ConfigKey.ACCEPT_BUTTON_TEXT: "Accept",
            ConfigKey.REJECT_BUTTON_TEXT: "Reject",
        }

        with patch.object(
            ConfigService,
            "get_all_config",
            new_callable=AsyncMock,
            return_value=config,
        ):
            await verification_cog._rebuild_pending_embeds_for_guild(mock_guild)

        mock_message.edit.assert_called_once()

    async def test_skips_no_mod_channel_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that does nothing if no mod channel is configured."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id,
                url1="https://cdn.discordapp.com/test1.png",
                url2="https://cdn.discordapp.com/test2.png",
                guild_name="Test Guild",
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)
            await session.commit()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        with patch.object(
            ConfigService,
            "get_all_config",
            new_callable=AsyncMock,
            return_value={},  # Without MOD_NOTIFICATION_CHANNEL
        ):
            await verification_cog._rebuild_pending_embeds_for_guild(mock_guild)

    async def test_skips_invalid_mod_channel(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that does nothing if mod channel is not valid."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id,
                url1="https://cdn.discordapp.com/test1.png",
                url2="https://cdn.discordapp.com/test2.png",
                guild_name="Test Guild",
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)
            await session.commit()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel = MagicMock(return_value=None)

        with patch.object(
            ConfigService,
            "get_all_config",
            new_callable=AsyncMock,
            return_value={ConfigKey.MOD_NOTIFICATION_CHANNEL: 888},
        ):
            await verification_cog._rebuild_pending_embeds_for_guild(mock_guild)

    async def test_handles_rebuild_error(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that continues if embed reconstruction fails."""
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id,
                url1="https://cdn.discordapp.com/test1.png",
                url2="https://cdn.discordapp.com/test2.png",
                guild_name="Test Guild",
            )
            await service.set_mod_message_id(request_id=request.id, message_id=789)
            await session.commit()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(side_effect=Exception("Discord API error"))
        mock_guild.get_channel = MagicMock(return_value=mock_channel)

        with patch.object(
            ConfigService,
            "get_all_config",
            new_callable=AsyncMock,
            return_value={ConfigKey.MOD_NOTIFICATION_CHANNEL: 888},
        ):
            await verification_cog._rebuild_pending_embeds_for_guild(mock_guild)


class TestOnConfigChangedModEmbed:
    """Tests for on_config_changed with moderation embed keys."""

    async def test_rebuilds_on_mod_embed_color_change(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that rebuilds embeds when color changes."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        with patch.object(
            verification_cog,
            "_rebuild_pending_embeds_for_guild",
            new_callable=AsyncMock,
        ) as mock_rebuild:
            await verification_cog.on_config_changed(mock_guild, [ConfigKey.MOD_EMBED_REGULAR])
            mock_rebuild.assert_called_once_with(mock_guild)

    async def test_rebuilds_on_mod_embed_icon_change(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that rebuilds embeds when icon changes."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        with patch.object(
            verification_cog,
            "_rebuild_pending_embeds_for_guild",
            new_callable=AsyncMock,
        ) as mock_rebuild:
            await verification_cog.on_config_changed(mock_guild, [ConfigKey.MOD_EMBED_ALLY])
            mock_rebuild.assert_called_once_with(mock_guild)

    async def test_rebuilds_on_accept_button_change(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that rebuilds embeds when button text changes."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        with patch.object(
            verification_cog,
            "_rebuild_pending_embeds_for_guild",
            new_callable=AsyncMock,
        ) as mock_rebuild:
            await verification_cog.on_config_changed(mock_guild, [ConfigKey.ACCEPT_BUTTON_TEXT])
            mock_rebuild.assert_called_once_with(mock_guild)

    async def test_no_rebuild_on_unrelated_key(self, verification_cog: VerificationCog) -> None:
        """Test that does not rebuild with unrelated keys."""
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"

        with patch.object(
            verification_cog,
            "_rebuild_pending_embeds_for_guild",
            new_callable=AsyncMock,
        ) as mock_rebuild:
            await verification_cog.on_config_changed(mock_guild, ["some_unrelated_key"])
            mock_rebuild.assert_not_called()


class TestScreenshotTimer:
    """Tests for the timer for screenshot timeout."""

    async def test_start_screenshot_timer_creates_task(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that start_screenshot_timer creates a task."""
        verification_cog.start_screenshot_timer(
            request_id=123,
            guild_id=456,
            user_id=789,
            timeout_minutes=5,
        )

        assert 123 in verification_cog._screenshot_timers
        task = verification_cog._screenshot_timers[123]
        assert not task.done()

        # Limpiar
        task.cancel()

    async def test_start_screenshot_timer_cancels_existing(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that start_screenshot_timer cancels existing timer."""
        import asyncio

        # Create first timer
        verification_cog.start_screenshot_timer(
            request_id=123,
            guild_id=456,
            user_id=789,
            timeout_minutes=5,
        )
        first_task = verification_cog._screenshot_timers[123]

        # Create second timer for the same request
        verification_cog.start_screenshot_timer(
            request_id=123,
            guild_id=456,
            user_id=789,
            timeout_minutes=10,
        )
        second_task = verification_cog._screenshot_timers[123]

        # Wait for the cancellation to process
        await asyncio.sleep(0)

        assert first_task.cancelled() or first_task.done()
        assert not second_task.done()

        # Limpiar
        second_task.cancel()

    async def test_cancel_screenshot_timer_returns_true(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that cancel_screenshot_timer returns True if it cancels."""
        verification_cog.start_screenshot_timer(
            request_id=123,
            guild_id=456,
            user_id=789,
            timeout_minutes=5,
        )

        result = verification_cog.cancel_screenshot_timer(123)

        assert result is True
        assert 123 not in verification_cog._screenshot_timers

    def test_cancel_screenshot_timer_returns_false_if_not_exists(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that cancel_screenshot_timer returns False if it does not exist."""
        result = verification_cog.cancel_screenshot_timer(999)

        assert result is False

    async def test_cog_unload_cancels_all_timers(self, verification_cog: VerificationCog) -> None:
        """Test that cog_unload cancels all timers."""
        import asyncio

        verification_cog.start_screenshot_timer(
            request_id=1,
            guild_id=100,
            user_id=200,
            timeout_minutes=5,
        )
        verification_cog.start_screenshot_timer(
            request_id=2,
            guild_id=100,
            user_id=201,
            timeout_minutes=5,
        )

        task1 = verification_cog._screenshot_timers[1]
        task2 = verification_cog._screenshot_timers[2]

        await verification_cog.cog_unload()

        # Wait for cancellations to process
        await asyncio.sleep(0)

        assert task1.cancelled() or task1.done()
        assert task2.cancelled() or task2.done()
        assert len(verification_cog._screenshot_timers) == 0


class TestAutoRejectByTimeout:
    """Tests for auto-reject due to screenshot timeout."""

    async def test_auto_reject_updates_status(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that auto-rejection changes the state to REJECTED."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        # Execute auto-rejection
        with patch.object(verification_cog, "bot") as mock_bot:
            mock_bot.database = test_database
            mock_bot.user = MagicMock()
            mock_bot.user.id = 999
            mock_bot.get_guild.return_value = None

            await verification_cog._auto_reject_by_timeout(
                request_id=request_id,
                guild_id=123,
                user_id=456,
            )

        # Verify state
        async with test_database.session() as session:
            service = VerificationService(session)
            updated_request = await service.get_by_public_id(public_id)
            assert updated_request is not None
            assert updated_request.status == VerificationStatus.REJECTED

    async def test_auto_reject_skips_if_not_pending_screenshots(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that does not reject if no longer waiting for screenshots."""
        # Create request and update it to PENDING_REVIEW
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await service.update_screenshots(
                request_id=request.id,
                url1="http://example.com/1.png",
                url2="http://example.com/2.png",
                guild_name="Test Guild",
            )
            await session.commit()
            public_id = request.public_id
            request_id = request.id

        # Execute auto-rejection
        with patch.object(verification_cog, "bot") as mock_bot:
            mock_bot.database = test_database
            mock_bot.user = MagicMock()
            mock_bot.user.id = 999

            await verification_cog._auto_reject_by_timeout(
                request_id=request_id,
                guild_id=123,
                user_id=456,
            )

        # Verify it stays in PENDING_REVIEW
        async with test_database.session() as session:
            service = VerificationService(session)
            updated_request = await service.get_by_public_id(public_id)
            assert updated_request is not None
            assert updated_request.status == VerificationStatus.PENDING_REVIEW

    async def test_auto_reject_clears_pending_dm(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that cleans _pending_dm_verifications."""
        # Create request
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        # Add a pending
        verification_cog._pending_dm_verifications[456] = (123, request_id)

        # Execute auto-rejection
        with patch.object(verification_cog, "bot") as mock_bot:
            mock_bot.database = test_database
            mock_bot.user = MagicMock()
            mock_bot.user.id = 999
            mock_bot.get_guild.return_value = None

            await verification_cog._auto_reject_by_timeout(
                request_id=request_id,
                guild_id=123,
                user_id=456,
            )

        assert 456 not in verification_cog._pending_dm_verifications

    async def test_auto_reject_request_not_found(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that does not fail if the request does not exist."""
        with patch.object(verification_cog, "bot") as mock_bot:
            mock_bot.database = test_database

            # Should not throw exception
            await verification_cog._auto_reject_by_timeout(
                request_id=99999,
                guild_id=123,
                user_id=456,
            )

    async def test_auto_reject_with_guild_updates_mod_message(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that updates moderation message when guild exists."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = None

        with (
            patch.object(verification_cog, "bot") as mock_bot,
            patch(
                "discord_bot.verification.cog.update_mod_message_status",
                new_callable=AsyncMock,
            ) as mock_update_status,
            patch(
                "discord_bot.verification.cog.update_tracker_message",
                new_callable=AsyncMock,
            ),
        ):
            mock_bot.database = test_database
            mock_bot.user = MagicMock()
            mock_bot.user.id = 999
            mock_bot.get_guild.return_value = mock_guild

            await verification_cog._auto_reject_by_timeout(
                request_id=request_id,
                guild_id=123,
                user_id=456,
            )

            mock_update_status.assert_called_once()

    async def test_auto_reject_notifies_member(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that notifies user via DM."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = mock_member

        with (
            patch.object(verification_cog, "bot") as mock_bot,
            patch(
                "discord_bot.verification.cog.update_mod_message_status",
                new_callable=AsyncMock,
            ),
            patch(
                "discord_bot.verification.cog.update_tracker_message",
                new_callable=AsyncMock,
            ),
        ):
            mock_bot.database = test_database
            mock_bot.user = MagicMock()
            mock_bot.user.id = 999
            mock_bot.get_guild.return_value = mock_guild

            await verification_cog._auto_reject_by_timeout(
                request_id=request_id,
                guild_id=123,
                user_id=456,
            )

            mock_member.send.assert_called_once()

    async def test_auto_reject_handles_forbidden_dm(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that handles Forbidden error when sending DM."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()
            request_id = request.id

        mock_member = MagicMock(spec=discord.Member)
        mock_member.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), ""))

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = mock_member

        with (
            patch.object(verification_cog, "bot") as mock_bot,
            patch(
                "discord_bot.verification.cog.update_mod_message_status",
                new_callable=AsyncMock,
            ),
            patch(
                "discord_bot.verification.cog.update_tracker_message",
                new_callable=AsyncMock,
            ),
        ):
            mock_bot.database = test_database
            mock_bot.user = MagicMock()
            mock_bot.user.id = 999
            mock_bot.get_guild.return_value = mock_guild

            # Should not throw exception
            await verification_cog._auto_reject_by_timeout(
                request_id=request_id,
                guild_id=123,
                user_id=456,
            )


class TestScreenshotTimerTask:
    """Tests for the task for the screenshot timer."""

    async def test_timer_task_calls_auto_reject_on_timeout(
        self, verification_cog: VerificationCog
    ) -> None:
        """Test that timer calls auto_reject when it expires."""
        with patch.object(
            verification_cog,
            "_auto_reject_by_timeout",
            new_callable=AsyncMock,
        ) as mock_reject:
            # Run with very short timeout
            await verification_cog._screenshot_timer_task(
                request_id=123,
                guild_id=456,
                user_id=789,
                timeout_minutes=0,  # 0 minutes = immediate
            )

            mock_reject.assert_called_once_with(
                request_id=123,
                guild_id=456,
                user_id=789,
            )

    async def test_timer_task_handles_exception(self, verification_cog: VerificationCog) -> None:
        """Test that timer handles exceptions correctly."""
        verification_cog._screenshot_timers[123] = MagicMock()

        with patch.object(
            verification_cog,
            "_auto_reject_by_timeout",
            new_callable=AsyncMock,
            side_effect=Exception("Test error"),
        ):
            # Should not throw exception
            await verification_cog._screenshot_timer_task(
                request_id=123,
                guild_id=456,
                user_id=789,
                timeout_minutes=0,
            )

        # Should clean up timer from dict
        assert 123 not in verification_cog._screenshot_timers

    async def test_timer_task_cleans_up_on_cancel(self, verification_cog: VerificationCog) -> None:
        """Test that timer cleans up when cancelled."""
        import asyncio

        verification_cog._screenshot_timers[123] = MagicMock()

        task = asyncio.create_task(
            verification_cog._screenshot_timer_task(
                request_id=123,
                guild_id=456,
                user_id=789,
                timeout_minutes=999,  # Very long
            )
        )

        await asyncio.sleep(0)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should clean up timer from dict
        assert 123 not in verification_cog._screenshot_timers


class TestRestorePendingVerificationsWithTimer:
    """Tests for restoration of verifications with timer."""

    async def test_restore_starts_timer_if_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that restores timers if configured."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()

        verification_cog._pending_dm_verifications.clear()
        verification_cog._screenshot_timers.clear()

        # Mock config with timeout
        with patch.object(
            ConfigService,
            "get_all_config",
            new_callable=AsyncMock,
            return_value={ConfigKey.SCREENSHOT_TIMEOUT_MINUTES: 30},
        ):
            await verification_cog._restore_pending_verifications()

        # Verify that the timer was created
        assert 456 in verification_cog._pending_dm_verifications
        # The timer should exist (or have executed if time already passed)

        # Clean up timers
        for task in verification_cog._screenshot_timers.values():
            task.cancel()

    async def test_restore_no_timer_if_not_configured(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that does not create timer if timeout is 0."""
        # Create pending request
        async with test_database.session() as session:
            service = VerificationService(session)
            await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            await session.commit()

        verification_cog._pending_dm_verifications.clear()
        verification_cog._screenshot_timers.clear()

        # Mock config without timeout
        with patch.object(
            ConfigService,
            "get_all_config",
            new_callable=AsyncMock,
            return_value={ConfigKey.SCREENSHOT_TIMEOUT_MINUTES: 0},
        ):
            await verification_cog._restore_pending_verifications()

        # Verify that no timer was created
        assert len(verification_cog._screenshot_timers) == 0

    async def test_restore_auto_rejects_if_time_expired(
        self, verification_cog: VerificationCog, test_database: DatabaseService
    ) -> None:
        """Test that auto-rejects if time already expired."""
        # Create pending request with old date
        async with test_database.session() as session:
            service = VerificationService(session)
            request = await service.create_request(
                guild_id=123,
                user_id=456,
                username="TestUser",
                guild_name="Test Guild",
                verification_type=VerificationType.REGULAR,
            )
            # Modify created_at to be 1 hour ago
            from datetime import timedelta

            request.created_at = datetime.now(UTC) - timedelta(hours=1)
            await session.commit()
            request_id = request.id

        verification_cog._pending_dm_verifications.clear()
        verification_cog._screenshot_timers.clear()

        # Mock config with 5 minute timeout (already expired)
        with (
            patch.object(
                ConfigService,
                "get_all_config",
                new_callable=AsyncMock,
                return_value={ConfigKey.SCREENSHOT_TIMEOUT_MINUTES: 5},
            ),
            patch.object(
                verification_cog,
                "_auto_reject_by_timeout",
                new_callable=AsyncMock,
            ) as mock_reject,
        ):
            await verification_cog._restore_pending_verifications()

            # Wait for the created task to execute
            import asyncio

            await asyncio.sleep(0.1)

            # Verify that auto_reject was called
            mock_reject.assert_called_once_with(
                request_id=request_id,
                guild_id=123,
                user_id=456,
            )
