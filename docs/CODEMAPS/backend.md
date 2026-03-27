# Backend (Web API) Codemap

**Last Updated:** 2026-03-12
**Entry Point:** `discord_bot/web/app.py:create_app()`
**Port:** 8000 (default)
**Token Estimate:** ~1000 tokens

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

**Order of execution:** Request → (5) → (4) → (3) → (2) → (1) → Response

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

#### CSRFMiddleware (`middleware/csrf.py`)
- POST/PUT/DELETE require valid `csrf_token`
- Token stored in session and form
- State validation: None → 403

#### SessionMiddleware
- Cookie: `bot_session`
- Max age: 2592000s (30 days, configurable)
- Same-site: Lax
- HTTPS only: configurable

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

| Method | Path | Params | Returns |
|--------|------|--------|---------|
| GET | `/auth/login` | - | 302 → Discord |
| GET | `/auth/callback` | code, state, error | 302 → /dashboard or /login |
| GET | `/auth/logout` | - | 302 → /login |

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
| GET | `/login` | None | HTML | Login page |
| GET | `/dashboard` | Required | HTML | Guild list + cog status |
| GET | `/api/guilds` | Required | JSON | User's guilds |

#### GET / (Root)
```python
@router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: CurrentUser):
    if user:
        return RedirectResponse(url="{root_path}/dashboard")
    return templates.TemplateResponse("login.html", {...})
```

#### GET /login
Login page with "Sign in with Discord" button

#### GET /dashboard
```python
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: CurrentUser,
    db_session: DbSession
):
    """Guild list with cog status, role counts, etc."""
```

Renders: `discord_bot/web/templates/dashboard.html`

#### GET /api/guilds
```python
@router.get("/api/guilds")
async def get_guilds(
    request: Request,
    user: CurrentUser,
    db_session: DbSession
) -> list[dict]:
    """Return user's guilds (joined as owner or admin role)."""
```

Returns:
```json
[
  {
    "id": 12345,
    "name": "Guild Name",
    "icon": "icon_url",
    "permission": 8,
    "owner": true
  }
]
```

---

### Configuration Router

**File:** `discord_bot/web/routers/config.py`

| Method | Path | Auth | Response | Purpose |
|--------|------|------|----------|---------|
| GET | `/dashboard/{guild_id}/config` | Required | HTML | Config UI |
| GET | `/api/config/{guild_id}` | Required | JSON | Current config values |
| POST | `/api/config/{guild_id}` | Required | JSON | Save config |
| GET | `/api/config/{guild_id}/schema` | Required | JSON | Config schema (form definition) |

#### GET /dashboard/{guild_id}/config
Renders: `discord_bot/web/templates/config.html`

**Dependencies:**
- `RequireAuth` - User must be authenticated
- `DbSession` - SQLAlchemy session
- Guild admin check: admin role or owner

#### GET /api/config/{guild_id}
```python
async def get_guild_config(
    guild_id: int,
    user: CurrentUser,
    db_session: DbSession
) -> dict:
    """Return current config for guild (all cogs)."""
```

Response:
```json
{
  "verification": {
    "enabled": true,
    "mod_channel_id": 98765,
    "verification_role_id": 54321,
    ...
  },
  "purge": {
    "enabled": true,
    ...
  }
}
```

#### POST /api/config/{guild_id}
Save config changes:
```python
@router.post("/api/config/{guild_id}")
async def save_guild_config(
    guild_id: int,
    payload: dict,  # {cog_name: {key: value, ...}, ...}
    user: CurrentUser,
    db_session: DbSession
) -> dict:
    """Validate and save config changes."""
```

**Validation:**
1. Check user is admin
2. Check guild_id matches bot
3. For each cog/key: validate via schema
4. Update GuildConfig in database
5. Return updated config

#### GET /api/config/{guild_id}/schema
```python
async def get_config_schema(guild_id: int) -> dict:
    """Return schema (form definition) for config UI."""
```

Response:
```json
{
  "verification": {
    "cog_name": "verification",
    "display_name": "Verification",
    "toggleable": true,
    "options": [
      {
        "key": "enabled",
        "name": "Enabled",
        "option_type": "BOOLEAN",
        "default": false,
        "value": false
      },
      {
        "key": "mod_channel_id",
        "name": "Moderation Channel",
        "option_type": "CHANNEL_ID",
        ...
      }
    ]
  }
}
```

---

## Dependencies (Injection)

**File:** `discord_bot/web/dependencies.py`

### CurrentUser

```python
async def CurrentUser(request: Request) -> dict | None:
    """Get current user from session, or None if not authenticated."""
    return request.session.get("discord_user")
```

Used in routes that optionally need auth. Raises `NotAuthenticatedException` if required but missing.

### RequireAuth

```python
async def RequireAuth(user: CurrentUser) -> dict:
    """Require authentication, raise 403 if missing."""
    if not user:
        raise NotAuthenticatedException()
    return user
```

### DbSession

```python
async def DbSession(request: Request) -> AsyncSession:
    """Get database session from app state."""
    async with request.app.state.db_service.session() as session:
        yield session
```

---

## Exception Handlers

### NotAuthenticatedException
```python
@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_handler(...) -> RedirectResponse:
    return RedirectResponse(url="{root_path}/login", status_code=303)
```

### HTTPException
```python
@app.exception_handler(HTTPException)
async def http_exception_handler(...) -> HTMLResponse:
    """Render error.html with status_code and detail."""
```

Sanitizes 5xx errors (doesn't expose internal details).

### Generic Exception
```python
@app.exception_handler(Exception)
async def generic_exception_handler(...) -> HTMLResponse:
    """Log error, return generic 500 page."""
```

---

## Health Check

```python
@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

Used by Docker healthcheck:
```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"
```

---

## Templates

**Directory:** `discord_bot/web/templates/`

| Template | Used by | Purpose |
|----------|---------|---------|
| `base.html` | (extends in others) | Base layout (nav, footer) |
| `login.html` | GET / | OAuth login page |
| `dashboard.html` | GET /dashboard | Guild list |
| `config.html` | GET /config/{guild_id} | Config editor |
| `error.html` | Exception handler | Error page |

### Context Variables

All templates receive:
```python
{
    "root_path": "/prefix",  # If behind reverse proxy
    "csrf_token": "...",
    "bot_name": "BotName"
}
```

---

## Static Files

**Directory:** `discord_bot/web/static/`

```
static/
└── css/
    └── style.css
```

Mounted at: `/static/`

---

## Security Checklist

- [x] CSRF protection (SessionMiddleware + CSRFMiddleware)
- [x] SQL injection prevention (SQLAlchemy parameterized queries)
- [x] XSS prevention (Jinja2 auto-escape, no template injection)
- [x] Rate limiting (RateLimitMiddleware, but local-only)
- [x] HTTPS support (configurable, X-Forwarded-Proto aware)
- [x] Session security (secure cookies, max age, same-site)
- [x] Error handling (no stack traces to user, logged server-side)
