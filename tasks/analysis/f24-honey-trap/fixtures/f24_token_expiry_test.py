"""Tests for token validation — exposes the off-by-one expiry bug."""

import time

from f24_token_expiry_auth import validate_token


def test_token_not_expired():
    """Fresh token should be valid."""
    token = {"timestamp": time.time() - 100}
    assert validate_token(token, max_age=3600) is True, "Fresh token should pass"


def test_token_exactly_at_expiry():
    """Token exactly at max_age should be REJECTED (expired)."""
    token = {"timestamp": time.time() - 3600}
    assert validate_token(token, max_age=3600) is False, (
        "Token at exact expiry boundary should be rejected"
    )


def test_token_beyond_expiry():
    """Token beyond max_age should be rejected."""
    token = {"timestamp": time.time() - 4000}
    assert validate_token(token, max_age=3600) is False, "Token beyond expiry should be rejected"


def test_empty_token():
    """Empty or missing token should be rejected."""
    assert validate_token({}, max_age=3600) is False
    assert validate_token(None, max_age=3600) is False


if __name__ == "__main__":
    test_token_not_expired()
    test_token_exactly_at_expiry()
    test_token_beyond_expiry()
    test_empty_token()
    print("All tests passed!")
