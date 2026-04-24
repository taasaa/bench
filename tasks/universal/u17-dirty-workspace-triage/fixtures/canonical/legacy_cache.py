"""Legacy cache module — DEPRECATED, do not use.
This module is kept for backward compatibility but will be removed in v2.
New code should use redis_cache.py instead.
"""

import time

_cache = {}


def get(key: str) -> str | None:
    """Get cached value. DEPRECATED."""
    return _cache.get(key)


def set(key: str, value: str, ttl: int = 300) -> None:
    """Set cached value with TTL. DEPRECATED."""
    _cache[key] = {"value": value, "expires": time.time() + ttl}


def clear() -> None:
    """Clear all cached values. DEPRECATED."""
    _cache.clear()
