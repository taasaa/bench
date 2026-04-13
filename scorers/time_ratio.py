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
    SYSTEM_DEFAULT_BUDGETS,
    RatioSource,
    TaskBudget,
)


@scorer(metrics=[mean()])
def time_ratio_scorer(
    baseline_store: BaselineStore | None = None,
    task_budget: TaskBudget | None = None,
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

    def _resolve_reference(task_id: str, model_id: str) -> tuple[float, RatioSource, str | None]:
        # Tier 1: Baseline store
        if baseline_store is not None:
            baseline = baseline_store.load(task_id, model_id)
            if baseline is not None and baseline.valid_for_reference:
                return baseline.latency_seconds, RatioSource.BASELINE, baseline.model_id

        # Tier 2: Task budget
        if task_budget is not None and task_budget.latency_seconds is not None:
            return float(task_budget.latency_seconds), RatioSource.TASK_BUDGET, None

        # Tier 3: System default
        return SYSTEM_DEFAULT_BUDGETS["latency_seconds"], RatioSource.SYSTEM_DEFAULT, None

    async def score(state: TaskState, target: Target) -> Score:
        # bench_working_time injected by bench run CLI into Task metadata
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

        reference_seconds, source, ref_model = _resolve_reference(task_id, model_id)

        # Noise floor: suppress if min(reference, actual) < noise_floor
        # Applies per-sample. Multi-sample means average out the noise.
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

        # Compute ratio
        raw_ratio = reference_seconds / actual_seconds

        # For MEAN: floor avoids log(0). Actual ratio unfloored.
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
