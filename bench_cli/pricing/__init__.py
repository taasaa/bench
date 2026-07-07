"""Pricing infrastructure for bench cost scoring."""

from bench_cli.pricing.litellm_config import (
    get_litellm_market_price,
    is_managed_model,
    resolve_market_price,
    resolve_openrouter_id,
)
from bench_cli.pricing.model_aliases import (
    MODEL_ALIAS_MAP,
    PriceInfo,
    is_free_model,
    resolve_alias,
)
from bench_cli.pricing.price_cache import (
    CacheMiss,
    OpenRouterCache,
    fetch_and_cache_prices,
    get_price,
)


def reconstruct_cost_from_usage(
    model_alias: str | None,
    sample_model_usage: dict | None,
    cost_usd: float | None,
    or_id: str | None = None,
) -> float | None:
    """Reconstruct actual_cost_usd from token counts × market price.

    Used to backfill the cost for samples where the scorer's stored
    `actual_cost_usd` is missing or 0 (typical for old free-model logs, where
    the pre-fix scorer hard-coded $0). The cost pillar MUST reflect the
    default paid-tier price regardless of how the user accessed the model,
    so we reconstruct whenever we have token counts and a market price.

    Callers with only the recorded OpenRouter id (e.g. card regen from logs)
    should pass `or_id` rather than `model_alias`. The pricing resolver
    consults the LiteLLM config's reverse-key map (OR id → price) FIRST, so
    the OR id path is preferred for log-driven reconstruction.

    Returns:
        - The original `cost_usd` if it's already a real value (>1e-6).
        - The reconstructed cost if `cost_usd` is None/0 and reconstruction is possible.
        - The original `cost_usd` (None/0) if reconstruction isn't possible —
          callers should treat this as an anomaly (display "--"), NOT as "FREE".
    """
    # Already have a real cost — keep it.
    if cost_usd is not None and cost_usd > 1e-6:
        return cost_usd
    if not sample_model_usage:
        return cost_usd

    market_price = resolve_market_price(alias=model_alias, or_id=or_id)
    if market_price is None:
        return cost_usd

    # Pick the primary model's usage. Filter out judge entries (hybrid
    # scoring adds `openai/judge` to model_usage) so the remaining entry is
    # always the model we're scoring cost for. Then prefer alias/or_id match
    # over single-entry fallback.
    non_judge = {
        k: v for k, v in sample_model_usage.items() if "judge" not in k.lower()
    }
    if not non_judge:
        return cost_usd

    primary = None
    if model_alias and model_alias in non_judge:
        primary = non_judge[model_alias]
    elif or_id and or_id in non_judge:
        primary = non_judge[or_id]
    elif len(non_judge) == 1:
        primary = next(iter(non_judge.values()))
    else:
        return cost_usd  # ambiguous; don't guess
    inp_price, out_price = market_price
    inp = getattr(primary, "input_tokens", 0) or 0
    out = getattr(primary, "output_tokens", 0) or 0
    return (inp * inp_price + out * out_price) / 1_000_000


__all__ = [
    "MODEL_ALIAS_MAP",
    "CacheMiss",
    "OpenRouterCache",
    "PriceInfo",
    "fetch_and_cache_prices",
    "get_litellm_market_price",
    "get_price",
    "is_free_model",
    "is_managed_model",
    "reconstruct_cost_from_usage",
    "resolve_alias",
    "resolve_market_price",
    "resolve_openrouter_id",
]
