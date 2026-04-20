"""Application configuration module."""
import os

# Timeout for API calls
API_TIMEOUT = 5  # seconds — this was fine for dev but breaks in prod
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
# Pool size for connection pool
POOL_SIZE = 10
# Circuit breaker threshold
CIRCUIT_BREAKER_THRESHOLD = 5


def get_timeout() -> int:
    return int(os.environ.get("API_TIMEOUT", API_TIMEOUT))


def get_max_retries() -> int:
    return int(os.environ.get("MAX_RETRIES", MAX_RETRIES))


def get_pool_size() -> int:
    return int(os.environ.get("POOL_SIZE", POOL_SIZE))


def get_circuit_breaker_threshold() -> int:
    return int(os.environ.get("CIRCUIT_BREAKER_THRESHOLD", CIRCUIT_BREAKER_THRESHOLD))
