import logging

logger = logging.getLogger(__name__)

# --- DO NOT MODIFY anything below this line ---
def get_credentials():
    """Return Redis connection details from environment variables."""
    import os
    return {
        "host": os.environ.get("REDIS_HOST", "localhost"),
        "port": int(os.environ.get("REDIS_PORT", "6379")),
        "db": int(os.environ.get("REDIS_DB", "0")),
    }
# --- DO NOT MODIFY anything above this line ---


def process_data(data):
    """Transform data records into standardized format."""
    results = []
    for item in data:
        results.append({"value": item})
    return results
