"""Tests for DerivedRolesCog."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_bot.common.services.config_schema_service import get_config_schema_service
from discord_bot.common.services.config_service import ConfigService
from discord_bot.common.services.database import DatabaseService
from discord_bot.derived_roles.cog import DerivedRolesCog
from discord_bot.derived_roles.config import COG_NAME, DERIVED_ROLES_CONFIG_SCHEMA, ConfigKey

GUILD_ID = 123456789
COLLIE = 100
WARDEN = 200
LOGI_COLLIE = 101


async def enable_cog_for_guild(db: DatabaseService, guild_id: int) -> None:
    """Enable the derived roles cog for a guild."""
    async with db.session() as session:
        config_service = ConfigService(session)
        await config_service.set_cog_enabled(guild_id=guild_id, cog_name=COG_NAME, enabled=True)
        await session.commit()


async def set_rules(db: DatabaseService, guild_id: int, rules: list[dict[str, Any]]) -> None:
    """Set the rules config value for a guild."""
    async with db.session() as session:
        config_service = ConfigService(session)
        success, error = await config_service.set_value(
            guild_id=guild_id, cog_name=COG_NAME, key=ConfigKey.RULES, value=rules
        )
        assert success, error
        await session.commit()


@pytest.fixture
def mock_discord_bot(test_database: DatabaseService) -> Any:
    """Create mock of the bot with database."""
    bot: Any = MagicMock()
    bot.database = test_database
    bot.guilds = []
    bot.get_guild = MagicMock(return_value=None)
    bot.wait_until_ready = AsyncMock()
    return bot


@pytest.fixture
def derived_roles_cog(mock_discord_bot: Any) -> DerivedRolesCog:
    """Create cog instance for tests."""
    schema_service = get_config_schema_service()
    if not schema_service.get_schema(COG_NAME):
        schema_service.register_schema(DERIVED_ROLES_CONFIG_SCHEMA)
    return DerivedRolesCog(mock_discord_bot)


def make_role(role_id: int, name: str) -> MagicMock:
    """Create a mock role."""
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.name = name
    role.mention = f"<@&{role_id}>"
    return role


@pytest.fixture
def mock_guild() -> MagicMock:
    """Create mock of a guild with the test roles."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = GUILD_ID
    guild.name = "Test Guild"
    roles = {
        COLLIE: make_role(COLLIE, "Collie"),
        WARDEN: make_role(WARDEN, "Warden"),
        LOGI_COLLIE: make_role(LOGI_COLLIE, "Logi Collie"),
    }
    guild.get_role = MagicMock(side_effect=lambda rid: roles.get(rid))
    guild.get_channel = MagicMock(return_value=None)
    guild.members = []
    return guild


def make_member(guild: MagicMock, role_ids: list[int], member_id: int = 555) -> MagicMock:
    """Create a mock member with the given roles."""
    member = MagicMock(spec=discord.Member)
    member.id = member_id
    member.bot = False
    member.display_name = "TestUser"
    member.mention = f"<@{member_id}>"
    member.guild = guild
    member.roles = [guild.get_role(rid) for rid in role_ids]
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    return member


IMPLIES_RULE = {"trigger_role": COLLIE, "rule_type": "implies", "target_role": LOGI_COLLIE}
REQUIRES_RULE = {"trigger_role": COLLIE, "rule_type": "requires", "target_role": LOGI_COLLIE}
INCOMPATIBLE_RULE = {"trigger_role": WARDEN, "rule_type": "incompatible", "target_role": COLLIE}


class TestOnMemberUpdate:
    """Tests for the member update event handler."""

    async def test_ignores_unchanged_roles(
        self, derived_roles_cog: DerivedRolesCog, mock_guild: MagicMock
    ) -> None:
        """No processing when roles did not change."""
        member = make_member(mock_guild, [COLLIE])

        await derived_roles_cog.on_member_update(member, member)

        member.add_roles.assert_not_called()

    async def test_ignores_bots(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Bot members are never processed."""
        await enable_cog_for_guild(test_database, GUILD_ID)
        await set_rules(test_database, GUILD_ID, [IMPLIES_RULE])

        before = make_member(mock_guild, [])
        after = make_member(mock_guild, [COLLIE])
        after.bot = True

        await derived_roles_cog.on_member_update(before, after)

        after.add_roles.assert_not_called()

    async def test_ignores_disabled_cog(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Nothing happens when the cog is disabled for the guild."""
        await set_rules(test_database, GUILD_ID, [IMPLIES_RULE])

        before = make_member(mock_guild, [])
        after = make_member(mock_guild, [COLLIE])

        await derived_roles_cog.on_member_update(before, after)

        after.add_roles.assert_not_called()

    async def test_implies_adds_derived_role(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Gaining the trigger role adds the derived role."""
        await enable_cog_for_guild(test_database, GUILD_ID)
        await set_rules(test_database, GUILD_ID, [IMPLIES_RULE])

        before = make_member(mock_guild, [])
        after = make_member(mock_guild, [COLLIE])

        await derived_roles_cog.on_member_update(before, after)

        after.add_roles.assert_called_once()
        added = after.add_roles.call_args.args
        assert [r.id for r in added] == [LOGI_COLLIE]
        after.remove_roles.assert_not_called()

    async def test_requires_removes_orphan_role(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Losing the trigger role removes dependent roles."""
        await enable_cog_for_guild(test_database, GUILD_ID)
        await set_rules(test_database, GUILD_ID, [REQUIRES_RULE])

        before = make_member(mock_guild, [COLLIE, LOGI_COLLIE])
        after = make_member(mock_guild, [LOGI_COLLIE])

        await derived_roles_cog.on_member_update(before, after)

        after.remove_roles.assert_called_once()
        removed = after.remove_roles.call_args.args
        assert [r.id for r in removed] == [LOGI_COLLIE]
        after.add_roles.assert_not_called()

    async def test_incompatible_removes_conflicting_role(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Gaining a role removes roles incompatible with it."""
        await enable_cog_for_guild(test_database, GUILD_ID)
        await set_rules(test_database, GUILD_ID, [INCOMPATIBLE_RULE])

        before = make_member(mock_guild, [COLLIE])
        after = make_member(mock_guild, [COLLIE, WARDEN])

        await derived_roles_cog.on_member_update(before, after)

        after.remove_roles.assert_called_once()
        removed = after.remove_roles.call_args.args
        assert [r.id for r in removed] == [COLLIE]

    async def test_noop_when_invariants_satisfied(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """No API calls when the member already satisfies all rules."""
        await enable_cog_for_guild(test_database, GUILD_ID)
        await set_rules(test_database, GUILD_ID, [IMPLIES_RULE])

        before = make_member(mock_guild, [COLLIE])
        after = make_member(mock_guild, [COLLIE, LOGI_COLLIE])

        await derived_roles_cog.on_member_update(before, after)

        after.add_roles.assert_not_called()
        after.remove_roles.assert_not_called()


class TestErrorState:
    """Tests for permission error handling and audit notifications."""

    async def _setup(self, test_database: DatabaseService, mock_guild: MagicMock) -> MagicMock:
        """Enable cog, set rules and an audit channel; return the channel mock."""
        await enable_cog_for_guild(test_database, GUILD_ID)
        await set_rules(test_database, GUILD_ID, [IMPLIES_RULE])
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=GUILD_ID, cog_name=COG_NAME, key=ConfigKey.AUDIT_CHANNEL, value=999
            )
            await session.commit()

        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        mock_guild.get_channel = MagicMock(return_value=channel)
        return channel

    async def test_forbidden_notifies_once(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """A permission failure notifies once, not on every retry."""
        channel = await self._setup(test_database, mock_guild)

        config = await derived_roles_cog._get_config(GUILD_ID)
        member = make_member(mock_guild, [COLLIE])
        member.add_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perms"))

        assert not await derived_roles_cog._apply_rules(member=member, config=config)
        assert not await derived_roles_cog._apply_rules(member=member, config=config)

        assert channel.send.call_count == 1
        assert derived_roles_cog._error_state[GUILD_ID] is True

    async def test_recovery_notifies_and_clears_state(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """A successful application after an error sends a recovery message."""
        channel = await self._setup(test_database, mock_guild)

        config = await derived_roles_cog._get_config(GUILD_ID)
        derived_roles_cog._error_state[GUILD_ID] = True

        member = make_member(mock_guild, [COLLIE])
        assert await derived_roles_cog._apply_rules(member=member, config=config)

        assert derived_roles_cog._error_state[GUILD_ID] is False
        recovery_calls = [
            call for call in channel.send.call_args_list if "recovered" in call.args[0]
        ]
        assert len(recovery_calls) == 1


class TestMemberLocks:
    """Tests for the per-member lock pool."""

    async def test_lock_evicted_after_apply(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Test that the per-member lock entry is removed after applying rules."""
        await enable_cog_for_guild(test_database, GUILD_ID)
        await set_rules(test_database, GUILD_ID, [IMPLIES_RULE])

        config = await derived_roles_cog._get_config(GUILD_ID)
        member = make_member(mock_guild, [COLLIE])

        assert await derived_roles_cog._apply_rules(member=member, config=config)

        assert len(derived_roles_cog._member_locks) == 0


class TestSendAudit:
    """Tests for _send_audit template tolerance."""

    def _make_channel(self, mock_guild: MagicMock) -> MagicMock:
        """Make the guild return an audit channel mock."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        mock_guild.get_channel = MagicMock(return_value=channel)
        return channel

    async def test_tolerates_unknown_placeholder(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """A template with an unknown placeholder still sends the message."""
        channel = self._make_channel(mock_guild)
        config = {
            ConfigKey.AUDIT_CHANNEL: 999,
            ConfigKey.AUDIT_ERROR_MSG: "Error for {user_name} {oops}",
        }

        await derived_roles_cog._send_audit(
            guild=mock_guild,
            config=config,
            template_key=ConfigKey.AUDIT_ERROR_MSG,
            user_name="TestUser",
        )

        channel.send.assert_called_once()
        sent = channel.send.call_args[0][0]
        assert "TestUser" in sent
        assert "{oops}" in sent

    async def test_tolerates_stray_brace(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
    ) -> None:
        """A template with a stray brace still sends the message."""
        channel = self._make_channel(mock_guild)
        config = {
            ConfigKey.AUDIT_CHANNEL: 999,
            ConfigKey.AUDIT_ERROR_MSG: "Error for {user_name} :{",
        }

        await derived_roles_cog._send_audit(
            guild=mock_guild,
            config=config,
            template_key=ConfigKey.AUDIT_ERROR_MSG,
            user_name="TestUser",
        )

        channel.send.assert_called_once()
        sent = channel.send.call_args[0][0]
        assert sent == "Error for TestUser :{"


class TestAppliedAudit:
    """Tests for the applied-rules audit message and its trigger placeholder."""

    async def _setup(
        self,
        test_database: DatabaseService,
        mock_guild: MagicMock,
        rules: list[dict[str, Any]],
    ) -> MagicMock:
        """Enable cog, rules, audit channel and applied notifications."""
        await enable_cog_for_guild(test_database, GUILD_ID)
        await set_rules(test_database, GUILD_ID, rules)
        async with test_database.session() as session:
            config_service = ConfigService(session)
            await config_service.set_value(
                guild_id=GUILD_ID, cog_name=COG_NAME, key=ConfigKey.AUDIT_CHANNEL, value=999
            )
            await config_service.set_value(
                guild_id=GUILD_ID, cog_name=COG_NAME, key=ConfigKey.AUDIT_APPLIED, value=True
            )
            await session.commit()

        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        mock_guild.get_channel = MagicMock(return_value=channel)
        return channel

    async def test_applied_message_includes_gained_trigger(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """The audit message shows which gained role triggered the changes."""
        channel = await self._setup(test_database, mock_guild, [IMPLIES_RULE])

        before = make_member(mock_guild, [])
        after = make_member(mock_guild, [COLLIE])

        await derived_roles_cog.on_member_update(before, after)

        channel.send.assert_called_once()
        message = channel.send.call_args.args[0]
        assert f"+<@&{COLLIE}>" in message
        assert f"<@&{LOGI_COLLIE}>" in message

    async def test_applied_message_includes_lost_trigger(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """The audit message shows which lost role triggered the removals."""
        channel = await self._setup(test_database, mock_guild, [REQUIRES_RULE])

        before = make_member(mock_guild, [COLLIE, LOGI_COLLIE])
        after = make_member(mock_guild, [LOGI_COLLIE])

        await derived_roles_cog.on_member_update(before, after)

        channel.send.assert_called_once()
        message = channel.send.call_args.args[0]
        assert f"-<@&{COLLIE}>" in message
        assert f"<@&{LOGI_COLLIE}>" in message

    async def test_sync_applied_message_has_no_trigger(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Sweep-driven corrections have no triggering event to report."""
        channel = await self._setup(test_database, mock_guild, [IMPLIES_RULE])

        config = await derived_roles_cog._get_config(GUILD_ID)
        member = make_member(mock_guild, [COLLIE])

        assert await derived_roles_cog._apply_rules(member=member, config=config)

        channel.send.assert_called_once()
        message = channel.send.call_args.args[0]
        assert f"+<@&{COLLIE}>" not in message
        assert "—" in message

    async def test_audit_message_never_pings(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Audit messages are sent with all mentions suppressed to avoid pings."""
        channel = await self._setup(test_database, mock_guild, [IMPLIES_RULE])

        before = make_member(mock_guild, [])
        after = make_member(mock_guild, [COLLIE])

        await derived_roles_cog.on_member_update(before, after)

        channel.send.assert_called_once()
        allowed = channel.send.call_args.kwargs["allowed_mentions"]
        assert allowed.roles is False
        assert allowed.users is False
        assert allowed.everyone is False

    async def test_log_states_trigger_action(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The log line states whether the trigger role was gained or lost."""
        await self._setup(test_database, mock_guild, [REQUIRES_RULE])

        before = make_member(mock_guild, [COLLIE, LOGI_COLLIE])
        after = make_member(mock_guild, [LOGI_COLLIE])

        with caplog.at_level(logging.INFO):
            await derived_roles_cog.on_member_update(before, after)

        assert "trigger gained [], lost ['Collie']" in caplog.text
        assert "removed ['Logi Collie']" in caplog.text


class TestReconciliation:
    """Tests for the periodic reconciliation sweep."""

    async def test_sync_guild_corrects_members(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """The sweep applies rules to all non-bot members."""
        await enable_cog_for_guild(test_database, GUILD_ID)
        await set_rules(test_database, GUILD_ID, [IMPLIES_RULE])

        needs_fix = make_member(mock_guild, [COLLIE], member_id=1)
        already_ok = make_member(mock_guild, [COLLIE, LOGI_COLLIE], member_id=2)
        bot_member = make_member(mock_guild, [COLLIE], member_id=3)
        bot_member.bot = True
        mock_guild.members = [needs_fix, already_ok, bot_member]

        config = await derived_roles_cog._get_config(GUILD_ID)
        await derived_roles_cog._sync_guild(guild=mock_guild, config=config)

        needs_fix.add_roles.assert_called_once()
        already_ok.add_roles.assert_not_called()
        bot_member.add_roles.assert_not_called()

    async def test_sync_respects_empty_rules(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """The sweep does nothing when no rules are configured."""
        await enable_cog_for_guild(test_database, GUILD_ID)

        member = make_member(mock_guild, [COLLIE])
        mock_guild.members = [member]

        config = await derived_roles_cog._get_config(GUILD_ID)
        await derived_roles_cog._sync_guild(guild=mock_guild, config=config)

        member.add_roles.assert_not_called()


class TestConfigValidation:
    """Tests for rule validation through the config service."""

    async def test_invalid_rules_rejected_on_save(
        self,
        derived_roles_cog: DerivedRolesCog,
        test_database: DatabaseService,
    ) -> None:
        """Contradictory rules are rejected by the config service."""
        async with test_database.session() as session:
            config_service = ConfigService(session)
            success, error = await config_service.set_value(
                guild_id=GUILD_ID,
                cog_name=COG_NAME,
                key=ConfigKey.RULES,
                value=[
                    {"trigger_role": COLLIE, "rule_type": "implies", "target_role": COLLIE},
                ],
            )

        assert not success
        assert error is not None
        assert f"<@&{COLLIE}>" in error

    async def test_valid_rules_accepted_on_save(
        self,
        derived_roles_cog: DerivedRolesCog,
        test_database: DatabaseService,
    ) -> None:
        """A valid rule set saves without error."""
        async with test_database.session() as session:
            config_service = ConfigService(session)
            success, error = await config_service.set_value(
                guild_id=GUILD_ID,
                cog_name=COG_NAME,
                key=ConfigKey.RULES,
                value=[IMPLIES_RULE, REQUIRES_RULE, INCOMPATIBLE_RULE],
            )

        assert success, error


class TestOnGuildRemove:
    """Tests for on_guild_remove cleanup."""

    async def test_clears_guild_state(
        self, derived_roles_cog: DerivedRolesCog, mock_guild: MagicMock
    ) -> None:
        """Test that cached per-guild state is dropped on removal."""
        derived_roles_cog._schedule.mark_run(
            guild_id=mock_guild.id, now=datetime.now(UTC), interval_minutes=30
        )
        derived_roles_cog._error_state[mock_guild.id] = True

        await derived_roles_cog.on_guild_remove(mock_guild)

        assert derived_roles_cog._schedule.next_due(mock_guild.id) is None
        assert mock_guild.id not in derived_roles_cog._error_state


class TestRunSyncSchedule:
    """Tests for the per-guild schedule of the reconciliation loop."""

    async def test_syncs_when_due_and_skips_idle_ticks(
        self, derived_roles_cog: DerivedRolesCog, mock_guild: MagicMock
    ) -> None:
        """The first tick syncs; ticks before the interval elapses read no config."""
        derived_roles_cog.bot.guilds = [mock_guild]
        config = {ConfigKey.SYNC_INTERVAL: 30, ConfigKey.RULES: []}

        with (
            patch.object(
                derived_roles_cog, "_is_cog_enabled", new_callable=AsyncMock, return_value=True
            ) as mock_enabled,
            patch.object(
                derived_roles_cog, "_get_config", new_callable=AsyncMock, return_value=config
            ),
            patch.object(derived_roles_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync,
        ):
            await derived_roles_cog._run_sync()
            await derived_roles_cog._run_sync()

        mock_sync.assert_awaited_once_with(guild=mock_guild, config=config)
        mock_enabled.assert_awaited_once()

    async def test_disabled_guild_is_deferred(
        self, derived_roles_cog: DerivedRolesCog, mock_guild: MagicMock
    ) -> None:
        """A disabled guild is not re-read on every tick."""
        derived_roles_cog.bot.guilds = [mock_guild]

        with (
            patch.object(
                derived_roles_cog, "_is_cog_enabled", new_callable=AsyncMock, return_value=False
            ) as mock_enabled,
            patch.object(derived_roles_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync,
        ):
            await derived_roles_cog._run_sync()
            await derived_roles_cog._run_sync()

        mock_sync.assert_not_awaited()
        mock_enabled.assert_awaited_once()

    async def test_zero_interval_is_deferred(
        self, derived_roles_cog: DerivedRolesCog, mock_guild: MagicMock
    ) -> None:
        """A guild with sync interval 0 never syncs and is not re-read every tick."""
        derived_roles_cog.bot.guilds = [mock_guild]

        with (
            patch.object(
                derived_roles_cog, "_is_cog_enabled", new_callable=AsyncMock, return_value=True
            ) as mock_enabled,
            patch.object(
                derived_roles_cog,
                "_get_config",
                new_callable=AsyncMock,
                return_value={ConfigKey.SYNC_INTERVAL: 0},
            ),
            patch.object(derived_roles_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync,
        ):
            await derived_roles_cog._run_sync()
            await derived_roles_cog._run_sync()

        mock_sync.assert_not_awaited()
        mock_enabled.assert_awaited_once()

    async def test_force_all_ignores_schedule(
        self, derived_roles_cog: DerivedRolesCog, mock_guild: MagicMock
    ) -> None:
        """force_all syncs even when the guild is not due yet."""
        derived_roles_cog.bot.guilds = [mock_guild]
        derived_roles_cog._schedule.mark_run(
            guild_id=mock_guild.id, now=datetime.now(UTC), interval_minutes=60
        )
        config = {ConfigKey.SYNC_INTERVAL: 60}

        with (
            patch.object(
                derived_roles_cog, "_is_cog_enabled", new_callable=AsyncMock, return_value=True
            ),
            patch.object(
                derived_roles_cog, "_get_config", new_callable=AsyncMock, return_value=config
            ),
            patch.object(derived_roles_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync,
        ):
            await derived_roles_cog._run_sync(force_all=True)

        mock_sync.assert_awaited_once_with(guild=mock_guild, config=config)

    async def test_config_callbacks_reset_schedule(
        self, derived_roles_cog: DerivedRolesCog, mock_guild: MagicMock
    ) -> None:
        """on_config_changed and on_cog_toggled make the guild due on the next tick."""
        derived_roles_cog.bot.guilds = [mock_guild]
        config = {ConfigKey.SYNC_INTERVAL: 60, ConfigKey.RULES: []}

        with (
            patch.object(
                derived_roles_cog, "_is_cog_enabled", new_callable=AsyncMock, return_value=True
            ) as mock_enabled,
            patch.object(
                derived_roles_cog, "_get_config", new_callable=AsyncMock, return_value=config
            ),
            patch.object(derived_roles_cog, "_sync_guild", new_callable=AsyncMock),
        ):
            await derived_roles_cog._run_sync()
            await derived_roles_cog.on_config_changed(guild=mock_guild, keys=["sync_interval"])
            await derived_roles_cog._run_sync()
            await derived_roles_cog.on_cog_toggled(guild=mock_guild, enabled=False)
            await derived_roles_cog._run_sync()

        assert mock_enabled.await_count == 3


class TestSyncRunsInBackground:
    """Dashboard callbacks must not block on a full-guild reconciliation."""

    async def test_on_config_changed_returns_before_sync_finishes(
        self, derived_roles_cog: DerivedRolesCog, mock_guild: MagicMock
    ) -> None:
        """The callback returns while the reconciliation is still running."""
        release = asyncio.Event()
        started = asyncio.Event()

        async def slow_sync(*, guild: discord.Guild, config: dict[str, Any]) -> None:
            started.set()
            await release.wait()

        with (
            patch.object(derived_roles_cog, "_get_config", new_callable=AsyncMock, return_value={}),
            patch.object(derived_roles_cog, "_sync_guild", side_effect=slow_sync),
        ):
            await asyncio.wait_for(
                derived_roles_cog.on_config_changed(mock_guild, [ConfigKey.RULES]), timeout=1
            )
            release.set()
            await derived_roles_cog._background.drain()

        assert started.is_set()

    async def test_sync_guild_skips_when_already_running(
        self, derived_roles_cog: DerivedRolesCog, mock_guild: MagicMock
    ) -> None:
        """A second reconciliation for the same guild is skipped while the first runs."""
        release = asyncio.Event()
        member = make_member(mock_guild, [COLLIE])
        mock_guild.members = [member]
        config = {ConfigKey.RULES: [IMPLIES_RULE]}
        calls = 0

        async def slow_apply(*, member: discord.Member, config: dict[str, Any]) -> bool:
            nonlocal calls
            calls += 1
            await release.wait()
            return False

        with patch.object(derived_roles_cog, "_apply_rules", side_effect=slow_apply):
            first = asyncio.create_task(
                derived_roles_cog._sync_guild(guild=mock_guild, config=config)
            )
            await asyncio.sleep(0)
            await derived_roles_cog._sync_guild(guild=mock_guild, config=config)
            release.set()
            await first

        assert calls == 1

    async def test_cog_unload_cancels_background_syncs(
        self, derived_roles_cog: DerivedRolesCog, mock_guild: MagicMock
    ) -> None:
        """Unloading the cog cancels reconciliations that are still running."""

        async def forever(*, guild: discord.Guild, config: dict[str, Any]) -> None:
            await asyncio.Event().wait()

        with (
            patch.object(derived_roles_cog, "_get_config", new_callable=AsyncMock, return_value={}),
            patch.object(derived_roles_cog, "_sync_guild", side_effect=forever),
        ):
            await derived_roles_cog.on_cog_toggled(mock_guild, enabled=True)
            await asyncio.sleep(0)
            assert len(derived_roles_cog._background) == 1
            await derived_roles_cog.cog_unload()
            await derived_roles_cog._background.drain()

        assert len(derived_roles_cog._background) == 0


class TestConfigCaching:
    """Tests for the per-guild config cache on hot paths."""

    async def test_member_updates_share_one_config_load(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Repeated role changes in a guild do not open a DB session each time."""
        await enable_cog_for_guild(test_database, GUILD_ID)
        await set_rules(test_database, GUILD_ID, [IMPLIES_RULE])
        before = make_member(mock_guild, [])
        first = make_member(mock_guild, [COLLIE], member_id=1)
        second = make_member(mock_guild, [COLLIE], member_id=2)

        with patch.object(test_database, "session", wraps=test_database.session) as session_spy:
            await derived_roles_cog.on_member_update(before, first)
            await derived_roles_cog.on_member_update(before, second)

        assert session_spy.call_count == 1
        first.add_roles.assert_called_once()
        second.add_roles.assert_called_once()

    async def test_on_config_changed_invalidates_cache(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Rule changes from the dashboard are visible immediately, not after the TTL."""
        assert (await derived_roles_cog._get_config(GUILD_ID)).get(ConfigKey.RULES) in (None, [])

        await set_rules(test_database, GUILD_ID, [IMPLIES_RULE])
        with patch.object(derived_roles_cog, "_sync_guild", new_callable=AsyncMock) as mock_sync:
            await derived_roles_cog.on_config_changed(mock_guild, [ConfigKey.RULES])
            await derived_roles_cog._background.drain()

        mock_sync.assert_awaited_once()
        assert mock_sync.await_args.kwargs["config"][ConfigKey.RULES] == [IMPLIES_RULE]
        assert (await derived_roles_cog._get_config(GUILD_ID))[ConfigKey.RULES] == [IMPLIES_RULE]

    async def test_on_cog_toggled_invalidates_cache(
        self,
        derived_roles_cog: DerivedRolesCog,
        mock_guild: MagicMock,
        test_database: DatabaseService,
    ) -> None:
        """Enabling the cog from the dashboard is visible immediately."""
        assert await derived_roles_cog._is_cog_enabled(GUILD_ID) is False

        await enable_cog_for_guild(test_database, GUILD_ID)
        with patch.object(derived_roles_cog, "_sync_guild", new_callable=AsyncMock):
            await derived_roles_cog.on_cog_toggled(mock_guild, enabled=True)
            await derived_roles_cog._background.drain()

        assert await derived_roles_cog._is_cog_enabled(GUILD_ID) is True

    async def test_on_guild_remove_drops_cache(
        self, derived_roles_cog: DerivedRolesCog, mock_guild: MagicMock
    ) -> None:
        """Leaving a guild drops its cached configuration."""
        await derived_roles_cog._get_config(GUILD_ID)
        assert len(derived_roles_cog._config_cache) == 1

        await derived_roles_cog.on_guild_remove(mock_guild)

        assert len(derived_roles_cog._config_cache) == 0
