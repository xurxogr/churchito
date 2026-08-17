"""Tests for discord_bot/purge/results.py."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select

from discord_bot.common.services.database import DatabaseService
from discord_bot.purge.enums import PurgeType
from discord_bot.purge.models import PurgeUserResult
from discord_bot.purge.results import PurgeResultBuffer, UserResultSink
from discord_bot.purge.service import PurgeService


async def _create_purge(db: DatabaseService) -> int:
    async with db.session() as session:
        record = await PurgeService(session).create_purge(
            guild_id=1,
            purge_type=PurgeType.WAR_END,
            initiated_by=2,
            config_snapshot={},
            scheduled_for=datetime.now(UTC) + timedelta(days=1),
        )
        await session.commit()
        return record.id


async def _stored_results(db: DatabaseService, purge_id: int) -> list[PurgeUserResult]:
    async with db.session() as session:
        result = await session.execute(
            select(PurgeUserResult)
            .where(PurgeUserResult.purge_id == purge_id)
            .order_by(PurgeUserResult.user_id)
        )
        return list(result.scalars().all())


async def test_purge_service_satisfies_sink_protocol(test_database: DatabaseService) -> None:
    """The phase functions can keep receiving a PurgeService where a sink is expected."""
    async with test_database.session() as session:
        sink: UserResultSink = PurgeService(session)
        assert hasattr(sink, "add_user_result")


async def test_results_are_persisted_on_flush(test_database: DatabaseService) -> None:
    """Buffered results reach the database with the fields they were added with."""
    purge_id = await _create_purge(test_database)
    buffer = PurgeResultBuffer(database=test_database, purge_id=purge_id, batch_size=100)

    await buffer.add_user_result(
        purge_id=purge_id,
        user_id=10,
        action_type="cleaned",
        roles_before=[1, 2],
        roles_after=[],
    )
    await buffer.add_user_result(
        purge_id=purge_id,
        user_id=20,
        action_type="promoted",
        roles_before=[1],
        roles_after=[1, 3],
        in_affected_group=True,
    )
    assert await _stored_results(test_database, purge_id) == []

    await buffer.flush()

    stored = await _stored_results(test_database, purge_id)
    assert [(r.user_id, r.action_type) for r in stored] == [(10, "cleaned"), (20, "promoted")]
    assert stored[0].roles_before == [1, 2]
    assert stored[0].in_affected_group is None
    assert stored[1].roles_after == [1, 3]
    assert stored[1].in_affected_group is True


async def test_full_batch_is_written_automatically(test_database: DatabaseService) -> None:
    """Reaching batch_size writes without waiting for an explicit flush."""
    purge_id = await _create_purge(test_database)
    buffer = PurgeResultBuffer(database=test_database, purge_id=purge_id, batch_size=2)

    with patch.object(test_database, "session", wraps=test_database.session) as session_spy:
        await buffer.add_user_result(
            purge_id=purge_id, user_id=1, action_type="cleaned", roles_before=[], roles_after=[]
        )
        assert session_spy.call_count == 0
        await buffer.add_user_result(
            purge_id=purge_id, user_id=2, action_type="cleaned", roles_before=[], roles_after=[]
        )
        assert session_spy.call_count == 1

    assert len(await _stored_results(test_database, purge_id)) == 2
    assert len(buffer) == 0


async def test_flush_with_nothing_pending_opens_no_session(test_database: DatabaseService) -> None:
    """An empty flush is free."""
    buffer = PurgeResultBuffer(database=test_database, purge_id=1)

    with patch.object(test_database, "session", wraps=test_database.session) as session_spy:
        await buffer.flush()

    assert session_spy.call_count == 0
