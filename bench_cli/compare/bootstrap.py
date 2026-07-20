"""Percentile bootstrap on per-task correctness values.

Used by ``bench compare`` to attach 95% CIs to a model's capability mean.
Pure Python — no numpy. Seeded for reproducibility.
"""

from __future__ import annotations

import random
from typing import Iterable


def bootstrap_ci(
    per_task_scores: Iterable[float],
    *,
    n_resample: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
    min_n: int = 46,
) -> tuple[float, float] | None:
    """Bootstrap 95% CI on the mean of per-task correctness scores.

    Args:
        per_task_scores: per-task correctness values (each in [0, 1]).
        n_resample: number of bootstrap iterations. Default 1000.
        confidence: CI level. Default 0.95.
        seed: random seed for reproducibility. Default 42.
        min_n: minimum task count to compute CI. Default ``34``
               (matches ``MIN_FULL_EVAL_TASKS``). Below this returns
               ``None``; callers render "insufficient data" rather than a
               misleading CI.

    Returns:
        ``(ci_low, ci_high)`` tuple, or ``None`` if
        ``len(per_task_scores) < min_n``.
    """
    scores = list(per_task_scores)
    if len(scores) < min_n:
        return None

    rng = random.Random(seed)
    means: list[float] = []
    n = len(scores)
    for _ in range(n_resample):
        # Sample with replacement.
        sample = [scores[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)

    means.sort()
    # Percentile bounds (e.g., 2.5 / 97.5 for 0.95 CI).
    alpha = (1.0 - confidence) / 2.0
    lo_idx = max(0, int(alpha * n_resample))
    hi_idx = min(n_resample - 1, int((1.0 - alpha) * n_resample))
    return (means[lo_idx], means[hi_idx])
