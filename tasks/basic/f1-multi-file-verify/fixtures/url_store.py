"""URL shortener store module."""

import hashlib
from typing import Optional


class URLStore:
    """Store short URL → long URL mappings in memory."""

    def __init__(self):
        self._urls = {}  # short_code -> long_url

    def add(self, long_url: str) -> str:
        """Add a URL and return its short code."""
        short_code = hashlib.md5(long_url.encode()).hexdigest()[:8]
        self.urls[short_code] = long_url  # BUG: should be self._urls
        return short_code

    def get(self, short_code: str) -> Optional[str]:
        """Look up a URL by its short code."""
        return self.urls.get(short_code)  # BUG: should be self._urls

    def remove(self, short_code: str) -> bool:
        """Remove a short URL mapping. Returns True if found."""
        if short_code in self.urls:  # BUG: should be self._urls
            del self.urls[short_code]  # BUG: should be self._urls
            return True
        return False

    def count(self) -> int:
        """Return the number of stored URLs."""
        return len(self._urls)
