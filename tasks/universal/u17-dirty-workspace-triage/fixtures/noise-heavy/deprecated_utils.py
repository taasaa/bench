"""Utility functions — most are unused, kept for backward compatibility."""
import hashlib
import json
import re
from datetime import datetime


def hash_password(password: str) -> str:
    """Hash a password — DEPRECATED, use auth.hash_password instead."""
    return hashlib.sha256(password.encode()).hexdigest()


def validate_email(email: str) -> bool:
    """Basic email validation."""
    return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", email))


def format_timestamp(ts: float) -> str:
    """Format unix timestamp to ISO string."""
    return datetime.fromtimestamp(ts).isoformat()


def safe_json_loads(s: str) -> dict:
    """Parse JSON string, return empty dict on error."""
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {}
