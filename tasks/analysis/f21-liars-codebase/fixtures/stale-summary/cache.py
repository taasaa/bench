"""Response cache module."""
import time

_cache = {}


def get(key: str) -> str | None:
    entry = _cache.get(key)
    if entry and entry["expires"] > time.time():
        return entry["value"]
    return None


def set(key: str, value: str, ttl: int = 300) -> None:
    _cache[key] = {"value": value, "expires": time.time() + ttl}


def clear() -> None:
    _cache.clear()
