"""Database module using python-dotenv."""
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")
POOL_SIZE = int(os.environ.get("POOL_SIZE", "10"))

def get_db():
    return {"url": DATABASE_URL, "pool_size": POOL_SIZE}
