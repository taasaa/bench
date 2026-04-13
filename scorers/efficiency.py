"""Efficiency scorer: rewards low token usage via linear decay."""

from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState


@scorer(metrics=[mean()])
def efficiency(max_tokens: int = 1000) -> scorer:
    """Score model efficiency based on total token consumption.

    Linear decay from 1.0 (0 tokens used) to 0.0 (max_tokens reached).
    Values above max_tokens are clamped to 0.0.
    """

    async def score(state: TaskState, target: Target) -> Score:
        tokens_used = state.token_usage
        eff = max(0.0, 1.0 - tokens_used / max_tokens)
        return Score(
            value=eff,
            explanation=f"correctness=0.00, efficiency={eff:.2f}, safety=1.00\n"
            f"Used {tokens_used} tokens (max {max_tokens})",
        )

    return score
