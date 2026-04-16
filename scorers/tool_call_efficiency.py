"""tool_call_efficiency scorer: measures tool call quality from agent eval traces.

This scorer post-processes the Inspect event log from agent eval runs to extract
tool call metrics. It is a PASSIVE scorer — it does not affect the primary
correctness score, but it captures the efficiency pillar for agent harness
evaluation.

BFCL v4 (Berkeley): reasoning models call 2.2x more tools but aren't more accurate.
This scorer measures exactly that: tool_call_count, unnecessary_call_rate, and
the reference_ratio (actual / expected).

Usage: add to every agent task's scorer list alongside correctness + token_ratio + time_ratio.
See doc/EVAL-TASKS.md Part III §U5.

Example output in Score.metadata:
    {
        "pillar": "efficiency",
        "tool_call_count": 12,
        "unique_tools": ["Read", "Edit", "Bash", "Write"],
        "reference_tool_count": 8,  # from task metadata or baseline
        "reference_ratio": 1.5,     # 12/8 = 1.5x more calls than expected
        "tool_call_rate": 2.4,      # calls per minute
    }
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState


@dataclass
class ToolCallMetrics:
    tool_call_count: int
    unique_tools: list[str]
    tool_name_counts: dict[str, int]
    reference_ratio: float | None  # None if no reference
    reference_tool_count: int | None


def _extract_tool_calls(state: TaskState) -> ToolCallMetrics:
    """Extract tool call metrics from the Inspect event log.

    Inspect stores messages in state.messages. Tool calls appear as
    ChatMessageTool messages. The tool name is in message.tool_name
    and parameters are in message.content.
    """
    from inspect_ai.model import ChatMessageTool

    tool_names: list[str] = []
    for msg in state.messages:
        if isinstance(msg, ChatMessageTool):
            if msg.tool_name:
                tool_names.append(msg.tool_name)

    tool_name_counts: dict[str, int] = {}
    for name in tool_names:
        tool_name_counts[name] = tool_name_counts.get(name, 0) + 1

    unique_tools = list(dict.fromkeys(tool_names))  # preserve order, deduplicate

    # Try to get reference tool count from task metadata
    ref_count: int | None = None
    if state.metadata:
        ref_count = state.metadata.get("reference_tool_count")
        if ref_count is None:
            ref_count = state.metadata.get("reference_tools")

    ratio: float | None = None
    if ref_count and ref_count > 0:
        ratio = len(tool_names) / ref_count

    return ToolCallMetrics(
        tool_call_count=len(tool_names),
        unique_tools=unique_tools,
        tool_name_counts=tool_name_counts,
        reference_ratio=ratio,
        reference_tool_count=ref_count,
    )


@scorer(metrics=[mean()])
def tool_call_efficiency(
    reference_tool_count: int | None = None,
) -> None:
    """Score tool call efficiency for agent eval tasks.

    Extracts tool call data from the Inspect event log and produces
    efficiency metrics. This scorer does NOT affect correctness — it only
    populates the efficiency pillar for harness comparison.

    Metrics produced:
      - tool_call_count: total number of tool calls made
      - unique_tools: list of unique tool names used
      - tool_name_counts: dict of tool_name → call count
      - reference_ratio: actual_calls / reference_calls (if reference provided)
      - tool_call_rate: calls per minute (computed from state.metadata elapsed time)

    Reference tool count can be provided:
      - Per-task as `reference_tool_count=N` in the scorer call
      - Per-sample via sample.metadata["reference_tool_count"]
      - Defaults to None (no ratio computed)

    Score value: 1.0 if reference_ratio is None (no baseline),
                 min(1.0, reference_count / actual_count) if ratio available,
                 or 1.0 if actual_count <= reference_count (efficient or matches baseline).

    The value represents efficiency: ≤1.0 means efficient or at baseline,
    >1.0 means excessive calls (penalized at 1.0 to not affect correctness).

    Args:
        reference_tool_count: Optional fixed reference for all samples.
            Prefer setting it per-sample via dataset metadata.
    """
    def _score(state: TaskState, target: Target) -> Score:
        metrics = _extract_tool_calls(state)

        # Compute score: 1.0 if at or below reference, <1.0 if above
        if metrics.reference_ratio is not None:
            # penalize only if ratio > 1.0 (more calls than reference)
            value = min(1.0, 1.0 / metrics.reference_ratio) if metrics.reference_ratio > 0 else 1.0
        else:
            # No reference: score 1.0 but flag as uncalibrated
            value = 1.0

        # Build explanation with key metrics
        tool_summary = ", ".join(
            f"{name}={count}" for name, count in sorted(metrics.tool_name_counts.items())
        )
        ratio_str = f", ratio={metrics.reference_ratio:.2f}" if metrics.reference_ratio else " (no reference)"
        explanation = (
            f"efficiency={value:.2f}\n"
            f"tool_calls={metrics.tool_call_count} ({tool_summary})"
            f"{ratio_str}"
        )

        return Score(
            value=value,
            explanation=explanation,
            metadata={
                "pillar": "efficiency",
                "tool_call_count": metrics.tool_call_count,
                "unique_tools": metrics.unique_tools,
                "tool_name_counts": metrics.tool_name_counts,
                "reference_ratio": metrics.reference_ratio,
                "reference_tool_count": metrics.reference_tool_count,
                "calibrated": metrics.reference_ratio is not None,
            },
        )

    return _score
