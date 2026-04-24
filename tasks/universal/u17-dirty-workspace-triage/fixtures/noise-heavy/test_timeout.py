"""Test suite for API timeout behavior."""

import pytest
from config import get_timeout


def test_timeout_is_reasonable():
    timeout = get_timeout()
    assert timeout >= 15, f"API timeout is {timeout}s — too short for production"


def test_timeout_not_excessive():
    timeout = get_timeout()
    assert timeout <= 120
