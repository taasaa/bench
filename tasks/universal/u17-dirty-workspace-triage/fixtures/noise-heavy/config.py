"""Application configuration module."""
import os

# BUG: timeout is 5 seconds — should be 30
API_TIMEOUT = 5
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0

def get_timeout() -> int:
    return int(os.environ.get("API_TIMEOUT", API_TIMEOUT))

def get_max_retries() -> int:
    return int(os.environ.get("MAX_RETRIES", MAX_RETRIES))
