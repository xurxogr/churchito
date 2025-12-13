"""Tests for Guild model."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.models.guild import Guild


async def test_guild_creation(test_session: AsyncSession) -> None:
    """Test creating a guild.

    Args:
        test_session: Test database session fixture
    """
    guild = Guild(id=123456789, name="Test Guild", prefix="!")

    test_session.add(guild)
    await test_session.commit()

    # Query back
    result = await test_session.execute(select(Guild).where(Guild.id == 123456789))
    fetched_guild = result.scalar_one()

    assert fetched_guild.id == 123456789
    assert fetched_guild.name == "Test Guild"
    assert fetched_guild.prefix == "!"
    assert fetched_guild.created_at is not None
    assert fetched_guild.updated_at is not None


async def test_guild_default_prefix(test_session: AsyncSession) -> None:
    """Test guild default prefix.

    Args:
        test_session: Test database session fixture
    """
    guild = Guild(id=987654321, name="Test Guild 2")

    test_session.add(guild)
    await test_session.commit()

    result = await test_session.execute(select(Guild).where(Guild.id == 987654321))
    fetched_guild = result.scalar_one()

    assert fetched_guild.prefix == "!"


async def test_guild_repr(test_session: AsyncSession) -> None:
    """Test guild string representation.

    Args:
        test_session: Test database session fixture
    """
    guild = Guild(id=111222333, name="Test Guild 3", prefix="?")

    assert repr(guild) == "<Guild(id=111222333, name='Test Guild 3')>"
