# Database Schema Codemap

**Last Updated:** 2026-03-12
**Entry Point:** `discord_bot/common/models/`, Alembic migrations
**Database:** SQLite (default) | PostgreSQL (optional)
**Token Estimate:** ~900 tokens

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

┌──────────────────────────────────────────────┐
│       verification_requests                   │
├──────────────┬──────────────┬────────────────┤
│ id (PK)      │ public_id(U) │ guild_id (FK)  │
│ user_id      │ username     │ verification   │
│ type         │ screenshot_1 │ screenshot_2   │
│ player_info  │ reviewed_by  │ rejection      │
│ reason       │ mod_message  │ status         │
│ created_at   │ submitted_at │ reviewed_at    │
└──────────────┴──────────────┴────────────────┘

┌──────────────────────────────────────────────┐
│          purge_records                        │
├──────────────┬──────────────┬────────────────┤
│ id (PK)      │ public_id(U) │ guild_id (FK)  │
│ purge_type   │ status       │ initiated_by   │
│ authorized_by│ cancelled_by │ confirmed_by   │
│ config_snap  │ execution    │ mod_channel    │
│ mod_message  │ scheduled_for│ authorized_at  │
│ created_at   │ executed_at  │ expires_at     │
└──────────────┴──────────────┴────────────────┘
           │ (1:N)
           ▼
    ┌──────────────────┐
    │ purge_user_      │
    │   results        │
    ├──────────────────┤
    │ id (PK)          │
    │ purge_id (FK)    │
    │ user_id          │
    │ action           │
    │ reason           │
    └──────────────────┘
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
(guild_id=123, cog_name='purge', key='min_votes', value=3, ...)
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
    public_id: Mapped[str] = mapped_column(String(21), unique=True)  # NanoID, previene IDOR
    guild_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    username: Mapped[str] = mapped_column(String(100))
    verification_type: Mapped[str] = mapped_column(String(20), default="REGULAR")
    status: Mapped[str] = mapped_column(String(30), default="PENDING_SCREENSHOTS")

    # Screenshots
    screenshot_1_url: Mapped[str | None] = mapped_column(Text)
    screenshot_2_url: Mapped[str | None] = mapped_column(Text)

    # OCR Results
    player_info: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Review
    reviewed_by_id: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_by_username: Mapped[str | None] = mapped_column(String(100))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    mod_message_id: Mapped[int | None] = mapped_column(BigInteger)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    screenshots_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

**Purpose:** Track user verification requests (screenshots, OCR, review status)
**Status Values:** `PENDING_SCREENSHOTS`, `SUBMITTED`, `PENDING_REVIEW`, `APPROVED`, `REJECTED`
**Access:** `VerificationService` (CRUD)
**Indexes:** `guild_id`, `user_id`, `status` (for fast queries)

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
    public_id: Mapped[str] = mapped_column(String(21), unique=True)  # NanoID, previene IDOR
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
**Purpose:** Track purge operations and votes
**Access:** `PurgeService` (CRUD)
**Cascade Delete:** Deleting purge_record deletes all purge_user_results

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

---

## Migrations (Alembic)

**Location:** `/home/xurxogr/code/discord/alembic/versions/`

### Migration System

- **Tool:** Alembic
- **Config:** `/home/xurxogr/code/discord/alembic.ini`
- **Execution:** Via `bot.py:_create_tables()` during startup (runs `alembic upgrade head`)

### Creating Migrations

```bash
alembic revision --autogenerate -m "Add new table"
alembic upgrade head
```

---

## Service Layer Access

### DatabaseService

**File:** `discord_bot/common/services/database.py`

```python
async def session(self) -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions."""
    async with self.session_maker() as session:
        yield session
```

Usage:
```python
async with db_service.session() as session:
    service = VerificationService(session)
    request = await service.create_request(...)
    await session.commit()
```

### ConfigService

**File:** `discord_bot/common/services/config_service.py`

```python
async def get_value(guild_id: int, cog_name: str, key: str) -> Any
async def set_value(guild_id: int, cog_name: str, key: str, value: Any) -> tuple[bool, str | None]
async def get_all_config(guild_id: int, cog_name: str) -> dict[str, Any]
async def delete_value(guild_id: int, cog_name: str, key: str) -> bool
```

### VerificationService

```python
async def create_request(...) -> VerificationRequest
async def get_request(request_id) -> VerificationRequest | None
async def get_pending_by_user(guild_id, user_id) -> VerificationRequest | None
async def get_all_pending_screenshots() -> list[VerificationRequest]
async def update_status(request_id, status) -> bool
async def approve(request_id, reviewed_by_id, ...) -> bool
async def reject(request_id, rejection_reason, ...) -> bool
```

### PurgeService

```python
async def create_record(guild_id, purge_type, initiated_by) -> PurgeRecord
async def get_record(record_id) -> PurgeRecord | None
async def update_status(record_id, status) -> bool
async def add_authorization(record_id, user_id) -> bool
async def add_confirmation(record_id, user_id) -> bool
async def save_execution_result(record_id, result_dict) -> bool
```

---

## Performance Tuning

### Indexes

All high-query tables have indexes:
- `verification_requests`: guild_id, user_id, status
- `purge_records`: guild_id, status, created_at
- `guild_configs`: guild_id, cog_name
- `guild_cog_enabled`: guild_id

### Query Patterns

Most queries use indexed columns:
```python
# Fast: indexed on guild_id, user_id, status
result = await session.execute(
    select(VerificationRequest).where(
        VerificationRequest.guild_id == guild_id,
        VerificationRequest.user_id == user_id,
        VerificationRequest.status == "PENDING_SCREENSHOTS"
    )
)
```

### JSON Columns

- `guild_config.value` - Stored as JSON, validated by Pydantic
- `purge_record.config_snapshot` - Snapshot of config at purge creation
- `purge_record.execution_result` - Summary of purge results
- `purge_record.authorized_by` - Array of user IDs
- `verification_request.player_info` - OCR extracted data

---

## Connection Configuration

### SQLite (Default)

```
sqlite+aiosqlite:///data/bot.db
```

Driver: `aiosqlite` (async SQLite)
Retry logic: WAL mode + retry on locked databases

### PostgreSQL (Optional)

```
postgresql+asyncpg://user:password@localhost/dbname
```

Driver: `asyncpg` (async PostgreSQL)
Connection pool: auto-managed by SQLAlchemy

### Async Engine Settings

```python
engine = create_async_engine(
    url,
    echo=False,  # Set to True to see SQL logs
    pool_pre_ping=True,  # Verify connections before use
    pool_size=5,
    max_overflow=10,
)
```

---

## Backup & Recovery

**Backup location:** `/home/xurxogr/code/discord/data/bot.db` (SQLite)

For production PostgreSQL, use standard pg_dump tools.
