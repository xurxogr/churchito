# Discord Bot Cogs Codemap

**Last Updated:** 2026-03-12
**Entry Point:** `discord_bot/bot.py:_load_cogs()`
**Token Estimate:** ~1100 tokens

## Cog Loading System

```python
# discord_bot/bot.py:_load_cogs()
cogs_to_load = [
    "discord_bot.verification.cog",
    "discord_bot.autoname.cog",
    "discord_bot.purge.cog",
]
for cog_module in cogs_to_load:
    await self.load_extension(cog_module)
```

Each cog is a `commands.Cog` subclass that:
1. Handles Discord events (on_member_join, on_message, etc.)
2. Registers commands and application commands
3. Manages persistent views (button interactions)
4. Delegates business logic to Service classes

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

**Model file:** `discord_bot/verification/models/verification_request.py`

```python
class VerificationRequest(Base):
    __tablename__ = "verification_requests"

    # Primary key
    id: int  # autoincrement
    public_id: str(21)  # NanoID, previene IDOR

    # Guild & user info
    guild_id: BigInteger
    user_id: BigInteger
    username: str(100)
    verification_type: str(20)  # "REGULAR", "ALLY", etc.

    # Screenshots
    screenshot_1_url: str (nullable)
    screenshot_2_url: str (nullable)

    # OCR results (JSON)
    player_info: dict (nullable)  # {name, level, faction, ...}

    # Review info
    reviewed_by_id: BigInteger (nullable)
    reviewed_by_username: str (nullable)
    rejection_reason: str (nullable)
    mod_message_id: BigInteger (nullable)

    # Status
    status: str(30)  # PENDING_SCREENSHOTS, SUBMITTED, PENDING_REVIEW, APPROVED, REJECTED

    # Timestamps
    created_at: DateTime
    screenshots_submitted_at: DateTime (nullable)
    reviewed_at: DateTime (nullable)
```

**Indexes:** `ix_verification_guild_id`, `ix_verification_user_id`, `ix_verification_status`

### Service

**File:** `discord_bot/verification/service.py`
**Class:** `VerificationService`

Key methods:
```python
async def create_request(guild_id, user_id, username, ...) -> VerificationRequest
async def get_request(request_id) -> VerificationRequest | None
async def get_pending_by_user(guild_id, user_id) -> VerificationRequest | None
async def get_all_pending_screenshots() -> list[VerificationRequest]
async def update_screenshots(request_id, urls) -> bool
async def update_status(request_id, status) -> bool
async def approve(request_id, reviewed_by_id, reviewed_by_username) -> bool
async def reject(request_id, rejection_reason, reviewed_by_id) -> bool
```

### Configuration Schema

**File:** `discord_bot/verification/config.py`

```python
VERIFICATION_CONFIG_SCHEMA = CogConfigSchema(
    cog_name="verification",
    display_name="Verification",
    options=[
        ConfigOption(key="enabled", ...),
        ConfigOption(key="mod_channel_id", ...),
        ConfigOption(key="verification_role_id", ...),
        ConfigOption(key="screenshot_timeout_minutes", ...),
        # ... 10+ more options
    ]
)
```

### Event Bus

Publishes:
- `VerificationCompleted` - After approval
- `VerificationRejected` - After rejection

### Handlers (Support Logic)

**File:** `discord_bot/verification/handlers/`

- `flow.py` - Start verification, send instructions
- `auto_processing.py` - OCR integration (if enabled)
- `mod_messages.py` - Update mod channel messages
- `utils.py` - Helper functions

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
    public_id: str(21)  # NanoID, previene IDOR
    guild_id: BigInteger
    purge_type: str(50)  # "war", "global", etc.
    status: str(50)      # PENDING, AUTHORIZED, EXECUTED, CANCELLED

    # Initiator
    initiated_by: BigInteger

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
    user_id: BigInteger
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

**File:** `discord_bot/purge/config.py`

```python
PURGE_CONFIG_SCHEMA = CogConfigSchema(
    cog_name="purge",
    options=[
        ConfigOption(key="enabled", ...),
        ConfigOption(key="min_votes_to_authorize", ...),
        ConfigOption(key="purge_expiration_hours", ...),
        # ... more options
    ]
)
```

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
**Class:** `AutoNameService`

```python
async def apply_naming_rule(member, guild_id) -> bool:
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
async def on_member_join(self, member):
    try:
        # Event logic
    except Exception as e:
        logger.exception(f"[{guild.name}] Error in on_member_join: {e}")
        # Continue - don't crash bot
```

---

## Testing Cogs

**Location:** `tests/` (pytest)

Each cog can be tested in isolation:
```python
# Mock bot, database, discord objects
# Call cog methods directly
# Verify database state and discord API calls
```

Example coverage targets:
- Verification: State transitions, screenshot validation
- Purge: Vote counting, execution logic
- AutoName: Name formatting rules
