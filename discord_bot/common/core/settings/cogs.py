"""Which cogs this bot process loads.

Every flag defaults to on. Switching one off in the config keeps the extension
out of the process entirely: no commands, no listeners, and no entry in the web
dashboard, since each cog registers its config schema when it loads.
"""

from pydantic import BaseModel, ConfigDict, Field

# Flag name -> extension module, in load order.
COG_EXTENSIONS: dict[str, str] = {
    "verification": "discord_bot.verification.cog",
    "autoname": "discord_bot.autoname.cog",
    "purge": "discord_bot.purge.cog",
    "stockpile": "discord_bot.stockpile.cog",
    "roles": "discord_bot.roles.cog",
    "derived_roles": "discord_bot.derived_roles.cog",
}


class CogsSettings(BaseModel):
    """Per-cog load switches for the whole bot process."""

    verification: bool = Field(description="Load the verification cog", default=True)
    autoname: bool = Field(description="Load the autoname cog", default=True)
    purge: bool = Field(description="Load the purge cog", default=True)
    stockpile: bool = Field(description="Load the stockpile cog", default=True)
    roles: bool = Field(description="Load the roles cog", default=True)
    derived_roles: bool = Field(description="Load the derived roles cog", default=True)

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "verification": True,
                "autoname": True,
                "purge": True,
                "stockpile": True,
                "roles": True,
                "derived_roles": True,
            }
        },
    )

    def enabled_extensions(self) -> tuple[str, ...]:
        """Extension modules to load, in load order.

        Returns:
            tuple[str, ...]: Module paths of the cogs left enabled.
        """
        return tuple(
            module for name, module in COG_EXTENSIONS.items() if getattr(self, name) is True
        )

    def disabled_cogs(self) -> tuple[str, ...]:
        """Cog names switched off in the config.

        Returns:
            tuple[str, ...]: Flag names whose value is False.
        """
        return tuple(name for name in COG_EXTENSIONS if getattr(self, name) is False)
