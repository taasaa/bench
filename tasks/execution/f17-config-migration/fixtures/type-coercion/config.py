"""Config module with type coercion — int() and bool() wrapping os.environ.get."""
import os
from dotenv import load_dotenv

load_dotenv()

PORT = int(os.environ.get("PORT", "8080"))
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
MAX_CONNECTIONS = int(os.environ.get("MAX_CONNECTIONS", "10"))
API_KEY = os.environ.get("API_KEY", "")


def get_config():
    return {
        "port": PORT,
        "debug": DEBUG,
        "max_connections": MAX_CONNECTIONS,
        "api_key": API_KEY,
    }
