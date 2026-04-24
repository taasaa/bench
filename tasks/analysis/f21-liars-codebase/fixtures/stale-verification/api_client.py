"""API client for external service."""

import os

import httpx


def call_external_api(endpoint: str, data: dict) -> dict:
    """Call external API with validated API key."""
    api_key = os.environ.get("API_KEY", "")
    # BUG: no validation of API key — empty string passes through
    response = httpx.post(
        f"https://external.example.com/{endpoint}",
        json=data,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return response.json()


def batch_call(endpoints: list[str]) -> list[dict]:
    """Call multiple endpoints. Uses async for performance."""
    # BUG: synchronous calls in a loop — not async, N+1 pattern
    results = []
    for endpoint in endpoints:
        results.append(call_external_api(endpoint, {}))
    return results
