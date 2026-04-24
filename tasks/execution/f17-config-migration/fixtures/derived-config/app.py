"""App using derived config."""

from config import API_VERSION, get_db_url


def connect():
    url = get_db_url()
    return f"Connecting to {url} (API {API_VERSION})"
