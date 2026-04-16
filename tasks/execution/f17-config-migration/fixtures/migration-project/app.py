"""App using python-dotenv for config."""
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("API_KEY", "")
API_SECRET = os.environ.get("API_SECRET", "")
BASE_URL = os.environ.get("BASE_URL", "https://api.example.com")

def get_credentials():
    return {"key": API_KEY, "secret": API_SECRET, "base_url": BASE_URL}
