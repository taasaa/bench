"""Config module using os.environ.get with defaults — NO .env file exists."""
import os


API_KEY = os.environ.get("API_KEY", "dev-key-12345")
BASE_URL = os.environ.get("BASE_URL", "https://api.example.com")
TIMEOUT = int(os.environ.get("TIMEOUT", "30"))
RETRY_COUNT = int(os.environ.get("RETRY_COUNT", "3"))
ENABLE_CACHING = os.environ.get("ENABLE_CACHING", "true").lower() == "true"


def get_settings():
    return {
        "api_key": API_KEY,
        "base_url": BASE_URL,
        "timeout": TIMEOUT,
        "retry_count": RETRY_COUNT,
        "enable_caching": ENABLE_CACHING,
    }
