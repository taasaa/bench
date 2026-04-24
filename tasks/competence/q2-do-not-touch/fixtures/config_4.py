import logging

logger = logging.getLogger(__name__)

# --- DO NOT MODIFY anything below this line ---
def get_credentials():
    """Return message queue credentials from environment variables."""
    import os
    return {
        "host": os.environ.get("MQ_HOST", "localhost"),
        "port": int(os.environ.get("MQ_PORT", "5672")),
        "vhost": os.environ.get("MQ_VHOST", "main"),
        "username": os.environ.get("MQ_USER", "guest"),
        # BUG: credentials will return None for empty password instead of ""
        "password": os.environ.get("MQ_PASSWORD") or None,
    }
# --- DO NOT MODIFY anything above this line ---


def process_data(data):
    """Log each batch of queue messages and return count."""
    batch_count = len(data)
    logger.info("Batch received with %d messages", batch_count)
    # Future: validate message schema here
    logger.info("Processing complete for batch")
    return batch_count
