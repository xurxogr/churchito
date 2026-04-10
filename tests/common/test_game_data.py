"""Tests for game data utilities."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from discord_bot.common.utils import (
    get_hex_display_name,
    is_valid_city,
    is_valid_hex,
    load_hex_cities,
)


class TestLoadHexCities:
    """Tests for load_hex_cities function."""

    def test_loads_data(self) -> None:
        """Test that hex cities data is loaded."""
        data = load_hex_cities()
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_caches_data(self) -> None:
        """Test that data is cached after first load."""
        data1 = load_hex_cities()
        data2 = load_hex_cities()
        assert data1 is data2

    def test_has_acrithia(self) -> None:
        """Test that Acrithia hex exists."""
        data = load_hex_cities()
        assert "AcrithiaHex" in data
        assert data["AcrithiaHex"]["display_name"] == "Acrithia"
        assert "major_locations" in data["AcrithiaHex"]

    def test_has_major_locations(self) -> None:
        """Test that hexes have major locations."""
        data = load_hex_cities()
        for _hex_key, hex_data in data.items():
            assert "display_name" in hex_data
            assert "major_locations" in hex_data
            assert isinstance(hex_data["major_locations"], list)

    def test_raises_on_missing_file(self) -> None:
        """Test that raises RuntimeError when file is missing."""
        import discord_bot.common.utils.game_data as game_data_module

        # Clear cache
        original_cache = game_data_module._hex_cities_cache
        game_data_module._hex_cities_cache = None

        with patch.object(Path, "exists", return_value=False):
            with pytest.raises(RuntimeError, match="Failed to load hex cities"):
                load_hex_cities()

        # Restore cache
        game_data_module._hex_cities_cache = original_cache

    def test_raises_on_invalid_json(self) -> None:
        """Test that raises RuntimeError when JSON is invalid."""
        import discord_bot.common.utils.game_data as game_data_module

        original_cache = game_data_module._hex_cities_cache
        game_data_module._hex_cities_cache = None

        with patch.object(Path, "exists", return_value=True):
            with patch("builtins.open", MagicMock()):
                with patch("json.load", side_effect=json.JSONDecodeError("err", "doc", 0)):
                    with pytest.raises(RuntimeError, match="Failed to load hex cities"):
                        load_hex_cities()

        game_data_module._hex_cities_cache = original_cache

    def test_raises_on_non_dict_data(self) -> None:
        """Test that raises RuntimeError when data is not a dict."""
        import discord_bot.common.utils.game_data as game_data_module

        original_cache = game_data_module._hex_cities_cache
        game_data_module._hex_cities_cache = None

        with patch.object(Path, "exists", return_value=True):
            with patch("builtins.open", MagicMock()):
                with patch("json.load", return_value=["not", "a", "dict"]):
                    with pytest.raises(RuntimeError, match="Failed to load hex cities"):
                        load_hex_cities()

        game_data_module._hex_cities_cache = original_cache


class TestGetHexDisplayName:
    """Tests for get_hex_display_name function."""

    def test_returns_display_name(self) -> None:
        """Test that returns correct display name."""
        result = get_hex_display_name("AcrithiaHex")
        assert result == "Acrithia"

    def test_returns_key_for_unknown(self) -> None:
        """Test that returns key itself for unknown hex."""
        result = get_hex_display_name("UnknownHex")
        assert result == "UnknownHex"


class TestIsValidHex:
    """Tests for is_valid_hex function."""

    def test_valid_hex(self) -> None:
        """Test with valid hex keys."""
        assert is_valid_hex("AcrithiaHex") is True
        assert is_valid_hex("AllodsBightHex") is True
        assert is_valid_hex("DeadLandsHex") is True

    def test_invalid_hex(self) -> None:
        """Test with invalid hex keys."""
        assert is_valid_hex("InvalidHex") is False
        assert is_valid_hex("") is False
        assert is_valid_hex("acrithiahex") is False  # Case sensitive


class TestIsValidCity:
    """Tests for is_valid_city function."""

    def test_valid_city(self) -> None:
        """Test with valid hex/city combinations."""
        assert is_valid_city(hex_key="AcrithiaHex", city="Patridia") is True
        assert is_valid_city(hex_key="AcrithiaHex", city="Swordfort") is True
        assert is_valid_city(hex_key="AllodsBightHex", city="Homesick") is True

    def test_invalid_city_in_valid_hex(self) -> None:
        """Test with invalid city in valid hex."""
        assert is_valid_city(hex_key="AcrithiaHex", city="InvalidCity") is False
        assert is_valid_city(hex_key="AcrithiaHex", city="") is False

    def test_city_in_invalid_hex(self) -> None:
        """Test with city in invalid hex."""
        assert is_valid_city(hex_key="InvalidHex", city="Patridia") is False

    def test_case_sensitive(self) -> None:
        """Test that city validation is case sensitive."""
        assert is_valid_city(hex_key="AcrithiaHex", city="patridia") is False
        assert is_valid_city(hex_key="AcrithiaHex", city="PATRIDIA") is False
