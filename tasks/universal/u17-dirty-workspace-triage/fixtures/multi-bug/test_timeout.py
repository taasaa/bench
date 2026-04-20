"""Test suite for API timeout behavior."""
import pytest
from config import get_timeout, is_debug


def test_timeout_is_reasonable():
    """API timeout should be at least 15 seconds for production."""
    timeout = get_timeout()
    assert timeout >= 15, f"API timeout is {timeout}s — too short"


def test_debug_off_in_production():
    """Debug mode should be off in production config."""
    assert not is_debug(), "DEBUG should be False for production"


def test_timeout_not_excessive():
    """API timeout should not exceed 120 seconds."""
    timeout = get_timeout()
    assert timeout <= 120
