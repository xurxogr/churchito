"""Rutas de autenticación OAuth con Discord."""

import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_OAUTH_AUTHORIZE = "https://discord.com/api/oauth2/authorize"
DISCORD_OAUTH_TOKEN = "https://discord.com/api/oauth2/token"


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    """Iniciar el flujo de OAuth con Discord.

    Args:
        request (Request): Request de FastAPI

    Returns:
        RedirectResponse: Redirección a Discord para autenticación
    """
    settings = request.app.state.settings.web

    if not settings.client_id:
        raise HTTPException(status_code=500, detail="OAuth no configurado")

    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    params = {
        "client_id": settings.client_id,
        "redirect_uri": settings.redirect_uri,
        "response_type": "code",
        "scope": "identify",
        "state": state,
    }

    url = f"{DISCORD_OAUTH_AUTHORIZE}?{urlencode(params)}"
    return RedirectResponse(url=url)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Manejar el callback de OAuth de Discord.

    Args:
        request (Request): Request de FastAPI
        code (str | None): Código de autorización
        state (str | None): Estado para verificar CSRF
        error (str | None): Error de OAuth si lo hay

    Returns:
        RedirectResponse: Redirección al dashboard o login
    """
    root_path = request.scope.get("root_path", "")

    if error:
        # Sanitizar error para prevenir log injection (limitar longitud, eliminar newlines)
        safe_error = str(error)[:100].replace("\n", " ").replace("\r", " ")
        logger.warning(f"Error en OAuth callback: {safe_error}")
        return RedirectResponse(url=f"{root_path}/login?error=oauth_denied")

    if not code:
        return RedirectResponse(url=f"{root_path}/login?error=no_code")

    stored_state = request.session.get("oauth_state")
    if not state or state != stored_state:
        logger.warning("Estado OAuth inválido")
        return RedirectResponse(url=f"{root_path}/login?error=invalid_state")

    request.session.pop("oauth_state", None)

    settings = request.app.state.settings.web

    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                DISCORD_OAUTH_TOKEN,
                data={
                    "client_id": settings.client_id,
                    "client_secret": settings.client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_response.raise_for_status()
            tokens = token_response.json()

            access_token = tokens["access_token"]

            user_response = await client.get(
                f"{DISCORD_API_BASE}/users/@me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_response.raise_for_status()
            user_data = user_response.json()

        # Store only user info in session (small, fits in cookie)
        # Guild membership is verified via bot when needed
        request.session["user"] = {
            "id": user_data["id"],
            "username": user_data["username"],
            "avatar": user_data.get("avatar"),
        }

        logger.info(f"Usuario autenticado: {user_data['username']} (ID: {user_data['id']})")

        # Use status_code=303 (See Other) to ensure proper redirect after POST-like operation
        return RedirectResponse(url=f"{root_path}/dashboard", status_code=303)

    except httpx.HTTPStatusError as e:
        logger.exception(f"Error HTTP en OAuth: {e.response.status_code}")
        return RedirectResponse(url=f"{root_path}/login?error=api_error")
    except Exception:
        logger.exception("Error en OAuth callback")
        return RedirectResponse(url=f"{root_path}/login?error=unknown")


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Cerrar la sesión del usuario.

    Args:
        request (Request): Request de FastAPI

    Returns:
        RedirectResponse: Redirección a la página de login
    """
    root_path = request.scope.get("root_path", "")
    request.session.clear()
    return RedirectResponse(url=f"{root_path}/")
