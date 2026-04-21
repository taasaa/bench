"""App using config module."""
from config import get_config


def app_info():
    cfg = get_config()
    return f"Running on port {cfg['port']}, debug={cfg['debug']}, max_conn={cfg['max_connections']}"
