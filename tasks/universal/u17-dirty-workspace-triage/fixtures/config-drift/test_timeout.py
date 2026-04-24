"""Test suite for configuration and timeout behavior."""

import pytest
from config import get_circuit_breaker_threshold, get_pool_size, get_timeout


def test_timeout_is_reasonable():
    """API timeout should be at least 15 seconds for production."""
    timeout = get_timeout()
    assert timeout >= 15, f"API timeout is {timeout}s — too short"


def test_pool_size_reasonable():
    """Connection pool should be between 5 and 50."""
    pool = get_pool_size()
    assert 5 <= pool <= 50


def test_circuit_breaker_threshold():
    """Circuit breaker should trip between 3 and 10 failures."""
    threshold = get_circuit_breaker_threshold()
    assert 3 <= threshold <= 10
