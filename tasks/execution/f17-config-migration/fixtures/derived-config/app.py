"""App using derived config."""
from config import get_db_url, API_VERSION


def connect():
    url = get_db_url()
    return f"Connecting to {url} (API {API_VERSION})"
