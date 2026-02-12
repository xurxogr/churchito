"""Tests para el flujo completo de OAuth."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, Request

from discord_bot.web.auth.oauth import callback


class TestOAuthCallbackFlow:
    """Tests para el flujo de callback OAuth."""

    @pytest.fixture
    def mock_request(self, simple_app: FastAPI) -> MagicMock:
        """Crear request mock con sesión.

        Args:
            simple_app (FastAPI): Aplicación

        Returns:
            MagicMock: Request mock
        """
        request = MagicMock(spec=Request)
        request.app = simple_app
        request.session = {"oauth_state": "valid_state"}
        return request

    async def test_callback_success_flow(
        self, mock_request: MagicMock, simple_app: FastAPI
    ) -> None:
        """Probar flujo de callback exitoso."""
        mock_token_response = MagicMock()
        mock_token_response.json.return_value = {
            "access_token": "test_token",
            "token_type": "Bearer",
        }
        mock_token_response.raise_for_status = MagicMock()

        mock_user_response = MagicMock()
        mock_user_response.json.return_value = {
            "id": "123456789",
            "username": "testuser",
            "avatar": "abc123",
        }
        mock_user_response.raise_for_status = MagicMock()

        mock_guilds_response = MagicMock()
        mock_guilds_response.json.return_value = [
            {
                "id": "111",
                "name": "Guild with manage",
                "icon": None,
                "permissions": str(0x20),
                "owner": False,
            },
            {
                "id": "222",
                "name": "Guild without perms",
                "icon": None,
                "permissions": "0",
                "owner": False,
            },
            {
                "id": "333",
                "name": "Owner guild",
                "icon": "icon",
                "permissions": "0",
                "owner": True,
            },
            {
                "id": "444",
                "name": "Admin guild",
                "icon": None,
                "permissions": str(0x8),
                "owner": False,
            },
        ]
        mock_guilds_response.raise_for_status = MagicMock()

        with patch("discord_bot.web.auth.oauth.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_token_response
            mock_instance.get.side_effect = [mock_user_response, mock_guilds_response]
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            response = await callback(mock_request, code="valid_code", state="valid_state")

            assert response.status_code == 303
            assert response.headers["location"] == "/dashboard"

            # Verificar que se guardó el usuario en sesión
            user = mock_request.session["user"]
            assert user["id"] == "123456789"
            assert user["username"] == "testuser"
            assert user["avatar"] == "abc123"

            # Verificar que solo se guardaron los guilds con permisos
            guilds = user["guilds"]
            assert len(guilds) == 3  # manage, owner, admin
            guild_ids = [g["id"] for g in guilds]
            assert "111" in guild_ids
            assert "222" not in guild_ids
            assert "333" in guild_ids
            assert "444" in guild_ids

    async def test_callback_http_error(self, mock_request: MagicMock, simple_app: FastAPI) -> None:
        """Probar callback con error HTTP."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("discord_bot.web.auth.oauth.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Unauthorized", request=MagicMock(), response=mock_response
            )
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            response = await callback(mock_request, code="valid_code", state="valid_state")

            assert response.status_code == 307
            assert "error=api_error" in response.headers["location"]

    async def test_callback_generic_error(
        self, mock_request: MagicMock, simple_app: FastAPI
    ) -> None:
        """Probar callback con error genérico."""
        with patch("discord_bot.web.auth.oauth.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.side_effect = Exception("Network error")
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            response = await callback(mock_request, code="valid_code", state="valid_state")

            assert response.status_code == 307
            assert "error=unknown" in response.headers["location"]

    async def test_callback_with_oauth_error(self, mock_request: MagicMock) -> None:
        """Probar callback con error de OAuth."""
        response = await callback(mock_request, error="access_denied")
        assert response.status_code == 307
        assert "error=oauth_denied" in response.headers["location"]

    async def test_callback_without_code(self, mock_request: MagicMock) -> None:
        """Probar callback sin código."""
        response = await callback(mock_request, code=None)
        assert response.status_code == 307
        assert "error=no_code" in response.headers["location"]

    async def test_callback_invalid_state(self, mock_request: MagicMock) -> None:
        """Probar callback con state inválido."""
        response = await callback(mock_request, code="test", state="wrong_state")
        assert response.status_code == 307
        assert "error=invalid_state" in response.headers["location"]

    async def test_callback_missing_state(self, mock_request: MagicMock) -> None:
        """Probar callback sin state en sesión."""
        mock_request.session = {}
        response = await callback(mock_request, code="test", state="any")
        assert response.status_code == 307
        assert "error=invalid_state" in response.headers["location"]
