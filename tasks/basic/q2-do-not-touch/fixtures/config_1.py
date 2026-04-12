import logging

logger = logging.getLogger(__name__)

# --- DO NOT MODIFY anything below this line ---
def get_credentials():
    """Return database credentials from environment variables."""
    import os
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }
# --- DO NOT MODIFY anything above this line ---


def process_data(data):
    """Process raw data records. Currently just returns them unchanged."""
    return data
