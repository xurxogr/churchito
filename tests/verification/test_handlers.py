"""Tests para handlers de verificación."""

from discord_bot.verification.handlers import _create_screenshot_embeds, _is_valid_discord_url


class TestIsValidDiscordUrl:
    """Tests para _is_valid_discord_url."""

    def test_valid_cdn_url(self) -> None:
        """Probar URL válida de cdn.discordapp.com."""
        url = "https://cdn.discordapp.com/attachments/123/456/image.png"
        assert _is_valid_discord_url(url) is True

    def test_valid_media_url(self) -> None:
        """Probar URL válida de media.discordapp.net."""
        url = "https://media.discordapp.net/attachments/123/456/image.png"
        assert _is_valid_discord_url(url) is True

    def test_empty_url(self) -> None:
        """Probar que URL vacía retorna False."""
        assert _is_valid_discord_url("") is False

    def test_http_url(self) -> None:
        """Probar que URL HTTP (no HTTPS) retorna False."""
        url = "http://cdn.discordapp.com/attachments/123/456/image.png"
        assert _is_valid_discord_url(url) is False

    def test_wrong_domain(self) -> None:
        """Probar que dominio incorrecto retorna False."""
        url = "https://example.com/image.png"
        assert _is_valid_discord_url(url) is False

    def test_malicious_url(self) -> None:
        """Probar que URL maliciosa retorna False."""
        url = "https://evil.com/cdn.discordapp.com/image.png"
        assert _is_valid_discord_url(url) is False

    def test_subdomain_attack(self) -> None:
        """Probar que subdominio malicioso retorna False."""
        url = "https://cdn.discordapp.com.evil.com/image.png"
        assert _is_valid_discord_url(url) is False

    def test_url_with_query_params(self) -> None:
        """Probar URL válida con query params."""
        url = "https://cdn.discordapp.com/attachments/123/456/image.png?size=128"
        assert _is_valid_discord_url(url) is True


class TestCreateScreenshotEmbeds:
    """Tests para _create_screenshot_embeds."""

    def test_creates_two_embeds_for_two_urls(self) -> None:
        """Probar que crea dos embeds para dos URLs."""
        url1 = "https://cdn.discordapp.com/attachments/123/456/1.png"
        url2 = "https://cdn.discordapp.com/attachments/123/456/2.png"

        embeds = _create_screenshot_embeds(url1=url1, url2=url2)

        assert len(embeds) == 2
        assert embeds[0].image.url == url1
        assert embeds[1].image.url == url2

    def test_creates_one_embed_for_one_url(self) -> None:
        """Probar que crea un embed si solo hay una URL."""
        url1 = "https://cdn.discordapp.com/attachments/123/456/1.png"

        embeds = _create_screenshot_embeds(url1=url1, url2=None)

        assert len(embeds) == 1
        assert embeds[0].image.url == url1

    def test_creates_empty_list_for_no_urls(self) -> None:
        """Probar que retorna lista vacía si no hay URLs."""
        embeds = _create_screenshot_embeds(url1=None, url2=None)

        assert len(embeds) == 0

    def test_skips_none_url(self) -> None:
        """Probar que salta URL None."""
        url2 = "https://cdn.discordapp.com/attachments/123/456/2.png"

        embeds = _create_screenshot_embeds(url1=None, url2=url2)

        assert len(embeds) == 1
        assert embeds[0].image.url == url2
