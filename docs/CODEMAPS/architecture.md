# Architecture Codemap

**Last Updated:** 2026-03-12
**Entry Points:** `discord_bot/__main__.py`, `discord_bot/bot.py`, `discord_bot/web/app.py`
**Token Estimate:** ~1200 tokens

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
│   ├── Handles: commands, confirmations
│   ├── Service: PurgeService (purge/service.py)
│   └── Models: PurgeRecord, PurgeUserResult ORM
└── AutoNameCog (discord_bot/autoname/cog.py)
    ├── Handles: member_join, member_update
    ├── Service: AutoNameService (autoname/service.py)
    └── Models: Guild.prefix config
```

## Web Application Stack

### Middleware Chain (execution order: bottom-to-top)

```
Request → Content Size Limit → Proxy Headers → Session Mgmt
→ CSRF Protection → Rate Limiting → Security Headers → Response
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
- `GuildConfig` - Key-value pairs per cog
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

## Data Flow

### Verification Workflow (Example)

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
Post to mod-channel (with embed)
  ↓
Mod reviews + accepts/rejects
  ↓
Update status + award role
  ↓
EventBus.publish(VerificationCompleted)
```

## Service Dependencies

```
DiscordBot
├── DatabaseService
│   └── AsyncEngine (SQLAlchemy)
│       └── SQLite|PostgreSQL
├── EventBus (singleton)
│   └── Internal pub/sub
├── Settings (AppSettings)
│   └── Environment + config files
└── Cogs (loaded via _load_cogs)
    ├── VerificationService (owns VerificationRequest)
    ├── ConfigService (owns GuildConfig)
    └── PurgeService (owns PurgeRecord)

FastAPI App
├── DatabaseService (shared)
├── AppSettings (shared)
├── Jinja2Templates
├── OAuth2Client (httpx)
└── Routers
    ├── Dashboard (lists guilds, configs)
    ├── Config (CRUD guild settings)
    └── Auth (OAuth2 flow)
```

## Error Handling

### Bot Layer
- Discord events wrapped in try/except (log + continue)
- Service methods raise domain exceptions (caught by cogs)
- Event handlers have timeout protection

### Web Layer
- HTTPException handlers with HTML error pages
- Unhandled exceptions → 500 (logged, generic response)
- Invalid CSRF → 403 Forbidden
- Rate limit exceeded → 429 Too Many Requests

## Deployment Model

### Single Process (Default)
- asyncio.TaskGroup spawns both bot and web server
- Shared DatabaseService (connection pool)
- Runs on port 8000 (configurable)

### Docker
- Image: Python 3.12 slim base
- CMD: `python -m discord_bot`
- Health check: GET /health

### Environment
- Box: WSL2 Linux (6.6.87 kernel)
- Database: Default SQLite in `data/bot.db`
- Config: From env vars, JSON, or CLI args
