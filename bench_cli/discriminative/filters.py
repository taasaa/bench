"""Task discrimination filtering — flag non-discriminative tasks.

Discrimination = std(scores across subjects per task).
If all subjects score the same on a task (std = 0), the task provides
zero information for discriminating between subjects.

This is NOT discrimination weighting (invalid at N=8).
This is just identifying which tasks add signal vs. noise.
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bench_cli.discriminative.types import SubjectID


def compute_task_discrimination(
    all_scores: dict[SubjectID, dict[str, float]],
) -> dict[str, float]:
    """Compute discrimination (std) for each task across all subjects.

    Args:
        all_scores: {subject_id: {task_id: correctness_score}}

    Returns:
        {task_id: discrimination} where discrimination = std(scores)
        0.0 = non-discriminative (all subjects same score)
        > 0.0 = discriminative (subjects differ on this task)
    """
    if not all_scores:
        return {}

    # Collect scores per task
    task_scores: dict[str, list[float]] = {}
    for subject_scores in all_scores.values():
        for task_id, score in subject_scores.items():
            if task_id not in task_scores:
                task_scores[task_id] = []
            task_scores[task_id].append(score)

    discrimination: dict[str, float] = {}
    for task_id, scores in task_scores.items():
        if len(scores) < 2:
            discrimination[task_id] = 0.0
        else:
            discrimination[task_id] = statistics.stdev(scores)

    return discrimination


def flag_non_discriminative(
    discrimination: dict[str, float],
    threshold: float = 0.0,
) -> set[str]:
    """Return task IDs where discrimination <= threshold.

    These tasks provide no signal for distinguishing between subjects.
    They should be excluded from cluster scores and listed separately.
    """
    return {task_id for task_id, sigma in discrimination.items() if sigma <= threshold}
