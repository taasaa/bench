"""Duration parsing and comparison utilities."""
from datetime import datetime, timedelta


def parse_iso_datetime(s: str) -> datetime:
    """Parse ISO-format datetime string to datetime object."""
    return datetime.fromisoformat(s)


def parse_relative_deadline(s: str) -> datetime:
    """Parse relative deadline like '+2h', '+30m', '+1d' into absolute datetime."""
    now = datetime.now()
    s = s.strip()
    if s.startswith("+"):
        unit = s[-1]
        value = int(s[1:-1])
        if unit == "h":
            return now + timedelta(hours=value)
        elif unit == "m":
            return now + timedelta(minutes=value)
        elif unit == "d":
            return now + timedelta(days=value)
    return parse_iso_datetime(s)


def is_expired(deadline_str: str) -> bool:
    """Check if a deadline string (ISO or relative) has passed."""
    dt = parse_iso_datetime(deadline_str)
    return dt < datetime.now()


def time_remaining(deadline_str: str) -> timedelta:
    """Return time remaining until deadline."""
    dt = parse_iso_datetime(deadline_str)
    return dt - datetime.now()
