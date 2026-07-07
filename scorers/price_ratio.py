"""PriceRatioScorer: cost-aware scoring for the cost pillar.

Ratio = reference_cost_usd / actual_cost_usd

Interpretation:
  ratio > 1.0 → cheaper than reference (more cost-efficient)
  ratio = 1.0 → at reference cost
  ratio < 1.0 → more expensive than reference (less cost-efficient)

Soft stop on CacheMiss: returns Score(value=NaN) with anomaly=True.
Free models (price=0): returns Score(value=inf) with is_free=True.

Smart-router support: when state.output.usage is a dict (multiple models ran,
e.g. routing tiers), sum costs across all entries. Each key is a tier name
(background, default, heavy, thinking) resolved via LiteLLM config at scoring time.
"""

from __future__ import annotations

from typing import Any

from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState

from bench_cli.pricing.litellm_config import (
    is_managed_model,
    resolve_market_price,
    resolve_openrouter_id,
)
from bench_cli.pricing.model_aliases import PriceInfo
from scorers.baseline_store import BaselineStore
from scorers.protocol import resolve_cost_reference
from scorers.protocol import TaskBudget as TaskBudgetType

# Late import — price_cache may not exist yet (Team A builds it).
# CacheMiss is only needed at runtime, not import time.
try:
    from bench_cli.pricing.price_cache import CacheMiss, OpenRouterCache

    # Module-level singleton — read cache once, not per-sample on the hot scoring path.
    _price_cache = OpenRouterCache()

    def _price_info(kilo_model_id: str) -> PriceInfo:
        return _price_cache.get_price(kilo_model_id)

except ImportError:

    class CacheMiss(Exception):  # type: ignore[no-redef]
        """Placeholder until price_cache.py is created."""

    def _price_info(model_id: str) -> PriceInfo:  # type: ignore[no-redef]
        raise CacheMiss(model_id)


DEFAULT_REFERENCE_COST_USD = 0.001


def _extract_tokens(usage: Any) -> tuple[int, int]:
    """Extract (input_tokens, output_tokens) from usage object.

    Handles both:
      - dict (used in test mocks): {"prompt_tokens": ..., "completion_tokens": ...}
      - ModelUsage Pydantic model (real Inspect AI): .input_tokens, .output_tokens
    """
    if isinstance(usage, dict):
        inp = usage.get("prompt_tokens", 0) or 0
        out = usage.get("completion_tokens", 0) or 0
    else:
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
    return int(inp), int(out)


def _price_from_alias(alias: str, inp: int, out: int) -> tuple[float | None, str | None, bool]:
    """Resolve alias → market price → cost. Returns (cost_usd, or_id, is_free).

    Uses `resolve_market_price` (LiteLLM config → OpenRouter cache with :free
    → paid resolution). Never returns $0 cost for a known model — a model with
    no resolvable price returns (None, or_id, False) so the caller marks the
    sample as anomalous, not as "FREE".

    `is_free` is INFORMATIONAL only — it tells callers the model is currently
    accessed free (via NIM quota or OpenRouter :free) so the card can show the
    "(currently free)" annotation. It does NOT gate the cost path, because the
    cost pillar MUST use the paid-tier market price regardless.
    """
    or_model_id = resolve_openrouter_id(alias)
    market_price = resolve_market_price(alias=alias, or_id=or_model_id)
    # Informational: is this model accessed free? Detect via :free OR id suffix
    # OR managed/local alias. Computed BEFORE pricing resolution so the flag
    # reflects the access path even when market price is found.
    is_free_access = bool(or_model_id and ":free" in or_model_id) or _alias_is_managed(alias)
    if market_price is None:
        if or_model_id is None:
            return None, None, is_free_access
        # OR id resolves but no LiteLLM price — try OpenRouter cache directly
        # (covers benchmark-only entries not in the LiteLLM proxy).
        try:
            price_info = _price_info(or_model_id)
        except Exception:
            return None, or_model_id, is_free_access
        if price_info.input_price == 0.0 and price_info.output_price == 0.0:
            # $0/$0 cache hit (typically a :free variant with no paid price
            # resolved) — caller flags anomaly, not "FREE".
            return None, or_model_id, True
        cost = price_info.cost_per_sample(inp, out)
        return cost, or_model_id, is_free_access or price_info.is_free
    input_price, output_price = market_price
    cost = (inp * input_price + out * output_price) / 1_000_000
    return cost, or_model_id, is_free_access


def _alias_is_managed(alias: str) -> bool:
    """Cheap local copy of `is_managed_model` to avoid an import cycle."""
    if alias.endswith("-local"):
        return True
    if alias in ("openai/glm-local", "openai/qwen3-coder-plus", "openai/qwen3-max"):
        return True
    return False


def _resolve_and_price(
    model_alias: str,
    usage: Any,
) -> tuple[float | None, float | None, bool, dict[str, dict] | None]:
    """Resolve model alias to OpenRouter ID, compute cost from usage.

    Returns (cost_usd, openrouter_id, is_free, tier_breakdown).
    tier_breakdown is None for non-router models; for smart-router it contains
    {tier_name: {"model": or_id, "input_tokens": N, "output_tokens": N, "cost_usd": F}}.
    """
    # Handle dict usage — distinguish old format from smart-router multi-model
    if isinstance(usage, dict):
        # Old single-model format: dict with token keys (backwards compat)
        if "prompt_tokens" in usage or "completion_tokens" in usage:
            inp = usage.get("prompt_tokens", 0) or 0
            out = usage.get("completion_tokens", 0) or 0
            return _price_from_alias(model_alias, inp, out) + (None,)

        # Smart-router / multi-model: dict of {tier_name: usage}
        total_cost = 0.0
        has_any_cost = False
        is_free = False
        tier_breakdown: dict[str, dict] = {}
        for tier_name, tier_usage in usage.items():
            tier_alias = f"openai/{tier_name}"
            inp, out = _extract_tokens(tier_usage)
            cost, or_id, free = _price_from_alias(tier_alias, inp, out)
            if cost is None or or_id is None:
                continue
            total_cost += cost
            has_any_cost = True
            if free:
                is_free = True
            tier_breakdown[tier_name] = {
                "model": or_id,
                "input_tokens": inp,
                "output_tokens": out,
                "cost_usd": cost,
            }
        if has_any_cost:
            return total_cost, None, is_free, tier_breakdown
        return None, None, False, None

    # Single ModelUsage object (standard single-model case)
    inp, out = _extract_tokens(usage)
    return _price_from_alias(model_alias, inp, out) + (None,)


def _resolve_paid_variant_price(or_model_id: str) -> PriceInfo | None:
    """For :free OpenRouter variants, resolve the paid variant's price.

    OpenRouter :free variants are promotional — the real market price is the
    same model without the :free suffix. This returns the paid variant's
    PriceInfo so the cost_ratio can reflect actual capability/price tradeoffs
    regardless of current promo status. Returns None if no paid variant found.
    """
    if ":free" not in or_model_id:
        return None
    paid_id = or_model_id.replace(":free", "")
    try:
        return _price_info(paid_id)
    except Exception:
        return None


def _score_free_model_with_paid_price(
    state: TaskState,
    model_alias: str,
    task_budget: TaskBudgetType | None,
    baseline_store: "BaselineStore | None",
) -> Score:
    """Fallback for models flagged is_free by the market-price resolver.

    `_price_from_alias` already uses `resolve_market_price`, which strips
    ":free" suffixes and consults the LiteLLM config (which we maintain at
    the paid-tier price). The only path that reaches THIS function is when
    `_price_from_alias` returned is_free=True — i.e. the market price is
    0/0 — and we still need to compute a cost ratio from the reference.

    Strategy: try the OpenRouter cache for the paid variant one more time
    (covers benchmark-only :free entries not in the LiteLLM proxy). If that
    also fails, return NaN with anomaly=True — NEVER "FREE", NEVER cost_ratio=inf.
    A model with unknown market price should render as "--" in the display,
    not as the misleading word "FREE".
    """
    from inspect_ai.scorer import Score

    or_model_id = resolve_openrouter_id(model_alias)
    paid_price = _resolve_paid_variant_price(or_model_id) if or_model_id else None

    if paid_price is None or (paid_price.input_price == 0.0 and paid_price.output_price == 0.0):
        return Score(
            value=float("nan"),
            explanation="cost_ratio=N/A, note=is_free flagged but no paid-variant price resolvable",
            metadata={
                "pillar": "cost",
                "cost_ratio": None,
                "actual_cost_usd": None,
                "reference_cost_usd": None,
                "is_free": True,
                "paid_or_id": (or_model_id or "").replace(":free", "") or None,
                "anomaly": True,
                "tier_breakdown": None,
            },
        )

    # Compute cost using paid variant's price
    usage = state.output.usage if state.output else None
    if isinstance(usage, dict) and ("prompt_tokens" in usage or "completion_tokens" in usage):
        inp = usage.get("prompt_tokens", 0) or 0
        out = usage.get("completion_tokens", 0) or 0
    elif hasattr(usage, "input_tokens"):
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
    else:
        inp, out = 0, 0

    actual_cost = paid_price.cost_per_sample(inp, out)

    # Resolve reference cost
    task_name = (state.metadata or {}).get("task_name", "") if state.metadata else ""
    reference_cost, _src, _ref = resolve_cost_reference(baseline_store, task_name)
    if reference_cost is None and task_budget is not None:
        reference_cost = task_budget.reference_cost_usd

    if reference_cost is None or actual_cost == 0:
        return Score(
            value=float("nan"),
            explanation=f"cost_ratio=N/A, actual_cost=${actual_cost:.6f} (paid price; model currently free), note={'no reference cost set' if reference_cost is None else 'zero tokens'}",
            metadata={
                "pillar": "cost",
                "cost_ratio": None,
                "actual_cost_usd": actual_cost,
                "reference_cost_usd": reference_cost,
                "is_free": True,
                "paid_or_id": or_model_id.replace(":free", "") if or_model_id else None,
                "anomaly": reference_cost is None,
                "tier_breakdown": None,
            },
        )

    cost_ratio = reference_cost / actual_cost
    return Score(
        value=cost_ratio,
        explanation=f"cost_ratio={cost_ratio:.3f}, actual_cost=${actual_cost:.6f} (paid price; model currently free), reference_cost=${reference_cost:.6f}",
        metadata={
            "pillar": "cost",
            "cost_ratio": cost_ratio,
            "actual_cost_usd": actual_cost,
            "reference_cost_usd": reference_cost,
            "is_free": True,
            "paid_or_id": or_model_id.replace(":free", "") if or_model_id else None,
            "anomaly": False,
            "tier_breakdown": None,
        },
    )


@scorer(metrics=[mean()])
def price_ratio_scorer(
    task_budget: TaskBudgetType | None = None,
    baseline_store: "BaselineStore | None" = None,
) -> None:
    """Score cost via price ratio.

    Args:
        task_budget: Per-task budget with optional reference_cost_usd.
        baseline_store: Optional BaselineStore for Tier-1 cost reference (W3b).
                       If None but a reference model is registered, one is
                       self-provisioned so task.py callers need no changes.
    """
    # W3: self-provision a store once a reference model is registered.
    import scorers.protocol as _proto
    baseline_store = _proto._maybe_provision_baseline_store(baseline_store)

    async def score(state: TaskState, target: Target) -> Score:
        usage = state.output.usage if state.output else None
        model_alias = str(state.model)

        actual_cost, _, is_free, tier_breakdown = _resolve_and_price(model_alias, usage)

        # No market price resolvable. Distinguish:
        #   - managed/local model → genuinely free, return NaN with is_free=True
        #     (display layer renders "FREE").
        #   - unknown/unpriced model → anomaly, return NaN with is_free=<informational>
        #     (display layer renders "--"). Never "FREE" for a model that
        #     should have a paid-tier price.
        if actual_cost is None:
            genuinely_free = is_managed_model(model_alias)
            return Score(
                value=float("nan"),
                explanation=(
                    "cost_ratio=N/A, note=price unavailable"
                    if not genuinely_free
                    else "cost_ratio=N/A, note=managed/local model — no market price"
                ),
                metadata={
                    "pillar": "cost",
                    "cost_ratio": None,
                    "actual_cost_usd": None,
                    "reference_cost_usd": None,
                    "is_free": genuinely_free or is_free,  # informational union
                    "anomaly": not genuinely_free,
                    "tier_breakdown": tier_breakdown,
                },
            )

        # Free model: still compute at paid-tier market price. The market-price
        # path above already does this when LiteLLM config has pricing for the
        # alias (which is the recommended setup for :free variants). The legacy
        # _score_free_model_with_paid_price fallback below only fires if the
        # alias has no LiteLLM pricing but has a :free OpenRouter id with a
        # resolvable paid variant.
        if is_free:
            return _score_free_model_with_paid_price(
                state, model_alias=model_alias, task_budget=task_budget,
                baseline_store=baseline_store,
            )

        # Resolve reference cost — Tier 1: reference-model BaselineStore (W3b),
        # Tier 2: task_budget.reference_cost_usd.
        task_name = (state.metadata or {}).get("task_name", "") if state.metadata else ""
        reference_cost, _src, _ref = resolve_cost_reference(baseline_store, task_name)
        if reference_cost is None and task_budget is not None:
            reference_cost = task_budget.reference_cost_usd

        # No reference cost — record actual cost only, skip ratio
        if reference_cost is None:
            return Score(
                value=float("nan"),
                explanation=f"cost_ratio=N/A, actual_cost=${actual_cost:.6f}, note=no reference cost set",
                metadata={
                    "pillar": "cost",
                    "cost_ratio": None,
                    "actual_cost_usd": actual_cost,
                    "reference_cost_usd": None,
                    "is_free": False,
                    "anomaly": False,
                    "tier_breakdown": tier_breakdown,
                },
            )

        # Compute cost ratio
        cost_ratio = reference_cost / actual_cost if actual_cost > 0 else float("nan")

        return Score(
            value=cost_ratio,
            explanation=f"cost_ratio={cost_ratio:.3f}, actual_cost=${actual_cost:.6f}, reference_cost=${reference_cost:.6f}",
            metadata={
                "pillar": "cost",
                "cost_ratio": cost_ratio,
                "actual_cost_usd": actual_cost,
                "reference_cost_usd": reference_cost,
                "is_free": False,
                "anomaly": False,
                "tier_breakdown": tier_breakdown,
            },
        )

    return score
