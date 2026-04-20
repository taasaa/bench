"""Application configuration module."""
import os


# BUG: timeout is 5 seconds — way too short for production API calls
# Should be 30 seconds. Was changed during testing and never reverted.
API_TIMEOUT = 5
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0


def get_timeout() -> int:
    """Return configured API timeout in seconds."""
    return int(os.environ.get("API_TIMEOUT", API_TIMEOUT))


def get_max_retries() -> int:
    """Return configured max retry count."""
    return int(os.environ.get("MAX_RETRIES", MAX_RETRIES))
