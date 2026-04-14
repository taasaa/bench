"""Scorer protocol and shared constants for the pillars-first scoring system.

Architecture:
  - PillarScorer: Protocol defining the interface for all pillar scorers.
  - TaskBudget: dataclass holding per-task scoring configuration.
  - RatioSource: enum identifying which reference source was used for a ratio score.
  - SYSTEM_DEFAULT_BUDGETS: scaffolding defaults (to be superseded by baselines).
  - MIN_RATIO_FLOOR: minimum ratio value used only for MEAN computation (log-safety).
  - DEFAULT_NOISE_FLOOR: default latency noise floor in seconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from inspect_ai.scorer import Score, Target
from inspect_ai.solver import TaskState

if TYPE_CHECKING:
    from scorers.baseline_store import BaselineStore

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class PillarScorer(Protocol):

    """Protocol for all pillar scorers in the 4-pillar architecture.

    Every pillar scorer must:
      - Declare which pillar it scores via the `pillar` attribute.
      - Accept TaskState and Target and return a Score.
      - Be async-safe (called within Inspect's async event loop).
    """

    pillar: str
    """One of: correctness | efficiency | latency | safety"""

    async def __call__(self, state: TaskState, target: Target) -> Score:
        """Score the sample for this pillar.

        Returns Score with:
          - value: the pillar score (0.0-1.0 for bounded pillars;
                    unbounded float for efficiency/latency ratios)
          - explanation: key=value pairs required by bench compare's regex parsers
          - metadata: pillar-specific diagnostic data
        """
        ...


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RatioSource(Enum):

    """Identifies which reference source was used for a ratio score."""

    BASELINE = "baseline"
    """Measured run of a reference model — highest fidelity."""

    TASK_BUDGET = "task_budget"
    """Author-specified budget in TaskBudget — second fidelity."""

    SYSTEM_DEFAULT = "system_default"
    """Global scaffolding fallback — lowest fidelity."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_RATIO_FLOOR = 0.01
"""Minimum ratio value. Used only during MEAN computation to avoid log(0).

The actual ratio values stored in Score.metadata are NOT floored.
This constant is a computational artifact for geometric/harmonic mean math only.
"""

DEFAULT_NOISE_FLOOR = 5.0
"""Default latency noise floor in seconds.

A latency ratio is suppressed (returns Score(value=None)) when
min(reference_seconds, actual_seconds) < noise_floor_seconds for a
single-sample run. Configurable per-task via TaskBudget.noise_floor_seconds.
"""

LOOP_MESSAGE_THRESHOLD = 50
"""Heuristic threshold for potential loop detection.

If the agent issued more than this many tool calls (messages), flag as
potential_loop. Actual input/output token ratio not available in TaskState,
so this heuristic proxies for excessive re-reading or looping behavior.
"""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TaskBudget:

    """Per-task scoring configuration for efficiency and latency pillars.

    Used to configure TokenRatioScorer and TimeRatioScorer per task.
    Falls back to SYSTEM_DEFAULT_BUDGETS when fields are None.
    """

    output_tokens: int | None = None
    """Override for system default output token budget (1000)."""

    latency_seconds: float | None = None
    """Override for system default latency budget (30.0)."""

    noise_floor_seconds: float | None = None
    """Override for DEFAULT_NOISE_FLOOR (5.0). Lower = more sensitive."""


SYSTEM_DEFAULT_BUDGETS: dict[str, float] = {
    "output_tokens": 1000.0,
    "latency_seconds": 30.0,
}
"""System-level scaffolding defaults (calibrated from qwen-local baseline run).

These are fallback values used when no baseline store entry or task budget
is available. Calibrated from 62 samples across 16 tasks:
  tokens: mean=1047, median=857 → default 1000
  working_time: mean=29.7s, median=27.5s → default 30.0s

Should be superseded by measured baselines as the eval matures.
"""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def resolve_baseline_reference(
    baseline_store: BaselineStore | None,
    task_id: str,
    model_id: str,
    budget_field: Literal["output_tokens", "latency_seconds"],
) -> tuple[float, RatioSource, str | None]:
    """Resolve a reference value using the 3-tier chain.

    Tier 1: BaselineStore → Tier 2: TaskBudget field → Tier 3: SYSTEM_DEFAULT.

    Args:
        baseline_store: BaselineStore instance (None skips tier 1).
        task_id: Task identifier for baseline lookup.
        model_id: Model identifier for baseline lookup.
        budget_field: Which TaskBudget field to use.

    Returns:
        (reference_value, source, reference_model_id)
    """
    # Tier 1: baseline
    if baseline_store is not None:
        baseline = baseline_store.load(task_id, model_id)
        if baseline is not None and baseline.valid_for_reference:
            field_val = getattr(baseline, budget_field, None)
            if field_val is not None:
                return float(field_val), RatioSource.BASELINE, baseline.model_id

    # Tier 3: system default
    default_val = SYSTEM_DEFAULT_BUDGETS.get(budget_field, 1500.0)
    return float(default_val), RatioSource.SYSTEM_DEFAULT, None
