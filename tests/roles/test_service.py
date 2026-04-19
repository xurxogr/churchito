"""Tests for ReactionRolesService."""

from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.roles.models import PanelType
from discord_bot.roles.service import ReactionRolesService


class TestReactionRolesService:
    """Tests for ReactionRolesService."""

    async def test_create_panel(self, test_session: AsyncSession) -> None:
        """Test panel creation."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        assert panel.id is not None
        assert panel.public_id is not None
        assert len(panel.public_id) == 21
        assert panel.guild_id == 123
        assert panel.channel_id == 456
        assert panel.name == "TestPanel"
        assert panel.panel_type == PanelType.TOGGLE
        assert panel.created_by == 789

    async def test_create_panel_with_all_options(self, test_session: AsyncSession) -> None:
        """Test panel creation with all optional parameters."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="FullPanel",
            panel_type=PanelType.EXCLUSIVE,
            created_by=789,
            guild_name="Test Guild",
            role_mappings=[{"emoji": "👍", "role_id": 100}],
            required_roles=[200, 300],
            dm_on_missing_role=True,
            dm_on_role_change=True,
            embed_config={"title": "Custom Title", "color": 0xFF0000},
        )

        assert panel.role_mappings == [{"emoji": "👍", "role_id": 100}]
        assert panel.required_roles == [200, 300]
        assert panel.dm_on_missing_role is True
        assert panel.dm_on_role_change is True
        assert panel.embed_config == {"title": "Custom Title", "color": 0xFF0000}

    async def test_get_by_id(self, test_session: AsyncSession) -> None:
        """Test getting panel by ID."""
        service = ReactionRolesService(test_session)

        created = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        retrieved = await service.get_by_id(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "TestPanel"

    async def test_get_by_id_not_found(self, test_session: AsyncSession) -> None:
        """Test getting non-existent panel."""
        service = ReactionRolesService(test_session)
        result = await service.get_by_id(99999)
        assert result is None

    async def test_get_by_public_id(self, test_session: AsyncSession) -> None:
        """Test getting panel by public ID."""
        service = ReactionRolesService(test_session)

        created = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        retrieved = await service.get_by_public_id(created.public_id)
        assert retrieved is not None
        assert retrieved.id == created.id

    async def test_get_by_public_id_not_found(self, test_session: AsyncSession) -> None:
        """Test getting panel by non-existent public ID."""
        service = ReactionRolesService(test_session)
        result = await service.get_by_public_id("nonexistent_public_id")
        assert result is None

    async def test_get_by_message_id(self, test_session: AsyncSession) -> None:
        """Test getting panel by message location."""
        service = ReactionRolesService(test_session)

        created = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        # Set message ID
        await service.set_message_id(
            panel_id=created.id, message_id=999888, guild_name="Test Guild"
        )

        retrieved = await service.get_by_message_id(
            guild_id=123,
            channel_id=456,
            message_id=999888,
        )
        assert retrieved is not None
        assert retrieved.id == created.id

    async def test_get_by_message_id_not_found(self, test_session: AsyncSession) -> None:
        """Test getting panel by non-existent message location."""
        service = ReactionRolesService(test_session)
        result = await service.get_by_message_id(
            guild_id=123,
            channel_id=456,
            message_id=99999,
        )
        assert result is None

    async def test_get_all_for_guild(self, test_session: AsyncSession) -> None:
        """Test getting all panels for a guild."""
        service = ReactionRolesService(test_session)

        await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="Panel1",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )
        await service.create_panel(
            guild_id=123,
            channel_id=457,
            name="Panel2",
            panel_type=PanelType.EXCLUSIVE,
            created_by=789,
            guild_name="Test Guild",
        )
        await service.create_panel(
            guild_id=999,  # Different guild
            channel_id=458,
            name="Panel3",
            panel_type=PanelType.VERIFY,
            created_by=789,
            guild_name="Other Guild",
        )

        panels = await service.get_all_for_guild(guild_id=123)
        assert len(panels) == 2

    async def test_get_all_for_guild_empty(self, test_session: AsyncSession) -> None:
        """Test getting panels for guild with no panels."""
        service = ReactionRolesService(test_session)
        panels = await service.get_all_for_guild(guild_id=99999)
        assert len(panels) == 0

    async def test_get_all_for_guild_sorted_by_name(self, test_session: AsyncSession) -> None:
        """Test that panels are sorted by name."""
        service = ReactionRolesService(test_session)

        await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="ZPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )
        await service.create_panel(
            guild_id=123,
            channel_id=457,
            name="APanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )
        await service.create_panel(
            guild_id=123,
            channel_id=458,
            name="MPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        panels = await service.get_all_for_guild(guild_id=123)
        assert panels[0].name == "APanel"
        assert panels[1].name == "MPanel"
        assert panels[2].name == "ZPanel"

    async def test_get_panel_names(self, test_session: AsyncSession) -> None:
        """Test getting panel names for autocomplete."""
        service = ReactionRolesService(test_session)

        await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="ColorRoles",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )
        await service.create_panel(
            guild_id=123,
            channel_id=457,
            name="GameRoles",
            panel_type=PanelType.EXCLUSIVE,
            created_by=789,
            guild_name="Test Guild",
        )

        names = await service.get_panel_names(guild_id=123)
        assert len(names) == 2
        assert "ColorRoles" in names
        assert "GameRoles" in names

    async def test_get_by_name(self, test_session: AsyncSession) -> None:
        """Test getting panel by name."""
        service = ReactionRolesService(test_session)

        await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="UniquePanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        found = await service.get_by_name(guild_id=123, name="UniquePanel")
        assert found is not None
        assert found.name == "UniquePanel"

    async def test_get_by_name_not_found(self, test_session: AsyncSession) -> None:
        """Test getting non-existent panel by name."""
        service = ReactionRolesService(test_session)
        result = await service.get_by_name(guild_id=123, name="NonExistent")
        assert result is None

    async def test_get_by_name_different_guild(self, test_session: AsyncSession) -> None:
        """Test that panel name is scoped to guild."""
        service = ReactionRolesService(test_session)

        await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="SameName",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        # Same name but different guild - should not find
        result = await service.get_by_name(guild_id=999, name="SameName")
        assert result is None

    async def test_set_message_id(self, test_session: AsyncSession) -> None:
        """Test setting message ID after posting."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        assert panel.message_id is None

        updated = await service.set_message_id(
            panel_id=panel.id, message_id=999888, guild_name="Test Guild"
        )
        assert updated is not None
        assert updated.message_id == 999888

    async def test_set_message_id_not_found(self, test_session: AsyncSession) -> None:
        """Test setting message ID for non-existent panel."""
        service = ReactionRolesService(test_session)
        result = await service.set_message_id(
            panel_id=99999, message_id=999888, guild_name="Test Guild"
        )
        assert result is None

    async def test_update_mappings(self, test_session: AsyncSession) -> None:
        """Test updating role mappings."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
            role_mappings=[{"emoji": "👍", "role_id": 100}],
        )

        new_mappings = [
            {"emoji": "👍", "role_id": 100},
            {"emoji": "👎", "role_id": 200},
            {"emoji": "🎉", "role_id": 300},
        ]

        updated = await service.update_mappings(
            panel_id=panel.id, role_mappings=new_mappings, guild_name="Test Guild"
        )
        assert updated is not None
        assert len(updated.role_mappings) == 3

    async def test_update_mappings_not_found(self, test_session: AsyncSession) -> None:
        """Test updating mappings for non-existent panel."""
        service = ReactionRolesService(test_session)
        result = await service.update_mappings(
            panel_id=99999, role_mappings=[], guild_name="Test Guild"
        )
        assert result is None

    async def test_add_mapping_unicode_emoji(self, test_session: AsyncSession) -> None:
        """Test adding a unicode emoji mapping."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        updated = await service.add_mapping(
            panel_id=panel.id,
            emoji="👍",
            emoji_id=None,
            role_id=100,
            display_name="Thumbs Up Role",
            guild_name="Test Guild",
        )

        assert updated is not None
        assert len(updated.role_mappings) == 1
        assert updated.role_mappings[0]["emoji"] == "👍"
        assert updated.role_mappings[0]["role_id"] == 100
        assert updated.role_mappings[0]["display_name"] == "Thumbs Up Role"
        assert "emoji_id" not in updated.role_mappings[0]

    async def test_add_mapping_custom_emoji(self, test_session: AsyncSession) -> None:
        """Test adding a custom emoji mapping."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        updated = await service.add_mapping(
            panel_id=panel.id,
            emoji="custom_emoji",
            emoji_id=12345,
            role_id=100,
            display_name=None,
            guild_name="Test Guild",
        )

        assert updated is not None
        assert len(updated.role_mappings) == 1
        assert updated.role_mappings[0]["emoji"] == "custom_emoji"
        assert updated.role_mappings[0]["emoji_id"] == 12345
        assert updated.role_mappings[0]["role_id"] == 100
        assert "display_name" not in updated.role_mappings[0]

    async def test_add_mapping_not_found(self, test_session: AsyncSession) -> None:
        """Test adding mapping to non-existent panel."""
        service = ReactionRolesService(test_session)
        result = await service.add_mapping(
            panel_id=99999,
            emoji="👍",
            emoji_id=None,
            role_id=100,
            display_name=None,
            guild_name="Test Guild",
        )
        assert result is None

    async def test_remove_mapping_unicode_emoji(self, test_session: AsyncSession) -> None:
        """Test removing a unicode emoji mapping."""
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

        updated = await service.remove_mapping(
            panel_id=panel.id,
            emoji="👍",
            emoji_id=None,
            guild_name="Test Guild",
        )

        assert updated is not None
        assert len(updated.role_mappings) == 1
        assert updated.role_mappings[0]["emoji"] == "👎"

    async def test_remove_mapping_custom_emoji(self, test_session: AsyncSession) -> None:
        """Test removing a custom emoji mapping."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
            role_mappings=[
                {"emoji": "custom", "emoji_id": 12345, "role_id": 100},
                {"emoji": "👎", "role_id": 200},
            ],
        )

        updated = await service.remove_mapping(
            panel_id=panel.id,
            emoji="custom",
            emoji_id=12345,
            guild_name="Test Guild",
        )

        assert updated is not None
        assert len(updated.role_mappings) == 1
        assert updated.role_mappings[0]["emoji"] == "👎"

    async def test_remove_mapping_not_found_panel(self, test_session: AsyncSession) -> None:
        """Test removing mapping from non-existent panel."""
        service = ReactionRolesService(test_session)
        result = await service.remove_mapping(
            panel_id=99999,
            emoji="👍",
            emoji_id=None,
            guild_name="Test Guild",
        )
        assert result is None

    async def test_remove_mapping_not_found_emoji(self, test_session: AsyncSession) -> None:
        """Test removing non-existent emoji mapping (no error, just no change)."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
            role_mappings=[{"emoji": "👍", "role_id": 100}],
        )

        updated = await service.remove_mapping(
            panel_id=panel.id,
            emoji="🎉",  # Not in mappings
            emoji_id=None,
            guild_name="Test Guild",
        )

        # Panel returned but mappings unchanged
        assert updated is not None
        assert len(updated.role_mappings) == 1

    async def test_update_panel_name(self, test_session: AsyncSession) -> None:
        """Test updating panel name."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="OldName",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        updated = await service.update_panel(
            panel_id=panel.id,
            guild_name="Test Guild",
            name="NewName",
        )

        assert updated is not None
        assert updated.name == "NewName"

    async def test_update_panel_type(self, test_session: AsyncSession) -> None:
        """Test updating panel type."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        updated = await service.update_panel(
            panel_id=panel.id,
            guild_name="Test Guild",
            panel_type=PanelType.EXCLUSIVE,
        )

        assert updated is not None
        assert updated.panel_type == PanelType.EXCLUSIVE

    async def test_update_panel_dm_settings(self, test_session: AsyncSession) -> None:
        """Test updating panel DM settings."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        updated = await service.update_panel(
            panel_id=panel.id,
            guild_name="Test Guild",
            dm_on_missing_role=True,
            dm_on_role_change=True,
        )

        assert updated is not None
        assert updated.dm_on_missing_role is True
        assert updated.dm_on_role_change is True

    async def test_update_panel_required_roles(self, test_session: AsyncSession) -> None:
        """Test updating panel required roles."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        updated = await service.update_panel(
            panel_id=panel.id,
            guild_name="Test Guild",
            required_roles=[100, 200],
        )

        assert updated is not None
        assert updated.required_roles == [100, 200]

    async def test_update_panel_embed_config(self, test_session: AsyncSession) -> None:
        """Test updating panel embed config."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        updated = await service.update_panel(
            panel_id=panel.id,
            guild_name="Test Guild",
            embed_config={"title": "Custom", "color": 0xFF0000},
        )

        assert updated is not None
        assert updated.embed_config == {"title": "Custom", "color": 0xFF0000}

    async def test_update_panel_not_found(self, test_session: AsyncSession) -> None:
        """Test updating non-existent panel."""
        service = ReactionRolesService(test_session)
        result = await service.update_panel(
            panel_id=99999,
            guild_name="Test Guild",
            name="NewName",
        )
        assert result is None

    async def test_delete(self, test_session: AsyncSession) -> None:
        """Test deleting a panel."""
        service = ReactionRolesService(test_session)

        panel = await service.create_panel(
            guild_id=123,
            channel_id=456,
            name="TestPanel",
            panel_type=PanelType.TOGGLE,
            created_by=789,
            guild_name="Test Guild",
        )

        deleted = await service.delete(panel_id=panel.id, guild_name="Test Guild")
        assert deleted is True

        # Verify it's gone
        result = await service.get_by_id(panel.id)
        assert result is None

    async def test_delete_not_found(self, test_session: AsyncSession) -> None:
        """Test deleting non-existent panel."""
        service = ReactionRolesService(test_session)
        result = await service.delete(panel_id=99999, guild_name="Test Guild")
        assert result is False
