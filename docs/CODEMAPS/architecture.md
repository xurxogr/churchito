# Architecture Codemap

<!-- Generated: 2026-04-24 | Files scanned: 48 | Token estimate: ~1300 -->

**Last Updated:** 2026-04-24
**Entry Points:** `discord_bot/__main__.py`, `discord_bot/bot.py`, `discord_bot/web/app.py`

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    asyncio.TaskGroup (main)                  │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┴─────────────┐
        │                          │
        ▼                          ▼
   ┌─────────────┐         ┌──────────────┐
   │ Discord Bot │         │ FastAPI Web  │
   │ (discord.py)│         │   (uvicorn)  │
   └──────┬──────┘         └──────┬───────┘
          │                       │
    ┌─────▼──────────┐      ┌────▼────────┐
    │  Gateway API   │      │  HTTP/HTTPS │
    │ (WebSocket)    │      │   (port 8000)
    └─────┬──────────┘      └────┬────────┘
          │                       │
    ┌─────▼──────────────────────▼────┐
    │   SQLAlchemy AsyncSession (Pool) │
    │    (SQLite | PostgreSQL)         │
    └─────────────┬────────────────────┘
                  │
    ┌─────────────▼───────────────┐
    │ Database (SQLite|PostgreSQL)│
    │  - Guilds                    │
    │  - Verification Requests     │
    │  - Purge Records             │
    │  - Stockpiles (NEW)          │
    │  - Guild Configs             │
    └──────────────────────────────┘
```

## Service Layer Architecture

### Core Components

| Component | Module | Responsibility |
|-----------|--------|-----------------|
| **DiscordBot** | `discord_bot/bot.py` | Bot initialization, cog loading, event loop management |
| **DatabaseService** | `discord_bot/common/services/database.py` | AsyncSession pool, migration execution |
| **ConfigService** | `discord_bot/common/services/config_service.py` | Guild config CRUD (database-backed) |
| **EventBus** | `discord_bot/common/services/event_bus.py` | Pub/sub for inter-service communication |
| **AppSettings** | `discord_bot/common/core/app_settings.py` | Config validation (env vars, JSON files) |

### Cog System (Pluggable Modules)

```
DiscordBot (base)
├── VerificationCog (discord_bot/verification/cog.py)
│   ├── Handles: member_join, message_events, button interactions
│   ├── Service: VerificationService (verification/service.py)
│   └── Models: VerificationRequest ORM
├── PurgeCog (discord_bot/purge/cog.py)
│   ├── Handles: commands, confirmations, voting
│   ├── Service: PurgeService (purge/service.py)
│   └── Models: PurgeRecord, PurgeUserResult ORM
├── StockpileCog (discord_bot/stockpile/cog.py) [NEW]
│   ├── Handles: commands (add, show, delete)
│   ├── Service: StockpileService (stockpile/service.py)
│   └── Models: Stockpile ORM
└── AutoNameCog (discord_bot/autoname/cog.py)
    ├── Handles: member_join, member_update
    ├── Service: AutoNameService (autoname/service.py)
    └── Models: Guild.prefix config
```

## Web Application Stack

### Middleware Chain (execution order: outer to inner)

```
Request
  ↓
Content-Size Limit (reject oversized uploads)
  ↓
Proxy Headers (X-Forwarded-* support)
  ↓
Session Management (Starlette SessionMiddleware)
  ↓
CSRF Protection (validate token in POST/PUT/DELETE)
  ↓
Rate Limiting (in-memory limiter, per-IP)
  ↓
Security Headers (CSP, X-Frame-Options, etc.)
  ↓
Routing (FastAPI app)
  ↓
Response
```

Middleware files:
- `discord_bot/web/middleware/content_size.py` - Reject oversized requests
- `discord_bot/web/middleware/csrf.py` - CSRF token validation
- `discord_bot/web/middleware/rate_limit.py` - In-memory rate limiter
- `discord_bot/web/middleware/security_headers.py` - CSP, X-Frame-Options headers

### Authentication Flow

```
User visits /login
  ↓ (Redirect to Discord OAuth)
Discord oauth2/authorize?client_id=...
  ↓ (User approves, gets redirected)
GET /auth/callback?code=...&state=...
  ↓ (Exchange code for token)
Discord oauth2/token
  ↓ (Fetch user profile)
GET /api/users/@me
  ↓ (Store in session)
Session["discord_user"] = {id, username, avatar}
  ↓ (Redirect to /dashboard)
Authenticated dashboard view
```

OAuth endpoints: `discord_bot/web/auth/oauth.py`
- `GET /auth/login` - Initiate OAuth flow
- `GET /auth/callback` - Handle OAuth callback
- `GET /auth/logout` - Clear session

### Web Routes

| Path | Module | Handler | Auth |
|------|--------|---------|------|
| `/` | `routers/dashboard.py` | Index (redirects to /login or /dashboard) | None |
| `/login` | `routers/dashboard.py` | Login page (OAuth link) | None |
| `/dashboard` | `routers/dashboard.py` | Guild list + status | Required |
| `/dashboard/{guild_id}/config` | `routers/config.py` | Configuration UI | Required |
| `/api/guilds` | `routers/dashboard.py` | JSON: user's guilds | Required |
| `/api/config/{guild_id}` | `routers/config.py` | JSON: guild config | Required |
| `/auth/login` | `auth/oauth.py` | Start OAuth | None |
| `/auth/callback` | `auth/oauth.py` | OAuth callback | CSRF + state |
| `/health` | `web/app.py` | Health check | None |

## Configuration System

### Settings Hierarchy

```
AppSettings (discord_bot/common/core/app_settings.py)
├── Bot
│   ├── token (env: BOT__TOKEN)
│   ├── command_prefix (env: BOT__COMMAND_PREFIX)
│   └── owner_id (env: BOT__OWNER_ID)
├── Database
│   ├── url (env: DATABASE__URL)
│   └── echo (env: DATABASE__ECHO)
├── Web
│   ├── enabled (env: WEB__ENABLED)
│   ├── host, port
│   ├── client_id, client_secret
│   ├── secret_key (for sessions)
│   └── https_only, rate_limit_enabled
└── Logging
    ├── log_level (env: LOGGING__LOG_LEVEL)
    └── log_file (env: LOGGING__LOG_FILE)
```

**Config file location:** `~/.config/discord-bot/config.json`

### Guild Configuration (Database-Backed)

Models: `discord_bot/common/models/`
- `GuildConfig` - Key-value pairs per cog (supports sections in schema)
- `GuildCogEnabled` - Cog enable/disable per guild
- `Guild` - Guild metadata (name, prefix, created_at)

Example:
```python
# Get verification config for a guild
config_service = ConfigService(session)
timeout = await config_service.get_value(
    guild_id=12345,
    cog_name="verification",
    key="screenshot_timeout_minutes"
)
```

## Data Flow Examples

### Verification Workflow

```
Member joins guild
  ↓
on_member_join event (VerificationCog)
  ↓
Load guild config (ConfigService)
  ↓
Create VerificationRequest (VerificationService)
  ↓
Send DM with instructions
  ↓
Member uploads screenshots (on_message handler)
  ↓
Update VerificationRequest model
  ↓
Post to mod-channel (with embed, preserving existing data)
  ↓
Mod reviews + accepts/rejects
  ↓
Update status + award role
  ↓
EventBus.publish(VerificationCompleted)
```

### Stockpile Management (NEW)

```
User runs /stockpile_add
  ↓
VerifyCommand permissions (admin/configured)
  ↓
StockpileService.create_stockpile()
  ↓
Insert into stockpiles table
  ↓
Format response embed
  ↓
Post confirmation message

User runs /stockpile_show
  ↓
Load guild stockpiles
  ↓
Filter by user's visible roles
  ↓
Format into embed with role-based fields
  ↓
Display to user
```

### Web Configuration Edit Flow

```
User visits /dashboard/{guild_id}/config
  ↓
Route handler loads config schema + current values
  ↓
Render Jinja2 template with form fields
  ↓
User submits form
  ↓
CSRF middleware validates token
  ↓
Config route validates input (Pydantic schemas)
  ↓
ConfigService updates guild_configs
  ↓
Reload config in memory
  ↓
Cogs notified of config change (if using EventBus)
```

## Service Dependencies

```
DiscordBot
├── DatabaseService
│   └── AsyncEngine (SQLAlchemy)
│       └── SQLite|PostgreSQL
├── EventBus (singleton)
│   └── Internal pub/sub for events
├── Settings (AppSettings)
│   └── Environment + config files
└── Cogs (loaded via _load_cogs)
    ├── VerificationService (owns VerificationRequest)
    ├── PurgeService (owns PurgeRecord, PurgeUserResult)
    ├── StockpileService (owns Stockpile)
    ├── AutoNameService (owns Guild.prefix)
    └── ConfigService (owns GuildConfig)

FastAPI App
├── DatabaseService (shared with bot)
├── AppSettings (shared with bot)
├── Jinja2Templates
├── OAuth2Client (httpx)
└── Routers
    ├── Dashboard (lists guilds, configs)
    ├── Config (CRUD guild settings, validates with schemas)
    └── Auth (OAuth2 flow)
```

## Error Handling

### Bot Layer
- Discord events wrapped in try/except (log + continue)
- Service methods raise domain exceptions (caught by cogs)
- Event handlers have timeout protection
- Health checks monitor cog state periodically

### Web Layer
- HTTPException handlers with HTML error pages
- Unhandled exceptions → 500 (logged, generic response)
- Invalid CSRF → 403 Forbidden
- Rate limit exceeded → 429 Too Many Requests
- Auth failures → 401 Unauthorized (redirects to /login)

### Database Layer
- AsyncSession connection pooling prevents exhaustion
- Transaction rollback on service errors
- Migrations run automatically on startup (Alembic)

## Deployment Model

### Single Process (Default)
- `asyncio.TaskGroup` spawns both bot and web server
- Shared `DatabaseService` (connection pool)
- Shared `AppSettings` and `EventBus`
- Runs on port 8000 (configurable)

### Docker
- Image: Python 3.12 slim base
- CMD: `python -m discord_bot`
- Health check: `GET /health` (returns 200)
- Graceful shutdown (SIGTERM handling)

### Environment
- Box: WSL2 Linux (kernel 6.6.87+)
- Database: Default SQLite in `data/bot.db`
- Config: From env vars, JSON, or CLI args

## State Management

### In-Memory Cog State
- `VerificationCog._pending_dm_verifications` - tracks active verification flows
- `VerificationCog._screenshot_timers` - asyncio tasks for timeouts
- `PurgeCog` - state tracked in database, not memory

### Database State
- All persistent state in database (guild configs, verification requests, purges, stockpiles)
- Enables multi-instance deployments (future)
- Health checks restore state on bot startup

### Session State (Web)
- Session data stored server-side via SessionMiddleware
- `discord_user` object cached in session (avoids repeated OAuth calls)
- Configurable timeout (default: 1 week)

## Recent Architectural Changes

### Stockpile Cog Integration (2026-03-27+)
- New cog added to bot.py's cog loading list
- Shares same infrastructure: ConfigService, database models, config schema
- Config options organized into sections (General, Display, Notifications)

### Verification Improvements
- Mod message updates now preserve existing embed data (instead of rebuilding)
- Regiment comparison refactored to use IDs (prevents OCR false negatives)
- Panel recreation guarded by cog enabled state

### Configuration Schema Evolution
- Config options now support `group` field (for UI organization)
- Web UI renders grouped options as collapsible sections
- Backward compatible with existing configs
