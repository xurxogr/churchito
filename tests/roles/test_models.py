"""Tests for ReactionPanel model."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.roles.models import PanelType
from discord_bot.roles.service import ReactionRolesService


class TestPanelType:
    """Tests for PanelType enum."""

    def test_toggle_value(self) -> None:
        """Test toggle type value."""
        assert PanelType.TOGGLE.value == "toggle"

    def test_exclusive_value(self) -> None:
        """Test exclusive type value."""
        assert PanelType.EXCLUSIVE.value == "exclusive"

    def test_verify_value(self) -> None:
        """Test verify type value."""
        assert PanelType.VERIFY.value == "verify"

    def test_is_string_enum(self) -> None:
        """Test that PanelType is a string enum."""
        assert isinstance(PanelType.TOGGLE.value, str)
        assert str(PanelType.TOGGLE) == "toggle"


class TestReactionPanelModel:
    """Tests for ReactionPanel model methods."""

    async def test_has_required_role_with_matching_role(self, test_session: AsyncSession) -> None:
        """Test has_required_role returns True when user has a matching role."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
            required_roles=[100, 200],
        )

        assert panel.has_required_role([100]) is True
        assert panel.has_required_role([200]) is True
        assert panel.has_required_role([100, 300]) is True

    async def test_has_required_role_without_matching_role(
        self, test_session: AsyncSession
    ) -> None:
        """Test has_required_role returns False when user has no matching role."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
            required_roles=[100, 200],
        )

        assert panel.has_required_role([300]) is False
        assert panel.has_required_role([]) is False

    async def test_has_required_role_with_no_roles_required(
        self, test_session: AsyncSession
    ) -> None:
        """Test has_required_role returns True when no roles are required."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
            required_roles=[],
        )

        assert panel.has_required_role([]) is True
        assert panel.has_required_role([100]) is True

    async def test_find_mapping_by_unicode_emoji(self, test_session: AsyncSession) -> None:
        """Test finding a mapping by unicode emoji."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
            role_mappings=[
                {"emoji": "👍", "role_id": 100},
                {"emoji": "👎", "role_id": 200},
            ],
        )

        mapping = panel.find_mapping_by_emoji("👍")
        assert mapping is not None
        assert mapping["role_id"] == 100

        mapping2 = panel.find_mapping_by_emoji("👎")
        assert mapping2 is not None
        assert mapping2["role_id"] == 200

    async def test_find_mapping_by_custom_emoji(self, test_session: AsyncSession) -> None:
        """Test finding a mapping by custom emoji ID."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
            role_mappings=[
                {"emoji": "custom_emoji", "emoji_id": 12345, "role_id": 100},
                {"emoji": "another", "emoji_id": 67890, "role_id": 200},
            ],
        )

        # Custom emoji should be found by ID, not name
        mapping = panel.find_mapping_by_emoji("custom_emoji", emoji_id=12345)
        assert mapping is not None
        assert mapping["role_id"] == 100

        mapping2 = panel.find_mapping_by_emoji("another", emoji_id=67890)
        assert mapping2 is not None
        assert mapping2["role_id"] == 200

    async def test_find_mapping_by_emoji_not_found(self, test_session: AsyncSession) -> None:
        """Test finding a mapping that doesn't exist."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
            role_mappings=[
                {"emoji": "👍", "role_id": 100},
            ],
        )

        # Non-existent unicode emoji
        assert panel.find_mapping_by_emoji("🎉") is None

        # Non-existent custom emoji
        assert panel.find_mapping_by_emoji("custom", emoji_id=99999) is None

        # Unicode emoji looking for custom (should not match)
        assert panel.find_mapping_by_emoji("👍", emoji_id=12345) is None

    async def test_find_mapping_unicode_not_matched_as_custom(
        self, test_session: AsyncSession
    ) -> None:
        """Test that unicode emoji is not matched when looking for custom."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
            role_mappings=[
                {"emoji": "👍", "role_id": 100},  # Unicode, no emoji_id
            ],
        )

        # Looking with emoji_id should NOT find the unicode emoji
        assert panel.find_mapping_by_emoji("👍", emoji_id=12345) is None

    async def test_get_all_role_ids(self, test_session: AsyncSession) -> None:
        """Test getting all role IDs from mappings."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
            role_mappings=[
                {"emoji": "👍", "role_id": 100},
                {"emoji": "👎", "role_id": 200},
                {"emoji": "🎉", "role_id": 300},
            ],
        )

        role_ids = panel.get_all_role_ids()
        assert len(role_ids) == 3
        assert 100 in role_ids
        assert 200 in role_ids
        assert 300 in role_ids

    async def test_get_all_role_ids_empty_mappings(self, test_session: AsyncSession) -> None:
        """Test getting role IDs from empty mappings."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
            role_mappings=[],
        )

        role_ids = panel.get_all_role_ids()
        assert role_ids == []

    async def test_repr(self, test_session: AsyncSession) -> None:
        """Test string representation of panel."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.EXCLUSIVE,
            created_by=789,
            guild_name="Test Guild",
        )

        repr_str = repr(panel)
        assert "ReactionPanel" in repr_str
        assert "TestPanel" in repr_str
        assert "exclusive" in repr_str

    async def test_panel_defaults(self, test_session: AsyncSession) -> None:
        """Test default values for panel creation."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        assert panel.role_mappings == []
        assert panel.required_roles == []
        assert panel.dm_on_missing_role is False
        assert panel.dm_on_role_change is False
        assert panel.embed_config is None
        assert panel.message_id is None
        assert panel.public_id is not None
        assert len(panel.public_id) == 21

    async def test_panel_created_at(self, test_session: AsyncSession) -> None:
        """Test that created_at is set automatically."""
        service = ReactionRolesService(test_session)

        before = datetime.now(UTC)
        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )
        after = datetime.now(UTC)

        assert panel.created_at is not None
        assert before <= panel.created_at <= after
