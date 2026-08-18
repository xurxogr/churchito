"""Which role pickers are limited to roles the bot can manage.

Roles the bot only *checks* (who may run a command, who is affected/excluded,
which role triggers a rule) may sit above the bot in the hierarchy, so their
pickers must offer every role. Only roles the bot *assigns or removes* need
to be below its top role.
"""

import pytest

from discord_bot.autoname.config import AUTONAME_CONFIG_SCHEMA
from discord_bot.autoname.config import ConfigKey as AutonameKey
from discord_bot.common.enums.config_option_type import ConfigOptionType
from discord_bot.common.schemas.cog_config_schema import CogConfigSchema
from discord_bot.derived_roles.config import DERIVED_ROLES_CONFIG_SCHEMA
from discord_bot.derived_roles.config import ConfigKey as DerivedKey
from discord_bot.purge.config import PURGE_CONFIG_SCHEMA
from discord_bot.purge.enums import ConfigKey as PurgeKey
from discord_bot.roles.config import ROLES_CONFIG_SCHEMA
from discord_bot.roles.enums import ConfigKey as RolesKey
from discord_bot.stockpile.config import STOCKPILE_CONFIG_SCHEMA
from discord_bot.stockpile.enums import ConfigKey as StockpileKey
from discord_bot.verification.config import VERIFICATION_CONFIG_SCHEMA
from discord_bot.verification.enums import ConfigKey as VerificationKey

ALL_SCHEMAS = [
    AUTONAME_CONFIG_SCHEMA,
    DERIVED_ROLES_CONFIG_SCHEMA,
    PURGE_CONFIG_SCHEMA,
    ROLES_CONFIG_SCHEMA,
    STOCKPILE_CONFIG_SCHEMA,
    VERIFICATION_CONFIG_SCHEMA,
]

# Roles the bot assigns/removes: the picker must hide roles it cannot manage.
MANAGED_ROLE_OPTIONS = [
    (PURGE_CONFIG_SCHEMA, PurgeKey.USER_REACTION_ROLE),
    (PURGE_CONFIG_SCHEMA, PurgeKey.WAR_ROLES_TO_REMOVE),
    (PURGE_CONFIG_SCHEMA, PurgeKey.WAR_ROLES_TO_ADD),
    (PURGE_CONFIG_SCHEMA, PurgeKey.WAR_GLOBAL_ROLES_TO_REMOVE),
    (PURGE_CONFIG_SCHEMA, PurgeKey.WAR_DEFAULT_PROMOTION),
    (PURGE_CONFIG_SCHEMA, PurgeKey.GLOBAL_ROLES_TO_REMOVE),
    (PURGE_CONFIG_SCHEMA, PurgeKey.GLOBAL_ROLES_TO_ADD),
    (VERIFICATION_CONFIG_SCHEMA, VerificationKey.REGULAR_ROLES_ADD),
    (VERIFICATION_CONFIG_SCHEMA, VerificationKey.REGULAR_ROLES_REMOVE),
    (VERIFICATION_CONFIG_SCHEMA, VerificationKey.ALLY_ROLES_ADD),
    (VERIFICATION_CONFIG_SCHEMA, VerificationKey.ALLY_ROLES_REMOVE),
    # Autoname renames members, and a member holding a role above the bot cannot
    # be renamed anyway, so its pickers stay restricted too.
    (AUTONAME_CONFIG_SCHEMA, AutonameKey.REQUIRED_ROLES),
]

# Roles the bot only checks membership of: any role, even above the bot.
MEMBERSHIP_ROLE_OPTIONS = [
    (PURGE_CONFIG_SCHEMA, PurgeKey.WAR_ADMIN_ROLES),
    (PURGE_CONFIG_SCHEMA, PurgeKey.WAR_AFFECTED_ROLES),
    (PURGE_CONFIG_SCHEMA, PurgeKey.GLOBAL_ADMIN_ROLES),
    (PURGE_CONFIG_SCHEMA, PurgeKey.GLOBAL_EXCLUDED_ROLES),
    (VERIFICATION_CONFIG_SCHEMA, VerificationKey.MOD_ROLES),
    (VERIFICATION_CONFIG_SCHEMA, VerificationKey.BLOCKING_ROLES),
    (VERIFICATION_CONFIG_SCHEMA, VerificationKey.WELCOME_CARD_REQUIRED_ROLES),
    (ROLES_CONFIG_SCHEMA, RolesKey.MANAGE_ROLES),
    (STOCKPILE_CONFIG_SCHEMA, StockpileKey.ADD_ROLES),
    (STOCKPILE_CONFIG_SCHEMA, StockpileKey.DELETE_ROLES),
    (STOCKPILE_CONFIG_SCHEMA, StockpileKey.EDIT_ROLES),
    (STOCKPILE_CONFIG_SCHEMA, StockpileKey.ALLOWED_VIEW_ROLES),
]

# (schema, table key, column key) -> manageable_only expected on the column.
TABLE_ROLE_COLUMNS = [
    (PURGE_CONFIG_SCHEMA, PurgeKey.WAR_PROMOTIONS, "from_role", False),
    (PURGE_CONFIG_SCHEMA, PurgeKey.WAR_PROMOTIONS, "to_role", True),
    (DERIVED_ROLES_CONFIG_SCHEMA, DerivedKey.RULES, "trigger_role", False),
    (DERIVED_ROLES_CONFIG_SCHEMA, DerivedKey.RULES, "target_role", True),
    (AUTONAME_CONFIG_SCHEMA, AutonameKey.ROLE_TAGS, "role_id", True),
    (AUTONAME_CONFIG_SCHEMA, AutonameKey.ROLE_PREFIXES, "role_id", True),
]


def _option_key(schema: CogConfigSchema, key: str) -> str:
    """Readable parametrize ID.

    Args:
        schema (CogConfigSchema): Schema owning the option.
        key (str): Option key.

    Returns:
        str: ``cog:key``.
    """
    return f"{schema.cog_name}:{key}"


@pytest.mark.parametrize(
    ("schema", "key"),
    MANAGED_ROLE_OPTIONS,
    ids=[_option_key(s, k) for s, k in MANAGED_ROLE_OPTIONS],
)
def test_managed_role_options_are_restricted(schema: CogConfigSchema, key: str) -> None:
    """Options whose roles the bot grants/revokes only offer manageable roles."""
    option = schema.get_option(key)

    assert option is not None
    assert option.manageable_only is True


@pytest.mark.parametrize(
    ("schema", "key"),
    MEMBERSHIP_ROLE_OPTIONS,
    ids=[_option_key(s, k) for s, k in MEMBERSHIP_ROLE_OPTIONS],
)
def test_membership_role_options_offer_any_role(schema: CogConfigSchema, key: str) -> None:
    """Options that only check membership must not hide roles above the bot."""
    option = schema.get_option(key)

    assert option is not None
    assert option.manageable_only is False


@pytest.mark.parametrize(
    ("schema", "key", "column", "expected"),
    TABLE_ROLE_COLUMNS,
    ids=[f"{_option_key(s, k)}.{c}" for s, k, c, _ in TABLE_ROLE_COLUMNS],
)
def test_table_role_columns_scope(
    schema: CogConfigSchema, key: str, column: str, expected: bool
) -> None:
    """Table role columns declare whether the bot must be able to manage the role."""
    option = schema.get_option(key)

    assert option is not None and option.columns is not None
    col = next(c for c in option.columns if c["key"] == column)
    assert col.get("manageable_only", False) is expected


def test_every_role_option_is_classified() -> None:
    """Every ROLE/ROLE_LIST option and role table column appears in one of the lists above."""
    classified = {_option_key(s, k) for s, k in [*MANAGED_ROLE_OPTIONS, *MEMBERSHIP_ROLE_OPTIONS]}
    classified_columns = {f"{_option_key(s, k)}.{c}" for s, k, c, _ in TABLE_ROLE_COLUMNS}

    for schema in ALL_SCHEMAS:
        for option in schema.options:
            option_id = _option_key(schema, option.key)
            if option.option_type in (ConfigOptionType.ROLE, ConfigOptionType.ROLE_LIST):
                assert option_id in classified, f"unclassified role option {option_id}"
            for col in option.columns or []:
                if col.get("type") == "role":
                    assert f"{option_id}.{col['key']}" in classified_columns, (
                        f"unclassified role column {option_id}.{col['key']}"
                    )
