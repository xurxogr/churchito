# External Dependencies & Integrations Codemap

**Last Updated:** 2026-03-12
**Location:** `discord_bot/` (all modules)
**Token Estimate:** ~800 tokens

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
- **Framework:** discord.py handles connection

#### OAuth2 (Web Auth)

**Endpoints:**
- **Authorize:** `https://discord.com/api/oauth2/authorize`
  - Params: `client_id`, `redirect_uri`, `scope=identify`, `state`
- **Token Exchange:** `https://discord.com/api/oauth2/token`
  - Method: POST with `client_id`, `client_secret`, `code`
- **User Profile:** `https://discord.com/api/v10/users/@me`
  - Headers: `Authorization: Bearer {access_token}`

**Configuration:**
```env
WEB__CLIENT_ID=your-app-id
WEB__CLIENT_SECRET=your-secret
WEB__REDIRECT_URI=http://localhost:8000/auth/callback
```

**Flow File:** `discord_bot/web/auth/oauth.py`

#### Rate Limits

- OAuth: No per-request limit (burst + per-minute)
- REST: 50 requests/second (bucket-based)
- Gateway: Connection limit + identify rate limit

### OCR Service (Optional)

**Purpose:** Auto-verify player screenshots
**Configuration:** (env variables in `verification/config.py`)
```env
VERIFICATION__API_URL=https://ocr-service.example.com
VERIFICATION__API_KEY=your-api-key
VERIFICATION__API_TIMEOUT=30
```

**Usage File:** `discord_bot/verification/auto_processor.py`

**Request:**
```
POST {API_URL}/verify
Headers: Authorization: Bearer {API_KEY}
Body: {
  "screenshot_urls": ["url1", "url2"],
  "game_name": "game-name"
}
```

**Response:**
```json
{
  "success": true,
  "player_info": {
    "name": "PlayerName",
    "level": 50,
    "faction": "Faction",
    "shard": "Shard",
    ...
  }
}
```

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

**Retry on locked:**
```python
@event.listens_for(AsyncEngine, "connect")
async def set_sqlite_timeout(conn):
    await conn.execute(text("PRAGMA busy_timeout=5000"))
```

### PostgreSQL (Optional)

**URL:** `postgresql+asyncpg://user:password@host:5432/dbname`
**Async Driver:** `asyncpg`
**Connection Pool:** 5 base + 10 overflow (configurable)

**Production Configuration:**
```env
DATABASE__URL=postgresql+asyncpg://user:pass@prod-db.example.com/discord_bot
```

---

## Deployment Services

### Docker

**Base Image:** `python:3.12-slim`
**Dockerfile:** `/home/xurxogr/code/discord/Dockerfile`

**Components:**
- Multi-stage build (dev stages excluded from final image)
- Health check: `GET /health` endpoint
- Volume: `/data` (for SQLite DB)
- Port: 8000 (FastAPI)
- Environment: Loads from `.env` or docker-compose

**Compose File:** `/home/xurxogr/code/discord/docker-compose.yml`

Services:
1. **discord-bot** - Main bot + web server
2. **postgres** (optional) - PostgreSQL database

### Environment Configuration

**Load order:**
1. Environment variables (highest priority)
2. `.env` file in working directory
3. JSON config file (`~/.config/discord-bot/config.json`)
4. Pydantic defaults (lowest priority)

**Example .env:**
```bash
BOT__TOKEN=your_token_here
WEB__ENABLED=true
WEB__CLIENT_ID=your_app_id
WEB__CLIENT_SECRET=your_secret
DATABASE__URL=sqlite+aiosqlite:///data/bot.db
LOGGING__LOG_LEVEL=INFO
```

---

## Utility Libraries

### Logging

**Framework:** Python `logging` module
**Config:** `discord_bot/common/core/logging.py`
**Levels:** DEBUG, INFO, WARNING, ERROR, CRITICAL

**Features:**
- File logging (optional)
- Console logging (always)
- Timestamp, level, logger name
- Bot/Cog context in messages

### Message Utilities

**File:** `discord_bot/common/utils/`

```python
async def delete_message(message: discord.Message, delay: float = 0)
def has_any_role(member: discord.Member, role_ids: list[int]) -> bool
```

### Event Bus (Internal)

**File:** `discord_bot/common/services/event_bus.py`
**Type:** Pub/sub pattern (in-memory)

**Events:**
- `VerificationCompleted` (from verification cog)
- `VerificationRejected` (from verification cog)
- Custom events per cog

**Usage:**
```python
event_bus = get_event_bus()
event_bus.publish(VerificationCompleted(user_id=123, ...))
```

---

## Third-Party Integrations

### None Required

This bot is self-contained:
- Discord API for events & user mgmt
- Optional OCR service (user-provided)
- No required third-party SaaS

### Optional Integrations

| Service | Purpose | When Enabled |
|---------|---------|--------------|
| OCR API | Auto-verify screenshots | `VERIFICATION__API_URL` set |
| Sentry/Similar | Error tracking | User implementation |
| Prometheus/Similar | Metrics | User implementation |

---

## API Client Abstractions

### Discord API

**Wrapper:** discord.py built-in
**No custom HTTP client** (discord.py handles)

### OAuth2 Client

**File:** `discord_bot/web/auth/oauth.py`
**Library:** `httpx` (async HTTP client)

```python
async with httpx.AsyncClient() as client:
    response = await client.post(
        "https://discord.com/api/oauth2/token",
        data={...},
        headers={...}
    )
    token_data = response.json()
```

**Error Handling:**
- Timeout (VERIFICATION__API_TIMEOUT) → Raise HTTPException
- 5xx errors → Retry logic (3 attempts)
- Invalid response → Log and fail gracefully

---

## Version Constraints

### Python

**Minimum:** 3.12
**Requirement:** `python-requires = ">=3.12"`
**Tested on:** Python 3.12.x

### Discord.py

**Version:** 2.0+
**Latest tested:** 2.x stable

### SQLAlchemy

**Version:** 2.0+
**Features used:** async ORM, mapped_column, relationships

### Pydantic

**Version:** 2.x
**Features used:** Field validation, ConfigDict, computed_fields

---

## Security Implications

### Token Management

- **Bot Token:** Never log, only env/config file
- **OAuth Secrets:** Never log, only env/config file
- **Session Secret:** Auto-generated if not provided (warning logged)

### Dependency Scanning

- **Tool:** (User responsibility via pip-audit)
- **CI/CD:** Should include dependency vulnerability checks

### Known Vulnerabilities

- None known as of 2026-03-11
- Regular updates recommended for all packages

---

## Performance Characteristics

### Database Connections

- **Pool size:** 5 + 10 overflow
- **Max latency:** ~100ms (localhost SQLite)
- **Concurrent sessions:** Limited by pool size

### API Rate Limits

- **Discord REST:** 50 req/sec bucket-based
- **Discord Gateway:** 1 identify/5s
- **OCR Service:** User-defined (configurable)

### Memory Usage

- **Base process:** ~100MB (Python + libraries)
- **Per guild:** ~1-5KB (config cache)
- **Connection pool:** ~10MB
- **Rate limiter:** O(1) per IP

---

## Troubleshooting Dependencies

### Discord.py Issues

- Intents not enabled → `requires message_content` error
- Token invalid → Connection fails with 401
- Missing privileged intents → Warning in logs

### Database Issues

- SQLite locked → Wait/retry (5s timeout configured)
- PostgreSQL connection refused → Check WEB__DATABASE__URL
- Migration failures → Check alembic.ini, run `alembic current`

### OAuth Issues

- Invalid state → Reload /login
- Token expired → Redirect to /login
- Scope insufficient → Bot token vs. user token mismatch
