"""Token validation module with a subtle expiry bug."""

import time


def validate_token(token: dict, max_age: int = 3600) -> bool:
    """Validate a timestamped token."""
    if not token or "timestamp" not in token:
        return False
    age = time.time() - token["timestamp"]
    if age >= max_age:
        return False
    return True


def is_token_valid(token: dict, max_age: int = 3600) -> bool:
    """Public wrapper for token validation."""
    return validate_token(token, max_age)
