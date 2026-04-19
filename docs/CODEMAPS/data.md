# Database Schema Codemap

<!-- Generated: 2026-04-10 | Files scanned: 12 | Token estimate: ~1100 -->

**Last Updated:** 2026-04-10
**Entry Point:** `discord_bot/common/models/`, Alembic migrations
**Database:** SQLite (default) | PostgreSQL (optional)

## Database Schema Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         guilds                               │
├──────────────┬──────────────┬──────────────┬─────────────────┤
│ id (PK)      │ name         │ prefix       │ created_at      │
│ invited_by_id│ updated_at   │              │                 │
└──────────┬───────────────────────────────────────────────────┘
           │ (1:N)
           ├─────────────────────────────┐
           │                             │
    ┌──────▼──────────┐        ┌────────▼────────┐
    │ guild_configs   │        │ guild_cog_      │
    ├─────────────────┤        │   enabled       │
    │ guild_id (FK)   │        ├─────────────────┤
    │ cog_name        │        │ guild_id (FK)   │
    │ key             │        │ cog_name        │
    │ value (JSON)    │        │ enabled         │
    │ created_at      │        │ created_at      │
    │ updated_at      │        └─────────────────┘
    └─────────────────┘

┌──────────────────────────────────────────────────────────────┐
│       verification_requests                                   │
├──────────────┬──────────────┬────────────────┬───────────────┤
│ id (PK)      │ public_id(U) │ guild_id (FK)  │ user_id       │
│ username     │ verification │ screenshot_1   │ screenshot_2  │
│ type         │ player_info  │ reviewed_by_id │ reviewed_by_  │
│ username     │ rejection_   │ mod_message_id │ status        │
│ reason       │ created_at   │ submitted_at   │ reviewed_at   │
└──────────────┴──────────────┴────────────────┴───────────────┘

┌──────────────────────────────────────────────────────────────┐
│          purge_records                                        │
├──────────────┬──────────────┬────────────────┬───────────────┤
│ id (PK)      │ public_id(U) │ guild_id (FK)  │ purge_type    │
│ status       │ initiated_by │ authorized_by  │ cancelled_by  │
│ confirmed_by │ config_snap  │ execution_res  │ mod_channel   │
│ mod_message  │ user_channel │ user_message   │ created_at    │
│ scheduled_   │ authorized_  │ executed_at    │ expires_at    │
│ for          │ at           │                │                │
└──────────────┴──────────────┴────────────────┴───────────────┘
           │ (1:N)
           ▼
┌──────────────────────────────────────┐
│ purge_user_results                   │
├──────────────┬──────────────────────┤
│ id (PK)      │ purge_id (FK)        │
│ user_id      │ action               │
│ reason       │                      │
└──────────────┴──────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│          stockpiles (NEW)                                     │
├──────────────┬──────────────┬────────────────┬───────────────┤
│ id (PK)      │ public_id(U) │ guild_id (FK)  │ hex_key       │
│ city         │ name         │ code           │ view_roles    │
│ created_by   │ created_at   │                │                │
└──────────────┴──────────────┴────────────────┴───────────────┘
```

---

## Table Definitions

### 1. guilds

**File:** `discord_bot/common/models/guild.py`

```python
class Guild(Base):
    __tablename__ = "guilds"
    __table_args__ = ()  # No indexes defined on this table

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str]
    prefix: Mapped[str] = mapped_column(default="!")
    invited_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
```

**Purpose:** Guild metadata (discord.Guild snapshots)
**Unique:** `id` (Discord guild ID, 64-bit)
**Usage:** Cogs reference this for guild-specific settings

---

### 2. guild_configs

**File:** `discord_bot/common/models/guild_config.py`

```python
class GuildConfig(Base):
    __tablename__ = "guild_configs"
    __table_args__ = (
        PrimaryKeyConstraint("guild_id", "cog_name", "key"),
        Index("ix_guild_config_guild_id", "guild_id"),
        Index("ix_guild_config_cog_name", "cog_name"),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger)
    cog_name: Mapped[str] = mapped_column(String(100))  # "verification", "purge", etc.
    key: Mapped[str] = mapped_column(String(100))        # "enabled", "mod_channel_id", etc.
    value: Mapped[Any] = mapped_column(JSON)             # Pydantic-validated value
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
```

**Purpose:** Key-value config storage (guild-specific settings per cog)
**Composite PK:** (guild_id, cog_name, key)
**Access:** `ConfigService.get_value()` / `set_value()`

**Example rows:**
```
(guild_id=123, cog_name='verification', key='enabled', value=true, ...)
(guild_id=123, cog_name='verification', key='mod_channel_id', value=456, ...)
(guild_id=123, cog_name='stockpile', key='command_channel', value=789, ...)
```

---

### 3. guild_cog_enabled

**File:** `discord_bot/common/models/guild_cog_enabled.py`

```python
class GuildCogEnabled(Base):
    __tablename__ = "guild_cog_enabled"
    __table_args__ = (
        PrimaryKeyConstraint("guild_id", "cog_name"),
        Index("ix_cog_enabled_guild_id", "guild_id"),
    )

    guild_id: Mapped[int] = mapped_column(BigInteger)
    cog_name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
```

**Purpose:** Toggle cogs on/off per guild
**Composite PK:** (guild_id, cog_name)

---

### 4. verification_requests

**File:** `discord_bot/verification/models/verification_request.py`

```python
class VerificationRequest(Base):
    __tablename__ = "verification_requests"
    __table_args__ = (
        Index("ix_verification_guild_id", "guild_id"),
        Index("ix_verification_user_id", "user_id"),
        Index("ix_verification_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(21), unique=True, nullable=False, default=_generate_public_id)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    verification_type: Mapped[str] = mapped_column(String(20), default="REGULAR", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING_SCREENSHOTS", nullable=False)

    # Screenshots (URLs as Text)
    screenshot_1_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_2_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # OCR Results (Pydantic model extracted data)
    player_info: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Review info
    reviewed_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reviewed_by_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    mod_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    screenshots_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

**Status Values:** `PENDING_SCREENSHOTS`, `SUBMITTED`, `PENDING_REVIEW`, `APPROVED`, `REJECTED`
**Verification Types:** `REGULAR`, `ALLY`
**Purpose:** Track user verification requests (screenshots, OCR analysis, review status)
**Access:** `VerificationService` (CRUD)
**Indexes:** `guild_id`, `user_id`, `status` (for fast queries)
**IDOR Protection:** `public_id` is NanoID (cryptographically random 21-char string)

---

### 5. purge_records

**File:** `discord_bot/purge/models/purge_record.py`

```python
class PurgeRecord(Base):
    __tablename__ = "purge_records"
    __table_args__ = (
        Index("ix_purge_guild_id", "guild_id"),
        Index("ix_purge_status", "status"),
        Index("ix_purge_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(21), unique=True)  # NanoID
    guild_id: Mapped[int] = mapped_column(BigInteger)
    purge_type: Mapped[str] = mapped_column(String(50))  # "war", "global", etc.
    status: Mapped[str] = mapped_column(String(50), default="PENDING")

    # Initiator
    initiated_by: Mapped[int] = mapped_column(BigInteger)

    # Message tracking
    mod_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    mod_message_id: Mapped[int | None] = mapped_column(BigInteger)
    user_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    user_message_id: Mapped[int | None] = mapped_column(BigInteger)

    # Voting (JSON arrays of user IDs)
    authorized_by: Mapped[list[int]] = mapped_column(JSON, default=list)
    cancelled_by: Mapped[list[int]] = mapped_column(JSON, default=list)
    confirmed_by: Mapped[list[int]] = mapped_column(JSON, default=list)

    # Config snapshot & results
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Relationship
    user_results = relationship(
        "PurgeUserResult",
        back_populates="purge",
        cascade="all, delete-orphan",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

**Status Values:** `PENDING`, `AUTHORIZED`, `EXECUTED`, `CANCELLED`
**Purpose:** Track purge operations with vote tracking and execution results
**Access:** `PurgeService` (CRUD)
**Cascade Delete:** Deleting purge_record deletes all purge_user_results
**IDOR Protection:** `public_id` is NanoID

---

### 6. purge_user_results

**File:** `discord_bot/purge/models/purge_user_result.py`

```python
class PurgeUserResult(Base):
    __tablename__ = "purge_user_results"
    __table_args__ = (
        ForeignKeyConstraint(["purge_id"], ["purge_records.id"]),
        Index("ix_purge_user_result_purge_id", "purge_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    purge_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(50))  # "removed", "warned", "skipped"
    reason: Mapped[str | None] = mapped_column(Text)

    # Relationship
    purge = relationship(
        "PurgeRecord",
        back_populates="user_results",
    )
```

**Purpose:** Detailed results per user in a purge operation
**Access:** `PurgeService` (reads for summary)
**Cascade:** Automatically deleted when parent PurgeRecord is deleted

---

### 7. stockpiles (NEW)

**File:** `discord_bot/stockpile/models/stockpile.py`

```python
class Stockpile(Base):
    __tablename__ = "stockpiles"
    __table_args__ = (
        Index("ix_stockpile_guild_id", "guild_id"),
        Index("ix_stockpile_hex_city", "guild_id", "hex_key", "city"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(21), unique=True, nullable=False, default=_generate_public_id)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hex_key: Mapped[str] = mapped_column(String(50), nullable=False)  # Map location ID
    city: Mapped[str] = mapped_column(String(100), nullable=False)    # City name
    name: Mapped[str] = mapped_column(String(10), nullable=False)     # Stockpile name (A, B, etc.)
    code: Mapped[str] = mapped_column(String(6), nullable=False)      # Access code
    view_roles: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)  # Role IDs
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
```

**Purpose:** Store stockpile locations with access codes and role-based visibility
**Key Features:**
- Role-based visibility (view_roles list; empty = visible to all)
- Compound index on `(guild_id, hex_key, city)` for location searches
- NanoID for IDOR protection
**Access:** `StockpileService` (CRUD)
**Unique:** `public_id` (NanoID)

---

### 8. reaction_panels (NEW)

**File:** `discord_bot/roles/models/reaction_panel.py`

```python
class ReactionPanel(Base):
    __tablename__ = "reaction_panels"
    __table_args__ = (
        Index("ix_reaction_panel_guild_id", "guild_id"),
        Index("ix_reaction_panel_message", "guild_id", "channel_id", "message_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(21), unique=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    panel_type: Mapped[str] = mapped_column(String(20), nullable=False)  # toggle, exclusive, verify

    role_mappings: Mapped[list[dict]] = mapped_column(JSON, default=list)  # [{emoji, emoji_id, role_id, display_name}]
    required_roles: Mapped[list[int]] = mapped_column(JSON, default=list)

    dm_on_missing_role: Mapped[bool] = mapped_column(Boolean, default=False)
    dm_on_role_change: Mapped[bool] = mapped_column(Boolean, default=False)
    embed_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

**Purpose:** Store reaction role panels with emoji-role mappings
**Panel Types:**
- `toggle`: React = add role, unreact = remove role
- `exclusive`: Only one role allowed at a time
- `verify`: One-time selection, reaction removed after role assignment
**Key Features:**
- User lock manager prevents race conditions
- Required roles for access control
- Optional DM notifications on role changes
- Compound index on `(guild_id, channel_id, message_id)` for reaction lookups
**Access:** `ReactionRolesService` (CRUD)
**IDOR Protection:** `public_id` is NanoID

---

## Migrations (Alembic)

**Location:** `/home/xurxogr/code/discord/alembic/versions/`

### Migration System

- **Tool:** Alembic
- **Config:** `/home/xurxogr/code/discord/alembic.ini`
- **Execution:** Via `bot.py:_create_tables()` during startup (runs `alembic upgrade head`)
- **Auto-generation:** `alembic revision --autogenerate -m "description"`

### Creating Migrations

```bash
# Generate migration based on model changes
alembic revision --autogenerate -m "Add new table"

# Apply migrations
alembic upgrade head

# View migration history
alembic history

# Downgrade
alembic downgrade -1
```

### Recent Migrations

- `verification_requests` table (core module)
- `purge_records` and `purge_user_results` tables
- `stockpiles` table (added 2026-03-27 or later)
- `guild_configs` and `guild_cog_enabled` tables (config system)

---

## Data Type Mappings

| SQLAlchemy Type | Python Type | Database Type | Notes |
|-----------------|-------------|---------------|-------|
| `BigInteger` | `int` | BIGINT | 64-bit (Discord IDs) |
| `String(N)` | `str` | VARCHAR(N) | Unicode strings |
| `Text` | `str` | TEXT | Unlimited strings (URLs, reasons) |
| `JSON` | `dict`, `list`, `Any` | JSON | Pydantic-serialized data |
| `DateTime(timezone=True)` | `datetime` | TIMESTAMP | UTC timezone-aware |
| `Boolean` | `bool` | BOOLEAN | Config flags |

---

## Indexing Strategy

### Performance-Critical Queries

| Index | Purpose | Used By |
|-------|---------|---------|
| `ix_verification_guild_id` | Find pending verifications | on_member_join, health checks |
| `ix_verification_user_id` | Check if user has pending request | verification flow |
| `ix_verification_status` | List by status | Mod panel queries |
| `ix_purge_guild_id` | Find purge records per guild | Purge commands |
| `ix_purge_status` | Find pending/authorized purges | Vote checking |
| `ix_stockpile_guild_id` | List all stockpiles for guild | /stockpile_show command |
| `ix_stockpile_hex_city` | Find by location | Location-based queries |

---

## Database Design Principles

### Immutability Pattern
- **Never mutate rows:** Use UPDATE with new values
- **Preserve history:** Keep timestamps and reviewer info
- **Snapshot configs:** `config_snapshot` stores exact values at execution time

### IDOR Prevention
- Use `public_id` (NanoID) instead of sequential IDs for public URLs
- Sequential `id` is internal database PK only
- Example: `/verification/abc123xyz` (public_id) not `/verification/42` (id)

### Cascade Rules
- `PurgeRecord` → auto-delete `PurgeUserResult` children
- All other FKs are soft delete compatible (nullable)

### Composite Keys
- `guild_configs`: (guild_id, cog_name, key) - enforces uniqueness
- `guild_cog_enabled`: (guild_id, cog_name) - one toggle per cog per guild
