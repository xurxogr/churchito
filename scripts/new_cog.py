#!/usr/bin/env python3
"""Scaffold a new cog with best practices.

Usage:
    python scripts/new_cog.py <cog_name> [--with-service]

Examples:
    python scripts/new_cog.py moderation
    python scripts/new_cog.py economy --with-service
"""

import argparse
import sys
from pathlib import Path

SIMPLE_COG_TEMPLATE = '''"""{{name}} cog."""

import discord
from discord.ext import commands

from discord_bot.bot import DiscordBot
from discord_bot.common.decorators import timeout


class {{class_name}}Cog(commands.Cog):
    """{{description}}"""

    def __init__(self, bot: DiscordBot) -> None:
        """Initialize cog.

        Args:
            bot: Discord bot instance
        """
        self.bot = bot

    @timeout(30)
    @commands.hybrid_command()
    async def {{command_name}}(self, ctx: commands.Context) -> None:
        """{{command_description}}

        Args:
            ctx: Command context
        """
        await ctx.send("Hello from {{name}}!")


async def setup(bot: DiscordBot) -> None:
    """Load the cog.

    Args:
        bot: Discord bot instance
    """
    await bot.add_cog({{class_name}}Cog(bot))
'''

SERVICE_COG_TEMPLATE = '''"""{{name}} cog."""

import discord
from discord.ext import commands

from discord_bot.bot import DiscordBot
from discord_bot.common.decorators import timeout
from discord_bot.common.schemas import UserContext
from discord_bot.{{name}}.services import {{class_name}}Service


class {{class_name}}Cog(commands.Cog):
    """{{description}}

    This is a thin adapter that handles Discord interactions and delegates
    business logic to the service layer.
    """

    def __init__(self, bot: DiscordBot) -> None:
        """Initialize cog.

        Args:
            bot: Discord bot instance
        """
        self.bot = bot

    async def _get_service(self) -> {{class_name}}Service:
        """Get service instance with database session.

        Returns:
            {{class_name}}Service instance
        """
        session = self.bot.database.get_session()
        return {{class_name}}Service(session)

    @timeout(30)
    @commands.hybrid_command()
    async def {{command_name}}(self, interaction: discord.Interaction) -> None:
        """{{command_description}}

        Args:
            interaction: Discord interaction
        """
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        # Create Discord-agnostic user context
        user_context = UserContext(
            user_id=interaction.user.id,
            guild_id=interaction.guild.id,
            role_ids=[role.id for role in interaction.user.roles]
            if isinstance(interaction.user, discord.Member)
            else [],
            username=interaction.user.name,
        )

        # Get service and call business logic
        service = await self._get_service()
        result = await service.do_something(user_context)

        await interaction.response.send_message(f"Result: {result}")


async def setup(bot: DiscordBot) -> None:
    """Load the cog.

    Args:
        bot: Discord bot instance
    """
    await bot.add_cog({{class_name}}Cog(bot))
'''

SERVICE_TEMPLATE = '''"""Service layer for {{name}} feature."""

from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.common.schemas import UserContext


class {{class_name}}Service:
    """Business logic for {{name}} feature.

    This service is Discord-agnostic and works with primitives/UserContext.
    All Discord interaction logic should stay in the cog.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service.

        Args:
            session: Database session
        """
        self.session = session

    async def do_something(self, user: UserContext) -> str:
        """Example service method.

        Args:
            user: User context

        Returns:
            Result string
        """
        # TODO: Implement business logic
        return f"Hello {user.username}!"

    async def can_use_feature(self, user: UserContext) -> bool:
        """Check if user can use this feature.

        Args:
            user: User context

        Returns:
            True if user has permission
        """
        # Example: Check if user has specific role
        required_roles = [123456789]  # TODO: Configure this
        return user.has_any_role(required_roles)
'''

TEST_TEMPLATE = '''"""Tests for {{name}} cog."""

import pytest
from unittest.mock import MagicMock

from discord_bot.{{name}}.cog import {{class_name}}Cog


@pytest.fixture
def {{name}}_cog(mock_bot: MagicMock) -> {{class_name}}Cog:
    """Create {{name}} cog for testing.

    Args:
        mock_bot: Mock Discord bot

    Returns:
        {{class_name}}Cog instance
    """
    return {{class_name}}Cog(mock_bot)


@pytest.mark.asyncio
async def test_cog_initialization({{name}}_cog: {{class_name}}Cog, mock_bot: MagicMock) -> None:
    """Test cog initializes correctly.

    Args:
        {{name}}_cog: {{class_name}} cog
        mock_bot: Mock bot
    """
    assert {{name}}_cog.bot == mock_bot
'''

SERVICE_TEST_TEMPLATE = '''"""Tests for {{name}} service."""

import pytest

from discord_bot.common.schemas import UserContext
from discord_bot.common.services import DatabaseService
from discord_bot.{{name}}.services import {{class_name}}Service


@pytest.fixture
async def {{name}}_service(test_database: DatabaseService) -> {{class_name}}Service:
    """Create {{name}} service for testing.

    Args:
        test_database: Test database service

    Returns:
        {{class_name}}Service instance
    """
    session = test_database.get_session()
    return {{class_name}}Service(session)


@pytest.mark.asyncio
async def test_do_something({{name}}_service: {{class_name}}Service) -> None:
    """Test do_something method.

    Args:
        {{name}}_service: Service instance
    """
    user = UserContext(user_id=123, guild_id=456, role_ids=[])
    result = await {{name}}_service.do_something(user)
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_can_use_feature({{name}}_service: {{class_name}}Service) -> None:
    """Test permission checking.

    Args:
        {{name}}_service: Service instance
    """
    # User without required role
    user_no_role = UserContext(user_id=123, guild_id=456, role_ids=[])
    can_use = await {{name}}_service.can_use_feature(user_no_role)
    assert can_use is False

    # User with required role
    user_with_role = UserContext(user_id=123, guild_id=456, role_ids=[123456789])
    can_use = await {{name}}_service.can_use_feature(user_with_role)
    assert can_use is True
'''


def to_class_name(name: str) -> str:
    """Convert snake_case to PascalCase.

    Args:
        name: Snake case name

    Returns:
        PascalCase name
    """
    return "".join(word.capitalize() for word in name.split("_"))


def create_cog(name: str, with_service: bool = False) -> bool:
    """Create a new cog with the proper structure.

    Args:
        name: Cog name (snake_case)
        with_service: Whether to create a service layer

    Returns:
        True if successful, False otherwise
    """
    # Validate name
    if not name.isidentifier():
        print(f"❌ Invalid cog name: {name}")
        print("   Use snake_case (e.g., 'my_cog', 'moderation')")
        return False

    class_name = to_class_name(name)
    cog_dir = Path(f"discord_bot/{name}")
    test_dir = Path(f"tests/{name}")

    # Check if cog already exists
    if cog_dir.exists():
        print(f"❌ Cog directory already exists: {cog_dir}")
        return False

    # Create directories
    cog_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    print(f"Creating cog: {name}")
    print(f"  Class name: {class_name}Cog")
    print(f"  Directory: {cog_dir}")

    # Create __init__.py files
    (cog_dir / "__init__.py").write_text("")
    (test_dir / "__init__.py").write_text("")

    # Choose template
    if with_service:
        cog_template = SERVICE_COG_TEMPLATE
        # Create service directory
        service_dir = cog_dir / "services"
        service_dir.mkdir(exist_ok=True)
        (service_dir / "__init__.py").write_text(
            f'"""Services for {name} feature."""\n\n'
            f"from discord_bot.{name}.services.{name} import {class_name}Service\n\n"
            f'__all__ = ["{class_name}Service"]\n'
        )
    else:
        cog_template = SIMPLE_COG_TEMPLATE

    # Create cog file
    cog_content = cog_template.replace("{{name}}", name)
    cog_content = cog_content.replace("{{class_name}}", class_name)
    cog_content = cog_content.replace("{{description}}", f"{class_name} commands")
    cog_content = cog_content.replace("{{command_name}}", name)
    cog_content = cog_content.replace("{{command_description}}", f"{class_name} command")

    (cog_dir / "cog.py").write_text(cog_content)
    print(f"  ✅ Created {cog_dir}/cog.py")

    # Create service file if needed
    if with_service:
        service_content = SERVICE_TEMPLATE.replace("{{name}}", name)
        service_content = service_content.replace("{{class_name}}", class_name)
        (service_dir / f"{name}.py").write_text(service_content)
        print(f"  ✅ Created {service_dir}/{name}.py")

        # Create service test
        service_test_content = SERVICE_TEST_TEMPLATE.replace("{{name}}", name)
        service_test_content = service_test_content.replace("{{class_name}}", class_name)
        test_service_dir = test_dir / "services"
        test_service_dir.mkdir(exist_ok=True)
        (test_service_dir / "__init__.py").write_text("")
        (test_service_dir / f"test_{name}.py").write_text(service_test_content)
        print(f"  ✅ Created {test_service_dir}/test_{name}.py")

    # Create test file
    test_content = TEST_TEMPLATE.replace("{{name}}", name)
    test_content = test_content.replace("{{class_name}}", class_name)
    (test_dir / "test_cog.py").write_text(test_content)
    print(f"  ✅ Created {test_dir}/test_cog.py")

    # Print next steps
    print(f"\n✅ Cog '{name}' created successfully!")
    print("\n📝 Next steps:")
    print("  1. Add cog to bot.py:")
    print(f'     cogs_to_load = [..., "discord_bot.{name}.cog"]')
    print(f"  2. Implement your commands in {cog_dir}/cog.py")
    if with_service:
        print(f"  3. Implement business logic in {service_dir}/{name}.py")
        print(f"  4. Write tests in {test_dir}/")
    else:
        print(f"  3. Write tests in {test_dir}/test_cog.py")
    print(f"  4. Run tests: pytest {test_dir}/")
    print(f"  5. Check code: ruff check {cog_dir}/cog.py")
    print("  6. Validate structure: python scripts/validate_cog_structure.py")

    return True


def main() -> int:
    """Main entry point.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(description="Scaffold a new Discord cog with best practices")
    parser.add_argument("name", help="Cog name in snake_case (e.g., 'moderation')")
    parser.add_argument(
        "--with-service",
        action="store_true",
        help="Create with service layer (for complex cogs with business logic)",
    )

    args = parser.parse_args()

    if create_cog(args.name, args.with_service):
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
