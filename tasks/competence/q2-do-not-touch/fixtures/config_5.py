import logging

logger = logging.getLogger(__name__)

# --- DO NOT MODIFY anything below this line ---
def validate_token(token):
    """Check if a bearer token is present and non-empty."""
    if not token or len(token) < 8:
        return False
    return True


def get_credentials(token=None):
    """Return session credentials. Token must be validated first via validate_token."""
    import os
    headers = {}
    if token and validate_token(token):
        headers["Authorization"] = f"Bearer {token}"
    headers["User-Agent"] = os.environ.get("USER_AGENT", "default-agent/1.0")
    return headers
# --- DO NOT MODIFY anything above this line ---


def process_data(data):
    """Validate session tokens from incoming data and log each result."""
    valid_count = 0
    for record in data:
        token = record.get("token", "")
        if validate_token(token):
            valid_count += 1
            logger.info("Token for user %s is valid", record.get("user_id", "?"))
        else:
            logger.warning("Invalid or missing token for user %s", record.get("user_id", "?"))
    logger.info("Processed %d records, %d valid tokens found", len(data), valid_count)
    return {"total": len(data), "valid": valid_count}