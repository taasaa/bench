"""Suggest alternative OpenRouter models when a price is not found.

Used by the price gate to show users nearby options from the same provider
before blocking the eval.
"""

from __future__ import annotations

from bench_cli.pricing.price_cache import OpenRouterCache


def suggest_alternatives(openrouter_id: str, max_results: int = 8) -> list[str]:
    """Return cached OpenRouter model IDs from the same provider.

    Args:
        openrouter_id: The OpenRouter model ID that was not found (e.g.
            ``mistralai/devstral-2-123b-instruct-2512``).
        max_results: Maximum number of alternatives to return.

    Returns:
        List of model IDs from the same provider that ARE in the cache.
        Empty list if no other models from that provider are cached.
    """
    provider = _provider_from_id(openrouter_id)
    if not provider:
        return []

    cache = OpenRouterCache()
    all_prices = cache.get_all_prices()

    candidates = [
        model_id
        for model_id in all_prices
        if model_id.startswith(f"{provider}/")
        and model_id != openrouter_id
    ]
    return candidates[:max_results]


def _provider_from_id(openrouter_id: str) -> str:
    """Extract the provider prefix from an OpenRouter model ID.

    ``mistralai/devstral-2-123b-instruct-2512`` → ``mistralai``
    ``qwen/qwen3-next-80b-a3b-instruct``        → ``qwen``
    ``anthropic/claude-opus-4.7``               → ``anthropic``
    """
    parts = openrouter_id.split("/")
    return parts[0] if len(parts) >= 2 else ""
