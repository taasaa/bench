"""instruction_overhead scorer: measures token cost of instructions vs behavior improvement.

This scorer quantifies the efficiency of instruction density. It is a harness A/B
testing tool — run the same task with Harness A (verbose CLAUDE.md) vs Harness B
(minimal CLAUDE.md) and compare instruction_overhead scores.

Key insight (arxiv 2602.15228, Humanlayer): models stop reading instructions after
~500-800 tokens. Beyond ~7 discrete rules, retention drops. Adding instructions
beyond the threshold can DECREASE performance. The instruction_overhead_scorer
makes this measurable.

Metrics:
  - overhead_ratio: (task_instruction_tokens) / (reference_instruction_tokens)
  - completion_density: output_tokens / reference_output_tokens
  - efficiency_ratio: (correctness_delta) / (instruction_overhead + token_delta)

Usage: Add to any agent task as efficiency scorer alongside correctness + token_ratio.
The composite score tells you whether added instructions justified their token cost.

Example output in Score.metadata:
    {
        "pillar": "efficiency",
        "instruction_tokens": 3200,
        "completion_tokens": 1840,
        "overhead_ratio": 2.4,      # 2.4x more instruction tokens than reference
        "completion_density": 0.58,  # used 58% of reference completion tokens
        "efficiency_ratio": 0.35,    # low = instruction overhead not worth it
        "calibrated": true,
    }

See doc/EVAL-TASKS.md Part III §U6.
"""

from __future__ import annotations

from dataclasses import dataclass

from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState


@dataclass
class InstructionOverheadMetrics:
    instruction_tokens: int
    completion_tokens: int
    overhead_ratio: float | None  # None if no reference
    completion_density: float | None  # None if no reference
    efficiency_ratio: float | None  # None if not calibrated


def _extract_token_metrics(state: TaskState) -> InstructionOverheadMetrics:
    """Extract instruction and completion token counts from Inspect event log.

    Inspect stores token usage in state.metadata after eval completes:
    - "input_tokens": instruction/prompt tokens (from model input)
    - "output_tokens": completion tokens (from model output)
    - "total_tokens": total tokens

    We use a rolling estimate when metadata isn't populated:
    - instruction_tokens: ~len(input_text) / 4 chars-per-token
    - completion_tokens: use state.metadata or estimate from completion text
    """
    metadata = state.metadata or {}

    # Try to get actual token counts from Inspect metadata
    input_tokens: int | None = metadata.get("input_tokens")
    output_tokens: int | None = metadata.get("output_tokens")

    if output_tokens is None:
        # Fall back to estimating from text length (rough: ~4 chars/token)
        completion_text = state.output.completion if state.output else ""
        output_tokens = max(1, len(completion_text) // 4)

    if input_tokens is None:
        # Estimate from input text
        input_text = state.input_text
        input_tokens = max(1, len(input_text) // 4)

    # Reference values from task metadata (set via dataset or task config)
    ref_instruction_tokens: int | None = metadata.get("reference_instruction_tokens")
    ref_completion_tokens: int | None = metadata.get("reference_completion_tokens")
    ref_correctness: float | None = metadata.get("reference_correctness")

    overhead_ratio: float | None = None
    completion_density: float | None = None
    efficiency_ratio: float | None = None

    if ref_instruction_tokens and ref_instruction_tokens > 0:
        overhead_ratio = input_tokens / ref_instruction_tokens

    if ref_completion_tokens and ref_completion_tokens > 0:
        # completion_density: actual completion tokens relative to reference
        completion_density = output_tokens / ref_completion_tokens

    # Compute efficiency if we have enough data
    if (
        overhead_ratio is not None
        and ref_correctness is not None
        and metadata.get("correctness") is not None
    ):
        correctness_delta = metadata["correctness"] - ref_correctness
        token_delta = abs(overhead_ratio - 1.0)
        if token_delta + abs(correctness_delta) > 0:
            efficiency_ratio = correctness_delta / (token_delta + abs(correctness_delta))

    return InstructionOverheadMetrics(
        instruction_tokens=input_tokens,
        completion_tokens=output_tokens,
        overhead_ratio=overhead_ratio,
        completion_density=completion_density,
        efficiency_ratio=efficiency_ratio,
    )


@scorer(metrics=[mean()])
def instruction_overhead_scorer(
    reference_instruction_tokens: int | None = None,
    reference_completion_tokens: int | None = None,
) -> None:
    """Score the efficiency of instruction density for harness A/B testing.

    Measures how much instruction overhead a task requires and whether that
    overhead is justified by behavior improvement.

    Metrics:
      - overhead_ratio: actual_instruction_tokens / reference_instruction_tokens
        - 1.0 = same as baseline
        - 2.0 = 2x more instruction tokens than baseline
        - 0.5 = half the instruction tokens (minimal harness)
      - completion_density: reference_completion_tokens / instruction_tokens
        - Higher = more output per instruction token (efficient)
        - Lower = verbose instructions eating into completion budget
      - efficiency_ratio: correctness_delta / overhead_delta
        - Higher = instructions justify their token cost
        - Zero or negative = instruction overhead hurts more than it helps

    Score value:
      - 1.0 if overhead_ratio <= 1.0 (efficient or minimal instructions)
      - <1.0 proportional to overhead if ratio > 1.0
      - 1.0 if not calibrated (no reference available)

    Args:
        reference_instruction_tokens: Fixed reference for all samples.
            Set this via sample.metadata["reference_instruction_tokens"] instead.
        reference_completion_tokens: Fixed reference for completion tokens.
    """
    def _score(state: TaskState, target: Target) -> Score:
        metrics = _extract_token_metrics(state)

        # Override references if provided at scorer call time
        if reference_instruction_tokens:
            if metrics.instruction_tokens > 0:
                metrics.overhead_ratio = (
                    reference_instruction_tokens / metrics.instruction_tokens
                )

        # Compute score: 1.0 if efficient, <1.0 proportional to overhead
        if metrics.overhead_ratio is not None:
            # penalize overhead beyond 1.0, reward below 1.0
            value = min(1.0, 1.0 / metrics.overhead_ratio) if metrics.overhead_ratio > 0 else 1.0
        else:
            # Uncalibrated — score 1.0 but flag as uncalibrated
            value = 1.0

        overhead_str = f"{metrics.overhead_ratio:.2f}" if metrics.overhead_ratio else "n/a"
        density_str = f"{metrics.completion_density:.2f}" if metrics.completion_density else "n/a"
        eff_str = f"{metrics.efficiency_ratio:.2f}" if metrics.efficiency_ratio else "n/a"

        explanation = (
            f"efficiency={value:.2f}\n"
            f"instruction_tokens={metrics.instruction_tokens}, "
            f"completion_tokens={metrics.completion_tokens}, "
            f"overhead_ratio={overhead_str}, "
            f"completion_density={density_str}, "
            f"efficiency_ratio={eff_str}"
        )

        return Score(
            value=value,
            explanation=explanation,
            metadata={
                "pillar": "efficiency",
                "instruction_tokens": metrics.instruction_tokens,
                "completion_tokens": metrics.completion_tokens,
                "overhead_ratio": metrics.overhead_ratio,
                "completion_density": metrics.completion_density,
                "efficiency_ratio": metrics.efficiency_ratio,
                "calibrated": metrics.overhead_ratio is not None,
            },
        )

    return _score
