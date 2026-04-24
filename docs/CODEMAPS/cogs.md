# Discord Bot Cogs Codemap

<!-- Generated: 2026-04-24 | Files scanned: 120 | Token estimate: ~1500 -->

**Last Updated:** 2026-04-24
**Entry Point:** `discord_bot/bot.py:_load_cogs()`

## Cog Loading System

```python
# discord_bot/bot.py:_load_cogs()
cogs_to_load = [
    "discord_bot.verification.cog",
    "discord_bot.autoname.cog",
    "discord_bot.purge.cog",
    "discord_bot.stockpile.cog",
    "discord_bot.roles.cog",
]
for cog_module in cogs_to_load:
    await self.load_extension(cog_module)
```

Each cog is a `commands.Cog` subclass that:
1. Handles Discord events (on_member_join, on_message, etc.)
2. Registers commands and application commands
3. Manages persistent views (button interactions)
4. Delegates business logic to Service classes

---

## Verification Cog

**File:** `discord_bot/verification/cog.py`
**Class:** `VerificationCog(commands.Cog)`

### Events & Handlers

| Event | Handler | Purpose |
|-------|---------|---------|
| `on_ready` | `cog_load()` | Restore pending verifications, start health check |
| `on_member_join` | `on_member_join()` | Trigger verification flow |
| `on_message` | `on_message()` | Handle screenshot uploads |
| Button click | `on_verification_button()` | Member/Ally selection |
| Button click | `on_mod_review_button()` | Accept/Reject/Re-review |

### Data Models

**Model files:**
- `discord_bot/verification/models/verification_request.py` - ORM model
- `discord_bot/verification/models/api_response.py` - API response schemas

```python
class VerificationRequest(Base):
    __tablename__ = "verification_requests"

    id: int  # autoincrement
    public_id: str(21)  # NanoID, prevents IDOR
    guild_id: int
    user_id: int
    username: str(100)
    verification_type: str(20)  # "REGULAR", "ALLY", etc.

    # Screenshots
    screenshot_1_url: str (nullable)
    screenshot_2_url: str (nullable)

    # OCR results (JSON)
    player_info: dict (nullable)  # {name, level, faction, ...}

    # Review info
    reviewed_by_id: int (nullable)
    reviewed_by_username: str (nullable)
    rejection_reason: str (nullable)
    mod_message_id: int (nullable)

    # Status
    status: str(30)  # PENDING_SCREENSHOTS, SUBMITTED, PENDING_REVIEW, APPROVED, REJECTED

    # Timestamps
    created_at: datetime
    screenshots_submitted_at: datetime (nullable)
    reviewed_at: datetime (nullable)
```

**Indexes:** `ix_verification_guild_id`, `ix_verification_user_id`, `ix_verification_status`

### Verification Processing

**File:** `discord_bot/verification/auto_processor.py`

New functions for per-reason auto-reject toggles:
```python
def process_verification(
    request: VerificationRequest,
    api_response: VerificationAPIResponse,
    config: dict[str, Any],
    member_display_name: str,
) -> set[RejectType]:
    """Check all verification rules, return set of ALL failures."""
    # Returns: {RejectType.WRONG_FACTION, RejectType.TIME_DIFF, ...}

def get_auto_rejectable_failures(
    config: dict[str, Any],
    failures: set[RejectType],
) -> set[RejectType]:
    """Filter failures to only those with auto-reject enabled (per-reason toggles)."""

def is_auto_reject_enabled(config: dict[str, Any], reason: RejectType) -> bool:
    """Check if auto-rejection is enabled for a specific reason."""

def get_auto_reject_config_key(reason: RejectType) -> ConfigKey | None:
    """Get the config key for an auto-reject toggle."""
```

**File:** `discord_bot/verification/enums/reject_type.py`

```python
class RejectType(StrEnum):
    """Types of verification rejection (6 types)."""
    INVALID_SCREENSHOTS = "invalid_screenshots"  # API 422
    WRONG_FACTION = "wrong_faction"
    WRONG_SHARD = "wrong_shard"
    HAS_REGIMENT = "has_regiment"
    NAME_MISMATCH = "name_mismatch"
    TIME_DIFF = "time_diff"
```

### Service

**File:** `discord_bot/verification/service.py`

Key methods:
```python
async def create_request(guild_id: int, user_id: int, username: str, ...) -> VerificationRequest
async def get_request(request_id: int) -> VerificationRequest | None
async def get_pending_by_user(guild_id: int, user_id: int) -> VerificationRequest | None
async def get_all_pending_screenshots() -> list[VerificationRequest]
async def update_screenshots(request_id: int, urls: dict) -> bool
async def update_status(request_id: int, status: str) -> bool
async def approve(request_id: int, reviewed_by_id: int, reviewed_by_username: str) -> bool
async def reject(request_id: int, rejection_reason: str, reviewed_by_id: int) -> bool
```

### Configuration Schema

**File:** `discord_bot/verification/config.py`

Config options include:
- `enabled` - Enable/disable verification cog
- `mod_channel_id` - Channel for mod reviews
- `verification_role_id` - Role to assign on approval
- `screenshot_timeout_minutes` - Screenshot submission deadline
- `auto_process_mode` - OCR integration (BOTH, ACCEPT_ONLY, REJECT_ONLY, NONE)
- `name_match_mode` - Match user's in-game name (EXACT, CONTAINS)
- **Per-reason auto-reject toggles** (NEW, v2025-04-24):
  - `auto_reject_invalid_screenshots` - Auto-reject if API returns 422
  - `auto_reject_wrong_faction` - Auto-reject if faction mismatch
  - `auto_reject_wrong_shard` - Auto-reject if shard mismatch
  - `auto_reject_has_regiment` - Auto-reject if user has wrong regiment
  - `auto_reject_name_mismatch` - Auto-reject if name doesn't match
  - `auto_reject_time_diff` - Auto-reject if screenshot too old
- Plus embed customization (titles, colors, descriptions)

### Event Bus

Publishes:
- `VerificationCompleted` - After approval
- `VerificationRejected` - After rejection

### Handlers

**File:** `discord_bot/verification/handlers/`

- `flow.py` - Start verification, send instructions
- `auto_processing.py` - OCR integration (if enabled)
- `mod_messages.py` - Update mod channel messages (preserves existing data)
- `utils.py` - Helper functions

### API Response Models

**File:** `discord_bot/verification/models/api_response.py`

```python
class VerificationAPIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")  # Strict validation

    name: str              # Player's in-game name
    level: int             # Player's level
    regiment: str          # Regiment name
    faction: str           # 'colonial' or 'wardens'
    shard: str             # 'ABLE' or 'CHARLIE'
    ingame_time: str       # Time in screenshot (e.g., "267, 21:45")
    war_number: int        # Current war number
    current_ingame_time: str  # Current in-game time (e.g., "268, 14:30")

class VerificationAPIResult(BaseModel):
    model_config = ConfigDict(extra="forbid")  # Strict validation

    success: bool
    status_code: int
    response: VerificationAPIResponse | None
    error_message: str | None
```

### Embed Placeholders

Available placeholders for mod embed templates:

| Placeholder | Description |
|-------------|-------------|
| `{username}` | Stored username from request |
| `{user_mention}` | Discord mention (`<@user_id>`) |
| `{user_display_name}` | Display name (plain text, fallback to username) |
| `{verification_type}` | Type display name |
| `{status}` | Current status text |
| `{created_at}` | Formatted date (YYYY-MM-DD HH:MM) |
| `{created_at_relative}` | Relative timestamp (`<t:UNIX:R>`) |
| `{war}` | War number from OCR |

**Note:** `format_message()` converts literal `\n` to actual newlines.

---

## Purge (Cleanup) Cog

**File:** `discord_bot/purge/cog.py`
**Class:** `PurgeCog(commands.Cog)`

### Commands

```python
/purge war <type> [options]  # Start war purge
/purge global <type>          # Start global purge
/purge cancel                  # Cancel pending purge
/purge results <purge_id>      # Show results
```

### Data Models

**File:** `discord_bot/purge/models/`

```python
class PurgeRecord(Base):
    __tablename__ = "purge_records"

    id: int (primary key)
    public_id: str(21)  # NanoID, prevents IDOR
    guild_id: int
    purge_type: str(50)  # "war", "global", etc.
    status: str(50)      # PENDING, AUTHORIZED, EXECUTED, CANCELLED

    # Initiator
    initiated_by: int

    # Message IDs (for tracking Discord messages)
    mod_channel_id, mod_message_id
    user_channel_id, user_message_id

    # Vote tracking (JSON arrays of user IDs)
    authorized_by: list[int]
    cancelled_by: list[int]
    confirmed_by: list[int]

    # Snapshot & results (JSON)
    config_snapshot: dict
    execution_result: dict (nullable)

    # Timestamps
    created_at, scheduled_for, authorized_at
    executed_at, expires_at

    # Relationship
    user_results: list[PurgeUserResult]
```

```python
class PurgeUserResult(Base):
    __tablename__ = "purge_user_results"

    id: int
    purge_id: int (FK -> PurgeRecord)
    user_id: int
    action: str  # "removed", "warned", "skipped"
    reason: str (nullable)
```

**Indexes:** `ix_purge_guild_id`, `ix_purge_status`, `ix_purge_created_at`

### State Machine

```
PENDING → AUTHORIZED → EXECUTED / CANCELLED
          (after mod votes)   (or manual cancel)
```

### Execution Engine

**File:** `discord_bot/purge/execution.py`

```python
async def execute_purge(
    guild: discord.Guild,
    purge_record: PurgeRecord,
    config: dict,
    db_service: DatabaseService
) -> dict:
    """Execute the purge on the guild. Return summary."""
```

### Configuration

Includes options for vote requirements, expiration hours, notification channels.

---

## Stockpile Cog (NEW)

**File:** `discord_bot/stockpile/cog.py`
**Class:** `StockpileCog(commands.Cog)`

### Commands

```python
/stockpile_add <hex_key> <city> <name> <code> [roles...]  # Add stockpile
/stockpile_show [role_filter]                              # List stockpiles
/stockpile_delete <stockpile_id>                           # Remove stockpile
```

### Data Models

**File:** `discord_bot/stockpile/models/stockpile.py`

```python
class Stockpile(Base):
    __tablename__ = "stockpiles"

    id: int (primary key)
    public_id: str(21)  # NanoID, prevents IDOR
    guild_id: int
    hex_key: str(50)    # Map location ID
    city: str(100)      # City name
    name: str(10)       # Stockpile name (e.g., "A", "B")
    code: str(6)        # Access code
    view_roles: list[int]  # JSON array of role IDs
    created_by: int
    created_at: datetime
```

**Indexes:** `ix_stockpile_guild_id`, `ix_stockpile_hex_city`

### Service

**File:** `discord_bot/stockpile/service.py`

```python
async def create_stockpile(...) -> Stockpile
async def get_stockpile(stockpile_id: int) -> Stockpile | None
async def get_all_by_guild(guild_id: int) -> list[Stockpile]
async def get_visible_by_guild(guild_id: int, user_role_ids: list[int]) -> list[Stockpile]
async def delete_stockpile(stockpile_id: int) -> bool
```

### Configuration Schema

**File:** `discord_bot/stockpile/config.py`

Organized into sections:
- **General:** Command channel, command names (add/show/delete)
- **Display:** Embed title, description, color, field formatting
- **Notifications:** Show all stockpiles on change, notification channel

---

## Roles Cog (NEW)

**File:** `discord_bot/roles/cog.py`
**Class:** `RolesCog(commands.Cog)`

### Commands

```python
/{prefix} create <name> <channel> <type>  # Create a new panel
/{prefix} add_role <panel> <emoji> <role>  # Add emoji-role mapping
/{prefix} remove_role <panel> <emoji>       # Remove mapping
/{prefix} post <panel>                       # Post panel to channel
/{prefix} refresh <panel>                    # Update posted panel
/{prefix} delete <panel>                     # Delete panel
/{prefix} list                               # List all panels
/{prefix} info <panel>                       # Show panel details
```

### Panel Types

| Type | Behavior |
|------|----------|
| `toggle` | React = add role, unreact = remove role |
| `exclusive` | Only one role allowed, switching removes previous |
| `verify` | One-time selection, reaction removed after role assignment |

### Data Models

**File:** `discord_bot/roles/models/reaction_panel.py`

```python
class ReactionPanel(Base):
    __tablename__ = "reaction_panels"

    id: int (primary key)
    public_id: str(21)        # NanoID, prevents IDOR
    guild_id: int
    channel_id: int
    message_id: int | None    # Set after posting
    name: str(100)
    panel_type: str(20)       # toggle, exclusive, verify

    role_mappings: list[dict] # [{emoji, emoji_id, role_id, display_name}]
    required_roles: list[int] # Role IDs required to use panel

    dm_on_missing_role: bool
    dm_on_role_change: bool
    embed_config: dict | None

    created_by: int
    created_at: datetime
```

**Indexes:** `ix_reaction_panel_guild_id`, `ix_reaction_panel_message`

### Service

**File:** `discord_bot/roles/service.py`

```python
async def create_panel(...) -> ReactionPanel
async def get_by_id(panel_id: int) -> ReactionPanel | None
async def get_by_message_id(guild_id, channel_id, message_id) -> ReactionPanel | None
async def get_all_for_guild(guild_id: int) -> list[ReactionPanel]
async def add_mapping(...) -> ReactionPanel | None
async def remove_mapping(...) -> ReactionPanel | None
async def delete(panel_id: int) -> bool
```

### Event Handlers

| Event | Handler | Purpose |
|-------|---------|---------|
| `on_raw_reaction_add` | `_handle_reaction()` | Add role on reaction |
| `on_raw_reaction_remove` | `_handle_reaction()` | Remove role on unreaction |

**User Lock Manager:** Prevents race conditions when same user clicks multiple reactions quickly.

### Configuration Schema

**File:** `discord_bot/roles/config.py`

Organized into groups:
- **General:** Command prefix (default: "roles")
- **Permissions:** Manage roles permission
- **Audit:** Audit channel, notification switches
- **Audit Messages:** Templates for panel/role change notifications
- **User DM Messages:** Missing role, role added/removed templates
- **Display:** Default panel embed template
- **Error Messages:** No permission, not found, missing required role

---

## AutoName Cog

**File:** `discord_bot/autoname/cog.py`
**Class:** `AutoNameCog(commands.Cog)`

### Events

| Event | Handler | Purpose |
|-------|---------|---------|
| `on_member_join` | `on_member_join()` | Auto-rename new members |
| `on_member_update` | `on_member_update()` | Rename if nick changes |

### Service

**File:** `discord_bot/autoname/service.py`

```python
async def apply_naming_rule(member: discord.Member, guild_id: int) -> bool:
    """Apply naming rule to a member based on guild config."""
```

### Configuration

Inherits from `Guild.prefix` model + guild config:
```python
ConfigOption(key="enabled", ...)
ConfigOption(key="name_format", ...)  # Template string
ConfigOption(key="name_match_mode", ...)  # Exact/Contains
```

---

## Shared Cog Infrastructure

### Base Cog Methods

All cogs inherit:
```python
def get_locked_options(self) -> dict[str, dict]:
    """Return options that are locked by deployment config."""
```

### View Persistence

Views registered in `cog_load()` for button interactions:

```python
async def cog_load(self):
    self.bot.add_view(VerificationPanelView())
    self.bot.add_view(ModReviewView())
```

Views persist across bot restarts (no timeout).

### Configuration Loading

```python
async def cog_load(self):
    async with self.bot.database.session() as session:
        config_service = ConfigService(session)
        config = await config_service.get_all_config(
            guild_id=guild_id,
            cog_name=self.COG_NAME
        )
```

### Health Checks

Cogs can implement periodic health checks:

```python
@tasks.loop(minutes=1)
async def health_check_loop(self):
    """Periodic validation of cog state."""
```

---

## Cog Registration & Schema

### Config Schema Service

**File:** `discord_bot/common/services/config_schema_service.py`

```python
# During bot.setup_hook():
get_config_schema_service().register_schema(VERIFICATION_CONFIG_SCHEMA)
get_config_schema_service().register_schema(PURGE_CONFIG_SCHEMA)
get_config_schema_service().register_schema(STOCKPILE_CONFIG_SCHEMA)
get_config_schema_service().register_schema(ROLES_CONFIG_SCHEMA)
get_config_schema_service().register_schema(AUTONAME_CONFIG_SCHEMA)
```

This enables:
1. Web UI auto-generation (form fields based on schema)
2. Config validation (when saving)
3. Default value lookup

---

## Error Handling in Cogs

All event handlers wrapped with error catching:

```python
@commands.Cog.listener()
async def on_member_join(self, member: discord.Member):
    try:
        # Event logic
    except Exception as e:
        logger.exception(f"[{guild.name}] Error in on_member_join: {e}")
        # Continue - don't crash bot
```

---

## Testing

**Location:** `tests/` (pytest)

Each cog can be tested in isolation:
- Mock bot, database, discord objects
- Call cog methods directly
- Verify database state and discord API calls

Example coverage targets:
- Verification: State transitions, screenshot validation, OCR integration
- Purge: Vote counting, execution logic
- Stockpile: Role-based visibility, CRUD operations
- AutoName: Name formatting rules
