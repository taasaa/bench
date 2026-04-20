"""Application configuration module."""
import os


# BUG: timeout is 5 seconds — too short for production API calls
# Should be 30 seconds.
API_TIMEOUT = 5
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
# BUG: debug mode should be False in production
DEBUG = True


def get_timeout() -> int:
    return int(os.environ.get("API_TIMEOUT", API_TIMEOUT))


def get_max_retries() -> int:
    return int(os.environ.get("MAX_RETRIES", MAX_RETRIES))


def is_debug() -> bool:
    return bool(os.environ.get("DEBUG", str(DEBUG)))
