"""Game data utilities for Foxhole map information."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Cache for hex cities data
_hex_cities_cache: dict[str, Any] | None = None


def load_hex_cities() -> dict[str, Any]:
    """Load hex cities data from JSON file.

    Returns:
        dict: Hex cities data with display names and major locations

    Raises:
        RuntimeError: If the data file cannot be loaded
    """
    global _hex_cities_cache
    if _hex_cities_cache is not None:
        return _hex_cities_cache

    data_path = Path(__file__).parent.parent.parent / "data" / "hex_cities.json"

    try:
        if not data_path.exists():
            raise FileNotFoundError(f"Hex cities data not found at {data_path}")

        with open(data_path, encoding="utf-8") as f:
            _hex_cities_cache = json.load(f)

        if not isinstance(_hex_cities_cache, dict):
            raise ValueError("Hex cities data must be a dictionary")

        return _hex_cities_cache
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        logger.error(f"Failed to load hex cities data: {e}")
        raise RuntimeError(f"Failed to load hex cities configuration: {e}") from e


def is_valid_hex(hex_key: str) -> bool:
    """Check if a hex key is valid.

    Args:
        hex_key: Hex key to validate

    Returns:
        bool: True if valid
    """
    hex_data = load_hex_cities()
    return hex_key in hex_data


def is_valid_city(hex_key: str, city: str) -> bool:
    """Check if a city is valid for a given hex.

    Args:
        hex_key: Hex key
        city: City name to validate

    Returns:
        bool: True if valid
    """
    hex_data = load_hex_cities()
    if hex_key not in hex_data:
        return False
    return city in hex_data[hex_key].get("major_locations", [])


def get_hex_display_name(hex_key: str) -> str:
    """Get the display name for a hex key.

    Args:
        hex_key: Internal hex key

    Returns:
        str: Human-readable hex name
    """
    hex_data = load_hex_cities()
    result = hex_data.get(hex_key, {}).get("display_name", hex_key)
    return str(result)


def get_all_hex_keys() -> list[str]:
    """Get all valid hex keys.

    Returns:
        list[str]: List of all hex keys
    """
    return list(load_hex_cities().keys())


def get_cities_for_hex(hex_key: str) -> list[str]:
    """Get all cities for a given hex.

    Args:
        hex_key: Hex key

    Returns:
        list[str]: List of city names, empty if hex not found
    """
    hex_data = load_hex_cities()
    result = hex_data.get(hex_key, {}).get("major_locations", [])
    return list(result)
