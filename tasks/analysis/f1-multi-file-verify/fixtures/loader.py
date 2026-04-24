"""Configuration loader module."""

import json
from typing import Any, Dict


def load_config(filepath: str) -> dict[str, Any]:
    """Load a JSON configuration file.

    Args:
        filepath: Path to the JSON config file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    with open(filepath) as f:
        return json.load(f)


def load_default_config() -> dict[str, Any]:
    """Load the built-in default configuration."""
    return {
        "server": {
            "host": "0.0.0.0",
            "port": 8080,
            "timeout": 30,
        },
        "logging": {
            "level": "INFO",
            "format": "text",
        },
    }


def merge_with_defaults(user_config: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Merge user config on top of defaults (user values take precedence)."""
    result = defaults.copy()
    for key, value in user_config.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_with_defaults(value, result[key])
        else:
            result[key] = value
    return result
