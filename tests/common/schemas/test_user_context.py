"""Tests for the UserContext model.

These tests are temporary, until there is a service that uses them.
"""

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


def test_user_context_has_role() -> None:
    """Test the has_role method."""
    context = UserContext(
        user_id=123456789,
        guild_id=987654321,
        role_ids=[111, 222, 333],
    )

    assert context.has_role(111) is True
    assert context.has_role(222) is True
    assert context.has_role(999) is False


def test_user_context_has_any_role() -> None:
    """Test the has_any_role method."""
    context = UserContext(
        user_id=123456789,
        guild_id=987654321,
        role_ids=[111, 222, 333],
    )

    # Has at least one of these roles
    assert context.has_any_role([111, 444]) is True
    assert context.has_any_role([222, 555]) is True
    assert context.has_any_role([111, 222]) is True

    # Has none of these roles
    assert context.has_any_role([444, 555]) is False
    assert context.has_any_role([999]) is False

    # Empty list
    assert context.has_any_role([]) is False


def test_user_context_has_all_roles() -> None:
    """Test the has_all_roles method."""
    context = UserContext(
        user_id=123456789,
        guild_id=987654321,
        role_ids=[111, 222, 333],
    )

    # Has all of these roles
    assert context.has_all_roles([111, 222]) is True
    assert context.has_all_roles([111]) is True
    assert context.has_all_roles([111, 222, 333]) is True

    # Missing at least one role
    assert context.has_all_roles([111, 999]) is False
    assert context.has_all_roles([444, 555]) is False

    # Empty list (vacuously true)
    assert context.has_all_roles([]) is True


def test_user_context_no_roles() -> None:
    """Test UserContext without roles."""
    context = UserContext(
        user_id=123456789,
        guild_id=987654321,
        role_ids=[],
    )

    assert context.has_role(111) is False
    assert context.has_any_role([111, 222]) is False
    assert context.has_all_roles([]) is True
    assert context.has_all_roles([111]) is False
