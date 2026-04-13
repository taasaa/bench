"""TimeRatioScorer: unbounded ratio scoring for latency pillar.

Ratio = reference_seconds / actual_seconds

Reads bench_working_time from state.metadata (injected by bench run CLI).
Noise floor suppresses single-sample runs below the threshold to avoid
API jitter dominating the signal.

Reference resolution priority (same as TokenRatioScorer):
  1. Baseline store → 2. TaskBudget → 3. SYSTEM_DEFAULT_BUDGETS
"""

from __future__ import annotations

from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState

from scorers.baseline_store import BaselineStore
from scorers.protocol import (
    DEFAULT_NOISE_FLOOR,
    MIN_RATIO_FLOOR,
    RatioSource,
    resolve_baseline_reference,
)
from scorers.protocol import TaskBudget as TaskBudgetType


@scorer(metrics=[mean()])
def time_ratio_scorer(
    baseline_store: BaselineStore | None = None,
    task_budget: TaskBudgetType | None = None,
) -> None:
    """Score latency via unbounded ratio.

    Args:
        baseline_store: Optional BaselineStore for reference resolution.
        task_budget: Per-task budget. noise_floor_seconds field overrides
                     DEFAULT_NOISE_FLOOR if set.
    """

    def _noise_floor() -> float:
        if task_budget is not None and task_budget.noise_floor_seconds is not None:
            return task_budget.noise_floor_seconds
        return DEFAULT_NOISE_FLOOR

    async def score(state: TaskState, target: Target) -> Score:
        actual_seconds = state.metadata.get("bench_working_time") if state.metadata else None
        if actual_seconds is None:
            return Score(
                value=1.0,
                explanation=(
                    "latency_ratio=1.00, "
                    "note=bench_working_time not in metadata, using 1.0"
                ),
                metadata={
                    "pillar": "latency",
                    "ratio": None,
                    "actual_seconds": None,
                    "suppressed": False,
                },
            )

        actual_seconds = float(actual_seconds)
        task_id = state.metadata.get("task_name", str(state.sample_id))
        model_id = str(state.model)
        noise_floor = _noise_floor()

        # Tier 1: baseline
        reference_seconds, source, ref_model = resolve_baseline_reference(
            baseline_store, task_id, model_id, "latency_seconds"
        )
        # Tier 2: task budget override
        if task_budget is not None and task_budget.latency_seconds is not None:
            reference_seconds = float(task_budget.latency_seconds)
            source = RatioSource.TASK_BUDGET
            ref_model = None

        if min(reference_seconds, actual_seconds) < noise_floor:
            return Score(
                value=None,
                explanation=(
                    f"latency_ratio=suppressed, actual_seconds={actual_seconds:.1f}, "
                    f"reference_seconds={reference_seconds:.1f}, noise_floor={noise_floor:.1f}s, "
                    f"note=ratio unreliable (below noise floor)"
                ),
                metadata={
                    "pillar": "latency",
                    "ratio": None,
                    "actual_seconds": actual_seconds,
                    "reference_seconds": reference_seconds,
                    "reference_source": source.value,
                    "noise_floor": noise_floor,
                    "suppressed": True,
                },
            )

        raw_ratio = reference_seconds / actual_seconds
        ratio_for_mean = max(MIN_RATIO_FLOOR, raw_ratio)

        explanation = (
            f"latency_ratio={raw_ratio:.3f}, actual_seconds={actual_seconds:.1f}, "
            f"reference_seconds={reference_seconds:.1f}, reference_source={source.value}"
        )
        if ref_model:
            explanation += f", reference_model={ref_model}"

        return Score(
            value=ratio_for_mean,
            explanation=explanation,
            metadata={
                "pillar": "latency",
                "ratio": raw_ratio,
                "actual_seconds": actual_seconds,
                "reference_seconds": reference_seconds,
                "reference_source": source.value,
                "reference_model": ref_model,
                "noise_floor": noise_floor,
                "suppressed": False,
            },
        )

    return score
