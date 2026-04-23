"""Task correlation analysis — discovering task groupings via Pearson r.

Phase 3: given multi-subject scores, compute pairwise task correlations.
Tasks that are highly correlated (r >= 0.5) likely tap the same underlying capability,
revealing natural clusters beyond the manual 4-tier taxonomy.
"""
from __future__ import annotations

import math

from bench_cli.discriminative.phase3_types import TaskCorrelation

_MIN_CORRELATION = 0.5
_MIN_DATA_POINTS = 3


def compute_task_correlation(
    all_scores: dict[str, dict[str, float]],
) -> list[TaskCorrelation]:
    """Compute pairwise Pearson r between tasks across subjects.

    Args:
        all_scores: {subject_id: {task_id: score}}. All subjects must have
            scored the same tasks for correlation to be meaningful.

    Returns:
        list of TaskCorrelation for task pairs where |r| >= 0.5 and n >= 3.
        Sorted by |r| descending.
    """
    if not all_scores:
        return []

    # Find tasks that appear across all subjects
    subject_ids = list(all_scores.keys())
    first_subj = subject_ids[0]
    all_tasks = set(all_scores[first_subj].keys())

    # Only include tasks present in ALL subjects (for fair comparison)
    shared_tasks: list[str] = []
    for task_id in all_tasks:
        present_in_all = True
        for subj in subject_ids:
            if task_id not in all_scores[subj]:
                present_in_all = False
                break
        if present_in_all:
            shared_tasks.append(task_id)

    if len(shared_tasks) < 2:
        return []

    # Build per-task score vectors
    task_vectors: dict[str, list[float]] = {task_id: [] for task_id in shared_tasks}
    for subj in subject_ids:
        for task_id in shared_tasks:
            task_vectors[task_id].append(all_scores[subj][task_id])

    # Compute pairwise Pearson r for all task pairs
    correlations: list[TaskCorrelation] = []

    for i, task_a in enumerate(shared_tasks):
        for task_b in shared_tasks[i + 1:]:
            vec_a = task_vectors[task_a]
            vec_b = task_vectors[task_b]

            # Need at least 3 data points for meaningful Pearson r
            if len(vec_a) < _MIN_DATA_POINTS or len(vec_b) < _MIN_DATA_POINTS:
                continue

            r = _pearson_r(vec_a, vec_b)

            if r is not None and abs(r) >= _MIN_CORRELATION:
                correlations.append(TaskCorrelation(
                    task_a=task_a,
                    task_b=task_b,
                    pearson_r=r,
                ))

    # Sort by absolute r descending
    correlations.sort(key=lambda c: abs(c.pearson_r), reverse=True)
    return correlations


def _pearson_r(vec_a: list[float], vec_b: list[float]) -> float | None:
    """Compute Pearson correlation coefficient.

    Returns None if variance is zero (no discriminative signal).
    """
    if len(vec_a) != len(vec_b):
        return None

    n = len(vec_a)
    if n < 2:
        return None

    try:
        mean_a = sum(vec_a) / n
        mean_b = sum(vec_b) / n
    except Exception:
        return None

    numerator = sum((a - mean_a) * (b - mean_b) for a, b in zip(vec_a, vec_b, strict=False))

    var_a = sum((a - mean_a) ** 2 for a in vec_a)
    var_b = sum((b - mean_b) ** 2 for b in vec_b)

    denom = math.sqrt(var_a * var_b)
    if denom == 0:
        return None

    return numerator / denom


def format_correlation_table(correlations: list[TaskCorrelation]) -> str:
    """Format correlations as an ASCII table."""
    lines: list[str] = []

    lines.append("TASK CORRELATION ANALYSIS (r >= 0.5, |r| descending)")
    lines.append("=" * 60)
    lines.append(f"{'Task A':<25} {'Task B':<25} {'r':>6}  Interpretation")
    lines.append("-" * 65)

    if not correlations:
        lines.append("(No task pairs with r >= 0.5 across available subjects.)")
        return "\n".join(lines)

    for corr in correlations:
        lines.append(
            f"{corr.task_a:<25} {corr.task_b:<25} {corr.pearson_r:>6.3f}  "
            f"{corr.interpretation}"
        )

    lines.append("")
    lines.append(f"{len(correlations)} correlated pairs found.")
    return "\n".join(lines)
