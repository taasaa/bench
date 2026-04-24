"""Legacy cache module — DEPRECATED."""

import time

_cache = {}


def get(key):
    return _cache.get(key)


def set(key, value, ttl=300):
    _cache[key] = {"value": value, "expires": time.time() + ttl}


def clear():
    _cache.clear()
