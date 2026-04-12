"""Configuration merger module for combining multiple config sources."""

from typing import Any, Dict


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two config dictionaries. Override values take precedence.

    BUG: Mutates the base dictionary instead of creating a copy.
    Should use deepcopy to avoid side effects on the input dictionaries.

    Args:
        base: The base configuration.
        override: Configuration values that override the base.

    Returns:
        Merged configuration dictionary.
    """
    for key, value in override.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            deep_merge(base[key], value)  # BUG: mutates base in-place
        else:
            base[key] = value  # BUG: mutates base in-place
    return base


def merge_configs(configs: list[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge a list of config dictionaries, left to right.

    Later configs override earlier ones.
    """
    if not configs:
        return {}

    result = configs[0]
    for config in configs[1:]:
        result = deep_merge(result, config)

    return result


def get_nested(config: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """Get a nested config value using dot notation.

    Args:
        config: The configuration dictionary.
        key_path: Dot-separated key path, e.g. "server.host".
        default: Default value if key not found.

    Returns:
        The value at the key path, or default.
    """
    keys = key_path.split(".")
    current = config
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current
