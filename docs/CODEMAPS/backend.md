# Backend (Web API) Codemap

<!-- Generated: 2026-05-13 | Files scanned: 126 | Token estimate: ~1100 -->

**Last Updated:** 2026-05-13
**Entry Point:** `discord_bot/web/app.py:create_app()`
**Port:** 8000 (default)

## Application Factory

**File:** `discord_bot/web/app.py`

```python
def create_app(
    settings: AppSettings,
    db_service: DatabaseService,
    bot: object | None = None
) -> FastAPI:
    """Create FastAPI application with all middleware and routers."""
```

Creates:
1. FastAPI instance
2. Registers middleware (in reverse order)
3. Mounts static files
4. Includes routers
5. Registers exception handlers

---

## Middleware Stack

**Order of execution:** Request → (6) → (5) → (4) → (3) → (2) → (1) → Response

| Order | File | Purpose | Status Codes |
|-------|------|---------|--------------|
| (1) | `middleware/security_headers.py` | CSP, X-Frame, X-Content-Type | 200+ |
| (2) | `middleware/rate_limit.py` | Token bucket per IP | 429 |
| (3) | `middleware/csrf.py` | CSRF token validation | 403 |
| (4) | Starlette `SessionMiddleware` | Session cookies | 200+ |
| (5) | Starlette `ProxyHeadersMiddleware` | X-Forwarded headers | 200+ |
| (6) | `middleware/content_size.py` | Max body size | 413 |

### Middleware Details

#### SecurityHeadersMiddleware (`middleware/security_headers.py`)
```
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Strict-Transport-Security: max-age=31536000 (if https_only=true)
Content-Security-Policy: default-src 'self'
```

#### RateLimitMiddleware (`middleware/rate_limit.py`)
- In-memory token bucket (NOT distributed)
- WARNING: Doesn't scale across multiple workers
- Default: 100 requests/minute per IP
- Whitelist: `127.0.0.1`, `::1` (localhost, never rate-limited)

#### CSRFMiddleware (`middleware/csrf.py`)
- POST/PUT/DELETE require valid `csrf_token`
- Token stored in session and form hidden field
- State validation: None → 403 Forbidden
- Safe methods (GET, HEAD, OPTIONS) exempt

#### SessionMiddleware
- Cookie: `bot_session`
- Max age: 2592000s (30 days, configurable)
- Same-site: Lax
- HTTPS only: configurable (default: true in production)

#### ProxyHeadersMiddleware
- Reads `X-Forwarded-Proto` for https detection
- Reads `X-Forwarded-For` for client IP
- Trusted hosts: from config (default: 127.0.0.1)

#### ContentSizeLimitMiddleware (`middleware/content_size.py`)
- Max body: 10 MB (configurable)
- Rejects → 413 Payload Too Large

---

## Authentication Layer

**File:** `discord_bot/web/auth/oauth.py`

### OAuth2 Flow (Discord)

```
GET /auth/login
  ↓ (Session: store CSRF state token)
  Redirect to: https://discord.com/api/oauth2/authorize
              ?client_id=...&scope=identify&state=...&redirect_uri=...
  ↓ (User approves, Discord redirects)
GET /auth/callback?code=...&state=...
  ↓ (Verify state, exchange code)
POST https://discord.com/api/oauth2/token
  ↓ (Parse access token)
GET https://discord.com/api/v10/users/@me
  ↓ (Store in session)
Session["discord_user"] = {
    "id": 12345,
    "username": "player",
    "avatar": "hash"
}
  ↓ (Redirect to /dashboard)
GET /dashboard (with session cookie)
```

### Endpoints

**File:** `discord_bot/web/auth/oauth.py`

| Method | Path | Params | Returns | Purpose |
|--------|------|--------|---------|---------|
| GET | `/auth/login` | - | 302 → Discord | Start OAuth flow |
| GET | `/auth/callback` | code, state, error | 302 → /dashboard or /login | Handle OAuth response |
| GET | `/auth/logout` | - | 302 → /login | Clear session |

### Session Schema

```python
request.session = {
    "discord_user": {
        "id": int,
        "username": str,
        "avatar": str,
    },
    "oauth_state": {
        "value": str,
        "created_at": float (timestamp)
    }
}
```

**Session max age:** 2592000s (30 days)
**HTTPS only:** true (by default, set via WEB__HTTPS_ONLY)

---

## Route Handlers

### Dashboard Router

**File:** `discord_bot/web/routers/dashboard.py`

| Method | Path | Auth | Response | Purpose |
|--------|------|------|----------|---------|
| GET | `/` | None | Redirect or HTML | Index (redirects to /login or /dashboard) |
| GET | `/login` | None | HTML | Login page (shows OAuth link) |
| GET | `/dashboard` | Required | HTML | Guild list + cog status |
| GET | `/api/guilds` | Required | JSON | User's guilds (from Discord API) |

### Config Router

**File:** `discord_bot/web/routers/config.py`

| Method | Path | Auth | Response | Purpose |
|--------|------|------|----------|---------|
| GET | `/dashboard/{guild_id}/config` | Required | HTML | Configuration form |
| GET | `/api/config/{guild_id}` | Required | JSON | Current guild config |
| POST | `/api/config/{guild_id}` | Required | JSON | Update guild config |

### Config Response Schema

**GET `/api/config/{guild_id}`**
```python
{
    "guild_id": int,
    "cogs": {
        "verification": {
            "enabled": bool,
            "options": {
                "mod_channel_id": int | null,
                "screenshot_timeout_minutes": int,
                "auto_process_mode": str,
                # ... more options
            },
            "schema": {
                "display_name": str,
                "description": str,
                "icon": str,
                "options": [
                    {
                        "key": str,
                        "name": str,
                        "description": str,
                        "type": str,  # "channel", "role", "string", etc.
                        "default": any,
                        "group": str | null,  # For section organization
                        # ... more fields
                    }
                ]
            }
        },
        "purge": { ... },
        "stockpile": { ... },
        "autoname": { ... }
    }
}
```

### Config Update Request

**POST `/api/config/{guild_id}`**

Request body:
```python
{
    "cog_name": str,  # "verification", "purge", etc.
    "updates": {
        "key1": value1,
        "key2": value2,
        # ... config key-value pairs
    }
}
```

Response:
```python
{
    "success": bool,
    "message": str,
    "errors": dict | null  # Per-field validation errors
}
```

---

## Authorization & Permissions

### Admin Check (Web Panel)

1. User must be authenticated (have `discord_user` in session)
2. User must be:
   - Server owner, OR
   - Member of admin role(s) configured in `guild_configs` (key: `admin_roles`)
   - User who invited the bot (if tracked)

Implementation:
```python
# In route handler
async def check_admin_access(guild_id: int, user_id: int, db_service: DatabaseService) -> bool:
    async with db_service.session() as session:
        config_service = ConfigService(session)
        admin_roles = await config_service.get_value(
            guild_id=guild_id,
            cog_name="bot",
            key="admin_roles"
        ) or []
        # Check user's roles against admin_roles list
```

### Cog-Level Permissions

Some config options are "locked" (read-only) if set via deployment config:
```python
class VerificationCog:
    def get_locked_options(self) -> dict[str, dict[str, Any]]:
        """Return options that are locked by deployment configuration."""
        # Returns {"mod_channel_id": {"locked": True, "reason": "..."},}
```

---

## Dependencies (Injection)

**File:** `discord_bot/web/dependencies.py`

```python
async def get_db_service(request: Request) -> DatabaseService:
    """Inject database service from app state."""
    return request.app.state.db_service

async def get_settings(request: Request) -> AppSettings:
    """Inject app settings from app state."""
    return request.app.state.settings

async def get_user(request: Request) -> dict | None:
    """Get authenticated user from session, or None."""
    return request.session.get("discord_user")
```

Usage in routes:
```python
@router.get("/api/config/{guild_id}")
async def get_config(
    guild_id: int,
    user: dict = Depends(get_user),
    db_service: DatabaseService = Depends(get_db_service),
):
    """Route handler with dependency injection."""
```

---

## Error Handling

### Exception Handlers

Registered in `create_app()`:
- `HTTPException` → returns JSON with `{"detail": "..."}` + status code
- `ValidationError` → returns JSON with field-level errors
- `Exception` (catch-all) → returns 500 + logs error

### Common Status Codes

| Code | Cause | Handler |
|------|-------|---------|
| 200 | Success | Route returns response |
| 302 | Redirect | OAuth flow, unauthorized web routes |
| 400 | Bad request | Invalid form data, missing required fields |
| 401 | Unauthorized | Missing session, OAuth expired |
| 403 | Forbidden | Invalid CSRF token, not admin, permission denied |
| 404 | Not found | Route doesn't exist |
| 413 | Payload too large | Upload exceeds 10 MB |
| 429 | Rate limit | Too many requests from IP |
| 500 | Server error | Unhandled exception (logged) |

---

## Static Files & Templates

### Static Files

**Location:** `discord_bot/web/static/`
- CSS, JavaScript, images
- Mounted at `/static/` route

### Jinja2 Templates

**Location:** `discord_bot/web/templates/`

Key templates:
- `base.html` - Extends with CSRF token, session info
- `login.html` - OAuth login button
- `dashboard.html` - Guild list, cog status
- `config.html` - Config form (dynamically generated from schema)

---

## Health Check Endpoint

**Path:** `GET /health`
**Auth:** None
**Response:**
```json
{
    "status": "ok",
    "timestamp": "2026-04-10T12:00:00Z",
    "version": "1.1.0"
}
```

---

## CORS

Not explicitly configured (same-origin only by default).
To enable CORS:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[...],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Recent Changes

### Config Schema Organization (2026-03-27+)
- Config options now support `group` field
- Web UI renders grouped options as collapsible sections
- Applies to all cogs: verification, purge, stockpile, autoname

### Verification Embed Formatting
- Mod channel messages now use embeds with sections
- Sections preserve existing data on update (no rebuild)

### Stockpile Config Options
- Organized into sections: General, Display, Notifications
- Command names configurable (/stockpile_add, /stockpile_show, /stockpile_delete)
- Notification settings for stockpile changes
