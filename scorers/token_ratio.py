"""TokenRatioScorer: unbounded ratio scoring for efficiency pillar.

Ratio = reference_output_tokens / actual_total_tokens

Interpretation:
  ratio > 1.0 → used fewer tokens than reference (more efficient)
  ratio = 1.0 → at reference
  ratio < 1.0 → used more tokens than reference (less efficient)
  No cap — extreme inefficiency is real signal (shown as <0.01 in display).

Reference resolution priority:
  1. Baseline store (highest fidelity — measured run)
  2. TaskBudget.output_tokens (author-specified)
  3. SYSTEM_DEFAULT_BUDGETS["output_tokens"] (scaffolding)
"""

from __future__ import annotations

from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState

from scorers.baseline_store import BaselineStore
from scorers.protocol import (
    LOOP_MESSAGE_THRESHOLD,
    MIN_RATIO_FLOOR,
    SYSTEM_DEFAULT_BUDGETS,
    RatioSource,
    TaskBudget,
)


@scorer(metrics=[mean()])
def token_ratio_scorer(
    baseline_store: BaselineStore | None = None,
    task_budget: TaskBudget | None = None,
) -> None:
    """Score efficiency via unbounded token ratio.

    Args:
        baseline_store: Optional BaselineStore for reference resolution.
                       If None, falls back to task_budget → system default.
        task_budget: Per-task budget override. Any None field falls through
                     to the next tier in the resolution chain.
    """

    def _resolve_reference(task_id: str, model_id: str) -> tuple[float, RatioSource, str | None]:
        """Resolve reference tokens and source for a (task, model) pair.

        Returns (reference_tokens, source, reference_model).
        """
        # Tier 1: Baseline store
        if baseline_store is not None:
            baseline = baseline_store.load(task_id, model_id)
            if baseline is not None and baseline.valid_for_reference:
                return float(
                    baseline.output_tokens or baseline.total_tokens,
                ), RatioSource.BASELINE, baseline.model_id

        # Tier 2: Task budget
        if task_budget is not None and task_budget.output_tokens is not None:
            return float(task_budget.output_tokens), RatioSource.TASK_BUDGET, None

        # Tier 3: System default
        return SYSTEM_DEFAULT_BUDGETS["output_tokens"], RatioSource.SYSTEM_DEFAULT, None

    async def score(state: TaskState, target: Target) -> Score:
        actual_tokens = state.token_usage  # total tokens only (no input/output split in TaskState)

        # Extract task_id from metadata or fallback to sample_id
        task_id = state.metadata.get("task_name", str(state.sample_id))
        model_id = str(state.model)

        reference_tokens, source, ref_model = _resolve_reference(task_id, model_id)

        # Compute ratio
        raw_ratio = reference_tokens / actual_tokens if actual_tokens > 0 else MIN_RATIO_FLOOR

        # Loop detection heuristic: too many messages suggests re-reading/looping
        # (Cannot use input/output ratio — TaskState only exposes total tokens)
        message_count = len(state.messages)
        potential_loop = message_count > LOOP_MESSAGE_THRESHOLD

        # For MEAN computation: floor to avoid log(0). Actual ratio NOT floored.
        ratio_for_mean = max(MIN_RATIO_FLOOR, raw_ratio)

        # Build explanation
        loop_note = " ⚇" if potential_loop else ""
        explanation = (
            f"efficiency_ratio={raw_ratio:.3f}{loop_note}, "
            f"actual_total_tokens={actual_tokens}, reference_tokens={int(reference_tokens)}, "
            f"reference_source={source.value}"
        )
        if ref_model:
            explanation += f", reference_model={ref_model}"

        return Score(
            value=ratio_for_mean,
            explanation=explanation,
            metadata={
                "pillar": "efficiency",
                "ratio": raw_ratio,  # actual ratio (unfloored for display)
                "actual_total_tokens": actual_tokens,
                "actual_input_tokens": None,  # unavailable — TaskState.token_usage is total only
                "reference_tokens": int(reference_tokens),
                "reference_source": source.value,
                "reference_model": ref_model,
                "potential_loop": potential_loop,
                "message_count": message_count,
                "loop_threshold": LOOP_MESSAGE_THRESHOLD,
            },
        )

    return score
