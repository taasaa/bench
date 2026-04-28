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

from bench_cli.pricing.litellm_config import resolve_openrouter_id
from bench_cli.pricing.model_aliases import PriceInfo
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
            or_model_id = resolve_openrouter_id(model_alias)
            if or_model_id is None:
                return None, None, False, None
            try:
                price_info = _price_info(or_model_id)
            except CacheMiss:
                return None, or_model_id, False, None
            except Exception:
                return None, or_model_id, False, None
            is_free = price_info.is_free
            return price_info.cost_per_sample(inp, out), or_model_id, is_free, None

        # Smart-router / multi-model: dict of {tier_name: usage}
        total_cost = 0.0
        has_any_cost = False
        is_free = False
        tier_breakdown: dict[str, dict] = {}
        for tier_name, tier_usage in usage.items():
            tier_alias = f"openai/{tier_name}"
            or_id = resolve_openrouter_id(tier_alias)
            if or_id is None:
                continue
            try:
                price_info = _price_info(or_id)
            except CacheMiss:
                continue
            except Exception:
                continue
            inp, out = _extract_tokens(tier_usage)
            tier_cost = price_info.cost_per_sample(inp, out)
            total_cost += tier_cost
            has_any_cost = True
            if price_info.is_free:
                is_free = True
            tier_breakdown[tier_name] = {
                "model": or_id,
                "input_tokens": inp,
                "output_tokens": out,
                "cost_usd": tier_cost,
            }
        if has_any_cost:
            return total_cost, None, is_free, tier_breakdown
        return None, None, False, None

    # Single ModelUsage object (standard single-model case)
    inp, out = _extract_tokens(usage)
    or_model_id = resolve_openrouter_id(model_alias)
    if or_model_id is None:
        return None, None, False, None
    try:
        price_info = _price_info(or_model_id)
    except CacheMiss:
        return None, or_model_id, False, None
    except Exception:
        return None, or_model_id, False, None
    is_free = price_info.is_free
    return price_info.cost_per_sample(inp, out), or_model_id, is_free, None


@scorer(metrics=[mean()])
def price_ratio_scorer(
    task_budget: TaskBudgetType | None = None,
) -> None:
    """Score cost via price ratio.

    Args:
        task_budget: Per-task budget with optional reference_cost_usd.
    """

    async def score(state: TaskState, target: Target) -> Score:
        usage = state.output.usage if state.output else None

        actual_cost, _, is_free, tier_breakdown = _resolve_and_price(str(state.model), usage)

        if actual_cost is None:
            return Score(
                value=float("nan"),
                explanation="cost_ratio=N/A, note=price unavailable",
                metadata={
                    "pillar": "cost",
                    "cost_ratio": None,
                    "actual_cost_usd": None,
                    "reference_cost_usd": None,
                    "is_free": False,
                    "anomaly": True,
                    "tier_breakdown": tier_breakdown,
                },
            )

        # Free model shortcut
        if is_free:
            return Score(
                value=float("inf"),
                explanation=f"cost_ratio=inf, actual_cost=$0.00 (FREE)",
                metadata={
                    "pillar": "cost",
                    "cost_ratio": None,
                    "actual_cost_usd": 0.0,
                    "reference_cost_usd": None,
                    "is_free": True,
                    "anomaly": False,
                    "tier_breakdown": tier_breakdown,
                },
            )

        # Resolve reference cost
        reference_cost: float | None = None
        if task_budget is not None and task_budget.reference_cost_usd is not None:
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
