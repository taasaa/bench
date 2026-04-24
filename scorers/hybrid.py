"""Hybrid scorer: combines verify_sh + llm_judge into weighted correctness score.

Produces a single Score object with value = weighted mean of both sub-scores.
Sub-scores stored in metadata for compare.py verbose display and diagnostics.

Weights default to verify_sh=0.7, judge=0.3 (deterministic checks favored).
Supports verify_weight=0 for pure judge fallback and judge_weight=0 for pure
verify fallback.
"""

from __future__ import annotations

from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState


@scorer(metrics=[mean()])
def hybrid_scorer(
    verify_weight: float = 0.7,
    judge_weight: float = 0.3,
    judge_model: str = "openai/judge",
) -> None:
    """Score correctness using both verify_sh AND llm_judge with weighted combination.

    Args:
        verify_weight: Weight for verify_sh score (default 0.7).
        judge_weight: Weight for llm_judge score (default 0.3).
        judge_model: Model string for the judge (default: openai/judge).
    """
    # Import scorers at factory time to avoid circular imports
    from scorers.llm_judge import llm_judge
    from scorers.verify_sh import verify_sh

    v_scorer = verify_sh()
    j_scorer = llm_judge(judge_model=judge_model)

    async def score(state: TaskState, target: Target) -> Score:
        # Run both scorers
        v_result = await v_scorer(state, target)
        j_result = await j_scorer(state, target)

        v_val = v_result.value if v_result.value is not None else 0.0
        j_val = j_result.value if j_result.value is not None else 0.0

        # Weighted combination
        total_weight = verify_weight + judge_weight
        if total_weight == 0:
            combined = 0.0
        else:
            combined = (verify_weight * v_val + judge_weight * j_val) / total_weight

        return Score(
            value=combined,
            explanation=(
                f"hybrid_correctness={combined:.2f} "
                f"(verify={v_val:.2f}x{verify_weight}, judge={j_val:.2f}x{judge_weight})\n"
                f"--- verify_sh ---\n{v_result.explanation}\n"
                f"--- llm_judge ---\n{j_result.explanation}"
            ),
            metadata={
                "pillar": "correctness",
                "scorer_type": "hybrid",
                "verify_sh_score": v_val,
                "llm_judge_score": j_val,
                "verify_weight": verify_weight,
                "judge_weight": judge_weight,
                "verify_sh_metadata": v_result.metadata,
                "llm_judge_metadata": j_result.metadata,
            },
        )

    return score
