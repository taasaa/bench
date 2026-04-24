"""HTTP client wrapper with retry and circuit breaker logic."""

import httpx
from config import get_circuit_breaker_threshold, get_max_retries, get_pool_size, get_timeout


class HttpClient:
    """Async HTTP client with retries, connection pooling, and circuit breaker."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._failure_count = 0
        self._circuit_open = False
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=get_timeout(),
            limits=httpx.Limits(max_connections=get_pool_size()),
        )

    async def get(self, path: str) -> dict:
        if self._circuit_open:
            raise RuntimeError("Circuit breaker is open")
        retries = get_max_retries()
        last_error = None
        for attempt in range(retries):
            try:
                response = await self._client.get(path)
                response.raise_for_status()
                self._failure_count = 0
                return response.json()
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_error = exc
                self._failure_count += 1
                if self._failure_count >= get_circuit_breaker_threshold():
                    self._circuit_open = True
                if attempt < retries - 1:
                    continue
        raise last_error

    async def close(self):
        await self._client.aclose()
