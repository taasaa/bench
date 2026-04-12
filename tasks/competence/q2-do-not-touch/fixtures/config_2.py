import logging

logger = logging.getLogger(__name__)

# --- DO NOT MODIFY anything below this line ---
def get_credentials():
    """Return API credentials from environment variables."""
    import os
    return {
        "api_key": os.environ.get("API_KEY", ""),
        "api_secret": os.environ.get("API_SECRET", ""),
        "base_url": os.environ.get("API_BASE_URL", "https://api.example.com"),
    }
# --- DO NOT MODIFY anything above this line ---


def process_data(data):
    """Filter and clean data records. Currently returns all records."""
    return [r for r in data]
