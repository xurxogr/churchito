# External Dependencies & Integrations Codemap

<!-- Generated: 2026-04-24 | Files scanned: 42 | Token estimate: ~950 -->

**Last Updated:** 2026-04-24
**Location:** `discord_bot/` (all modules)

## Runtime Dependencies

### Bot Framework

| Package | Version | Use | Module |
|---------|---------|-----|--------|
| **discord.py** | 2.x | Discord bot framework | `bot.py`, all cogs |
| **python-dotenv** | latest | Load .env files | `common/core/app_settings.py` |
| **pydantic** | 2.x | Config validation | All settings |
| **nanoid** | 2.x | ID generation (IDOR prevention) | Models (public_id) |

### Web Framework

| Package | Version | Use | Module |
|---------|---------|-----|--------|
| **fastapi** | latest | ASGI web framework | `web/app.py` |
| **uvicorn** | latest | ASGI server | `web/app.py`, `__main__.py` |
| **starlette** | (via fastapi) | Middleware base | `web/middleware/` |
| **jinja2** | latest | Template rendering | `web/templates/` |
| **python-multipart** | latest | Form parsing | `web/routers/` |
| **httpx** | latest | Async HTTP client | `web/auth/oauth.py` |

### Database

| Package | Version | Use | Module |
|---------|---------|-----|--------|
| **sqlalchemy** | 2.0+ | Async ORM | `common/models/`, services |
| **aiosqlite** | latest | SQLite async driver | `common/services/database.py` |
| **asyncpg** | latest | PostgreSQL async driver (optional) | `common/services/database.py` |
| **alembic** | latest | Schema migrations | `alembic/` directory |

### Development & Testing

| Package | Version | Use | Context |
|---------|---------|-----|---------|
| **pytest** | latest | Unit & integration tests | `tests/` |
| **pytest-asyncio** | latest | Async test support | `tests/` |
| **pytest-cov** | latest | Coverage reporting | CI/CD |
| **mypy** | latest | Type checking | CI/CD |
| **ruff** | latest | Linting & formatting | CI/CD |
| **black** | (via ruff) | Code formatting | CI/CD |
| **pre-commit** | latest | Git hooks | `.pre-commit-config.yaml` |

---

## External APIs & Services

### Discord API

**Provider:** Discord Inc.
**Endpoint:** `https://discord.com/api/v10`
**Authentication:** Bot token (env: `BOT__TOKEN`)

#### Bot Gateway

- **WebSocket:** `wss://gateway.discord.gg/`
- **Purpose:** Real-time events (member join, message, etc.)
- **Framework:** discord.py handles connection, reconnection, heartbeat

#### OAuth2 (Web Auth)

**Endpoints:**
- **Authorize:** `https://discord.com/api/oauth2/authorize`
  - Params: `client_id`, `redirect_uri`, `scope=identify`, `state`
  - Returns: Authorization code (if user approves)
- **Token Exchange:** `https://discord.com/api/oauth2/token`
  - Method: POST with `client_id`, `client_secret`, `code`
  - Returns: `access_token`, `refresh_token`, `expires_in`
- **User Profile:** `https://discord.com/api/v10/users/@me`
  - Headers: `Authorization: Bearer {access_token}`
  - Returns: User ID, username, avatar hash, etc.

**Configuration:**
```env
WEB__CLIENT_ID=your-app-id
WEB__CLIENT_SECRET=your-secret
WEB__REDIRECT_URI=http://localhost:8000/auth/callback
```

**Flow File:** `discord_bot/web/auth/oauth.py`

**How it's used:**
1. User clicks "Login with Discord" on `/login`
2. Redirects to Discord OAuth authorize endpoint
3. User approves in Discord client
4. Discord redirects to `/auth/callback?code=...&state=...`
5. Bot exchanges code for access token
6. Bot fetches user profile with access token
7. User session created, redirects to `/dashboard`

#### Rate Limits

- OAuth: No per-request limit (burst + per-minute)
- REST: 50 requests/second (bucket-based)
- Gateway: Connection limit + identify rate limit (1 per 5 seconds)

#### Intents Required

```python
intents = discord.Intents.default()
intents.message_content = True  # Read DM/channel messages
intents.members = True          # Member add/update/remove events
```

Must be enabled in Discord Developer Portal.

### OCR Service (Optional)

**Purpose:** Auto-detect player info from screenshots (verification cog)
**Status:** Optional - manual verification works without OCR

**Configuration:**
```env
VERIFICATION__API_URL=https://ocr-service.example.com
VERIFICATION__API_KEY=your-api-key
VERIFICATION__API_TIMEOUT=30
```

**Usage File:** `discord_bot/verification/auto_processor.py`

**Request:**
```
POST {API_URL}/verify
Headers: Authorization: Bearer {API_KEY}, Content-Type: application/json
Body: {
  "screenshot_urls": ["url1", "url2"],
  "game_name": "game-name"
}
```

**Response (parsed into VerificationAPIResponse):**
```json
{
  "name": "PlayerName",
  "level": 50,
  "regiment": "Regiment Name",
  "faction": "colonial",
  "shard": "ABLE",
  "ingame_time": "268, 07:41",
  "war": 130,
  "current_ingame_time": "278, 08:34"
}
```

**Pydantic Models:** `discord_bot/verification/models/api_response.py`
- `VerificationAPIResponse` - Parsed player data
- `VerificationAPIResult` - Wrapper with success/error info

**Integration Points:**
- Called when verification screenshots submitted
- Results stored in `VerificationRequest.player_info` (JSON)
- Auto-accept/reject based on config if enabled
- Falls back to manual review if API unavailable

**If not configured:** Manual verification mode only

---

## Database Backends

### SQLite (Default)

**URL:** `sqlite+aiosqlite:///data/bot.db`
**Location:** `/home/xurxogr/code/discord/data/bot.db`
**Async Driver:** `aiosqlite`

**Connection Logic:**
```python
# discord_bot/common/services/database.py:_ensure_database_directory()
# Creates data/ directory if missing
```

**WAL Mode (async writes):**
```python
@event.listens_for(AsyncEngine, "connect")
async def set_sqlite_pragma(conn):
    await conn.execute(text("PRAGMA journal_mode=WAL"))
```

**Advantages:**
- Zero-config, single file
- Good for development & small deployments
- SQLAlchemy handles async I/O

**Limitations:**
- Single-writer (locks on writes)
- Not suitable for high-concurrency production
- WAL mode helps but still limited

### PostgreSQL (Optional)

**URL:** `postgresql+asyncpg://user:pass@localhost/dbname`
**Driver:** `asyncpg` (installed as optional dependency)
**Recommended for:** Production deployments

**Configuration:**
```env
DATABASE__URL=postgresql+asyncpg://user:password@localhost:5432/discord_bot
```

**Advantages:**
- Multi-writer support (true concurrency)
- Better for scaling
- JSONB support for configs

**Requirements:**
- PostgreSQL server running
- `asyncpg` pip package installed
- Database created manually

---

## Configuration Files

### .env File

**Location:** `/home/xurxogr/code/discord/.env` (git-ignored)
**Example:** `/home/xurxogr/code/discord/.env.example`

**Key Variables:**
```env
# Bot
BOT__TOKEN=your-discord-bot-token
BOT__COMMAND_PREFIX=!
BOT__OWNER_ID=123456789

# Database
DATABASE__URL=sqlite+aiosqlite:///./data/bot.db

# Web
WEB__ENABLED=true
WEB__HOST=0.0.0.0
WEB__PORT=8000
WEB__CLIENT_ID=your-discord-app-id
WEB__CLIENT_SECRET=your-discord-app-secret
WEB__REDIRECT_URI=http://localhost:8000/auth/callback
WEB__SECRET_KEY=your-session-secret
WEB__HTTPS_ONLY=false

# Logging
LOGGING__LOG_LEVEL=INFO
LOGGING__LOG_FILE=logs/bot.log

# Verification (optional)
VERIFICATION__API_URL=https://ocr-service.example.com
VERIFICATION__API_KEY=your-ocr-key
```

### JSON Config File

**Location:** `~/.config/discord-bot/config.json`
**Format:** Pydantic v2 compatible

Example:
```json
{
  "bot": {
    "token": "your-token",
    "command_prefix": "!",
    "owner_id": 123456789
  },
  "database": {
    "url": "sqlite+aiosqlite:///./data/bot.db"
  },
  "web": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8000,
    "client_id": "your-id",
    "client_secret": "your-secret"
  }
}
```

**Priority:** Env vars override JSON file, JSON file overrides defaults

---

## File Upload & Storage

### Screenshot URLs

**Current Implementation:**
- Screenshots stored in Discord CDN (user uploads)
- URLs stored in `VerificationRequest.screenshot_1_url`, `screenshot_2_url`
- URLs validated on submission to prevent injection

**URL Validation:**
- Must start with `https://cdn.discordapp.com/` or `https://media.discordapp.net/`
- Prevents URL injection attacks

### Stockpile Data

- Stored entirely in database (Stockpile model)
- No file uploads
- Role lists stored as JSON array

### Config Data

- Guild-specific config stored in database (GuildConfig table)
- Serialized as JSON for complex types
- Validated with Pydantic schemas on read/write

---

## Deployment Integrations

### Docker

**Image:** Python 3.12 slim base
**Dockerfile:** `/home/xurxogr/code/discord/Dockerfile`

**Entrypoint:**
```bash
python -m discord_bot
```

**Environment Variables:** Passed via:
- `.env` file (for compose)
- Docker environment (container run)
- Kubernetes ConfigMaps/Secrets (if applicable)

**Compose File:** `docker-compose.yml`

**Health Check:**
```bash
curl http://localhost:8000/health
```

### Migrations

**Tool:** Alembic
**Location:** `/home/xurxogr/code/discord/alembic/versions/`

**Automatic Execution:**
```python
# discord_bot/bot.py:_create_tables()
# Runs during bot startup: alembic upgrade head
```

**Manual Execution:**
```bash
alembic revision --autogenerate -m "Add new table"
alembic upgrade head
```

---

## Security Integrations

### Rate Limiting

**Implementation:** In-memory token bucket (web layer)
**Location:** `discord_bot/web/middleware/rate_limit.py`

**Per-IP Limits:**
- 100 requests/minute (default)
- Whitelist: localhost (127.0.0.1, ::1) never rate-limited

**Not Suitable For:** Multi-worker deployments (no shared state)

### CSRF Protection

**Implementation:** Token in session + form field
**Location:** `discord_bot/web/middleware/csrf.py`

**Protected Methods:** POST, PUT, DELETE
**Safe Methods:** GET, HEAD, OPTIONS (no CSRF required)

**Token Generation:**
```python
# Form includes hidden field: <input name="csrf_token" value="...">
# Session stores matching token
# Middleware validates on each request
```

### Session Security

**Cookie:** `bot_session`
**Attributes:**
- Secure: true (HTTPS only, unless dev mode)
- HttpOnly: true (no JavaScript access)
- SameSite: Lax (CSRF protection)
- Max-Age: 30 days (default)

---

## Monitoring & Observability

### Health Check Endpoint

**Path:** `GET /health`
**Status Code:** 200 (always, minimal check)
**Response:**
```json
{
  "status": "ok",
  "timestamp": "2026-04-10T12:00:00Z",
  "version": "1.1.0"
}
```

**Used By:** Docker health checks, load balancers

### Logging

**Framework:** Python logging
**Configuration:** `discord_bot/common/core/logging.py`

**Log Levels:**
- DEBUG: Detailed info (cog operations, DB queries if echo=true)
- INFO: Important events (bot ready, config loaded)
- WARNING: Recoverable issues (failed verification, timeout)
- ERROR: Errors caught and handled (API failures)
- CRITICAL: Unrecoverable issues (bot crash)

**Output:**
- Console (stdout/stderr)
- File (if configured): `logs/bot.log`

### Metrics

**Planned:** Prometheus metrics (not yet implemented)
**Current:** Log-based only

---

## Third-Party Integrations (Future)

### Potential Additions

- **Prometheus:** Metrics export
- **Sentry:** Error tracking
- **DataDog:** Distributed tracing
- **AWS S3:** Screenshot storage (instead of Discord CDN)
- **Slack Notifications:** Alerting

---

## Recent Changes

### Dependencies Added (2026-03-27+)
- Stockpile cog: No new external dependencies
- Uses existing: SQLAlchemy, Pydantic, discord.py, FastAPI

### Configuration Schema Updates
- Support for `group` field in config options
- Web UI renders sections from groups
- Affects: verification, purge, stockpile, autoname configs

### Security Improvements
- NanoID for all public-facing IDs (prevents IDOR)
- URL validation on screenshot upload
- CSRF token in all POST/PUT/DELETE requests
