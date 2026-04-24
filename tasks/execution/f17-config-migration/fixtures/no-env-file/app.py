"""App using config — no .env file exists."""

from config import get_settings


def client_info():
    s = get_settings()
    return f"API: {s['base_url']}, timeout={s['timeout']}s, retries={s['retry_count']}"
