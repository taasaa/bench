"""Test suite for API timeout behavior."""

import pytest
from config import get_timeout


def test_timeout_is_reasonable():
    """API timeout should be at least 15 seconds for production."""
    timeout = get_timeout()
    assert timeout >= 15, f"API timeout is {timeout}s — too short for production"


def test_timeout_not_excessive():
    """API timeout should not exceed 120 seconds."""
    timeout = get_timeout()
    assert timeout <= 120, f"API timeout is {timeout}s — too long, will hang"


def test_max_retries_sensible():
    """Max retries should be between 1 and 5."""
    from config import get_max_retries

    retries = get_max_retries()
    assert 1 <= retries <= 5
