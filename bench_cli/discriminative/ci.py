"""Agresti-Coull confidence intervals for binary proportions at small n.

At n=5 binary samples, only 6 possible outcomes exist (0/5 through 5/5).
Bootstrap resampling produces biased intervals. Agresti-Coull exact intervals
are mathematically honest for this data.

Reference: Agresti & Coull (1998). Approximate is better than "exact"
for interval estimation of binomial proportions. Statistics in Medicine.
"""
from __future__ import annotations

import math
from typing import Sequence

# ---------------------------------------------------------------------------
# z-scores for common confidence levels
# ---------------------------------------------------------------------------
_Z_SCORES: dict[float, float] = {
    0.80: 1.282,
    0.90: 1.645,
    0.95: 1.960,
    0.99: 2.576,
}


def _z_score(confidence: float) -> float:
    """Return z-score for given confidence level."""
    # Try exact match first
    if confidence in _Z_SCORES:
        return _Z_SCORES[confidence]
    # Compute inverse normal for intermediate levels
    # Using approximation: z = sqrt(2) * erfc^{-1}(2*(1-confidence))
    # Fall back to nearest available
    best = min(_Z_SCORES.keys(), key=lambda k: abs(k - confidence))
    return _Z_SCORES[best]


def agresti_coull_ci(
    n_successes: int,
    n_trials: int,
    confidence: float = 0.90,
) -> tuple[float, float]:
    """Compute Agresti-Coull confidence interval for a binary proportion.

    The Agresti-Coull interval adds 2 successes and 2 failures (z^2/2) to
    the sample before computing the interval, which corrects for the
    discreteness problem at small n.

    Formula:
        n_adj = n + z^2
        p_adj = (n_successes + z^2/2) / n_adj
        se_adj = sqrt(p_adj * (1 - p_adj) / n_adj)
        low  = p_adj - z * se_adj
        high = p_adj + z * se_adj
        clamp to [0, 1]

    Args:
        n_successes: number of successes (0..n_trials)
        n_trials: total number of trials (must be > 0)
        confidence: confidence level (default 0.90)

    Returns:
        (low, high) tuple, both clamped to [0.0, 1.0]
    """
    if n_trials <= 0:
        return (0.0, 1.0)

    n_successes = max(0, min(n_successes, n_trials))
    z = _z_score(confidence)
    z2 = z * z

    # Agresti-Coull adjustment: add z^2/2 successes to n trials
    n_adj = n_trials + z2
    x_adj = n_successes + z2 / 2.0
    p_adj = x_adj / n_adj

    # Adjusted standard error
    se_adj = math.sqrt(p_adj * (1 - p_adj) / n_adj)

    low = p_adj - z * se_adj
    high = p_adj + z * se_adj

    return (max(0.0, low), min(1.0, high))


def cluster_ci(
    scores: Sequence[float],
    n_samples: int = 5,
    confidence: float = 0.90,
) -> tuple[float, float]:
    """Compute CI for a cluster's aggregate score.

    Aggregates all per-task scores into a single binary proportion,
    then computes Agresti-Coull CI on the aggregate.

    Args:
        scores: list of per-task correctness scores (0.0 or 1.0 per sample)
        n_samples: number of samples per task (default 5)
        confidence: confidence level (default 0.90)

    Returns:
        (low, high) CI tuple
    """
    total_successes = sum(int(s >= 0.5) for s in scores)
    total_trials = len(scores) * n_samples
    return agresti_coull_ci(total_successes, total_trials, confidence)


def c_is_significant(
    ci_a: tuple[float, float],
    ci_b: tuple[float, float],
) -> bool:
    """Check whether two CIs are non-overlapping (significant difference)."""
    # CIs are non-overlapping if one's high < the other's low
    return ci_a[1] < ci_b[0] or ci_b[1] < ci_a[0]
