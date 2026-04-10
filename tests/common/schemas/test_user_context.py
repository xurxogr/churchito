"""Tests for the UserContext model."""

from discord_bot.common.schemas import UserContext


def test_user_context_creation() -> None:
    """Test creating UserContext."""
    context = UserContext(
        user_id=123456789,
        guild_id=987654321,
        role_ids=[111, 222, 333],
        username="TestUser",
    )

    assert context.user_id == 123456789
    assert context.guild_id == 987654321
    assert context.role_ids == [111, 222, 333]
    assert context.username == "TestUser"


def test_user_context_minimal() -> None:
    """Test creating UserContext with minimum fields."""
    context = UserContext(
        user_id=123456789,
        guild_id=987654321,
    )

    assert context.user_id == 123456789
    assert context.guild_id == 987654321
    assert context.role_ids == []  # Default
    assert context.username is None  # Default
