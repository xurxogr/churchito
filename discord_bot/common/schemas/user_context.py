"""User context for permission verification."""

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """User context for permission verification.

    This model represents a user's identity and permissions without
    Discord-specific dependencies. Both Discord cogs and web routers
    can create this context from their respective sources.
    """

    user_id: int = Field(description="Unique user ID")
    guild_id: int = Field(description="Guild/server ID")
    role_ids: list[int] = Field(default_factory=lambda: [], description="User's role IDs")
    username: str | None = Field(default=None, description="User's display name")

    def has_role(self, role_id: int) -> bool:
        """Check if the user has a specific role.

        Args:
            role_id (int): Role ID to check

        Returns:
            bool: True if the user has the role
        """
        return role_id in self.role_ids

    def has_any_role(self, role_ids: list[int]) -> bool:
        """Check if the user has any of the specified roles.

        Args:
            role_ids (list[int]): List of role IDs to check

        Returns:
            bool: True if the user has at least one of the roles
        """
        return any(role_id in self.role_ids for role_id in role_ids)

    def has_all_roles(self, role_ids: list[int]) -> bool:
        """Check if the user has all of the specified roles.

        Args:
            role_ids (list[int]): List of role IDs to check

        Returns:
            bool: True if the user has all the roles
        """
        return all(role_id in self.role_ids for role_id in role_ids)
