"""HTTP client wrapper with retry logic."""

import httpx
from config import get_max_retries, get_timeout


class HttpClient:
    """Async HTTP client with automatic retries and timeout handling."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=get_timeout(),
        )

    async def get(self, path: str) -> dict:
        """Send GET request with retry logic."""
        retries = get_max_retries()
        last_error = None
        for attempt in range(retries):
            try:
                response = await self._client.get(path)
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < retries - 1:
                    continue
        raise last_error

    async def post(self, path: str, data: dict) -> dict:
        """Send POST request with retry logic."""
        retries = get_max_retries()
        last_error = None
        for attempt in range(retries):
            try:
                response = await self._client.post(path, json=data)
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < retries - 1:
                    continue
        raise last_error

    async def close(self):
        await self._client.aclose()
