"""PriceRatioScorer: cost-aware scoring for the cost pillar.

Ratio = reference_cost_usd / actual_cost_usd

Interpretation:
  ratio > 1.0 → cheaper than reference (more cost-efficient)
  ratio = 1.0 → at reference cost
  ratio < 1.0 → more expensive than reference (less cost-efficient)

Soft stop on CacheMiss: returns Score(value=NaN) with anomaly=True.
Free models (price=0): returns Score(value=inf) with is_free=True.
"""

from __future__ import annotations

from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState

from bench_cli.pricing.model_aliases import PriceInfo, resolve_alias

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


def _extract_tokens(usage) -> tuple[int, int]:
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


@scorer(metrics=[mean()])
def price_ratio_scorer(
    task_budget: TaskBudgetType | None = None,
) -> None:
    """Score cost via price ratio.

    Args:
        task_budget: Per-task budget with optional reference_cost_usd.
    """

    async def score(state: TaskState, target: Target) -> Score:
        # Extract token counts
        input_tokens = 0
        output_tokens = 0
        if state.output and state.output.usage:
            input_tokens, output_tokens = _extract_tokens(state.output.usage)

        # Resolve model → KiloCode ID → price
        model_alias = (
            state.metadata.get("model", str(state.model))
            if state.metadata
            else str(state.model)
        )
        kilo_model_id = resolve_alias(model_alias)

        if kilo_model_id is None:
            return Score(
                value=float("nan"),
                explanation="cost_ratio=N/A, note=unknown model alias",
                metadata={
                    "pillar": "cost",
                    "cost_ratio": None,
                    "actual_cost_usd": None,
                    "reference_cost_usd": None,
                    "is_free": False,
                    "anomaly": True,
                },
            )

        # Fetch price from cache (singleton, no per-sample re-reads)
        try:
            price_info = _price_info(kilo_model_id)
        except CacheMiss:
            return Score(
                value=float("nan"),
                explanation="cost_ratio=N/A, note=price unavailable (cache miss)",
                metadata={
                    "pillar": "cost",
                    "cost_ratio": None,
                    "actual_cost_usd": None,
                    "reference_cost_usd": None,
                    "is_free": False,
                    "anomaly": True,
                },
            )
        except Exception:
            return Score(
                value=float("nan"),
                explanation="cost_ratio=N/A, note=price lookup failed",
                metadata={
                    "pillar": "cost",
                    "cost_ratio": None,
                    "actual_cost_usd": None,
                    "reference_cost_usd": None,
                    "is_free": False,
                    "anomaly": True,
                },
            )

        # Compute actual cost
        actual_cost = price_info.cost_per_sample(input_tokens, output_tokens)

        # Free model shortcut
        if price_info.is_free:
            return Score(
                value=float("inf"),
                explanation=f"cost_ratio=inf, actual_cost=$0.00 (FREE), "
                f"input_tokens={input_tokens}, output_tokens={output_tokens}",
                metadata={
                    "pillar": "cost",
                    "cost_ratio": None,
                    "actual_cost_usd": 0.0,
                    "reference_cost_usd": None,
                    "is_free": True,
                    "anomaly": False,
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
                explanation=(
                    f"cost_ratio=N/A, actual_cost=${actual_cost:.6f}, "
                    f"note=no reference cost set"
                ),
                metadata={
                    "pillar": "cost",
                    "cost_ratio": None,
                    "actual_cost_usd": actual_cost,
                    "reference_cost_usd": None,
                    "is_free": False,
                    "anomaly": False,
                },
            )

        # Compute cost ratio
        cost_ratio = reference_cost / actual_cost if actual_cost > 0 else float("nan")

        explanation = (
            f"cost_ratio={cost_ratio:.3f}, actual_cost=${actual_cost:.6f}, "
            f"reference_cost=${reference_cost:.6f}, "
            f"input_tokens={input_tokens}, output_tokens={output_tokens}"
        )

        return Score(
            value=cost_ratio,
            explanation=explanation,
            metadata={
                "pillar": "cost",
                "cost_ratio": cost_ratio,
                "actual_cost_usd": actual_cost,
                "reference_cost_usd": reference_cost,
                "is_free": False,
                "anomaly": False,
            },
        )

    return score
