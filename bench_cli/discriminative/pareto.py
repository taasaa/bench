"""Pareto frontier computation — quality vs cost trade-off analysis.

Pareto-optimal subjects: not dominated by any other subject.
Subject A dominates Subject B if A is >= B on all axes and > B on at least one.

Free models: separate frontier (cost=$0 anchors them separately).
Paid models: frontier on (quality, cost) where quality = geometric mean of cluster scores.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from bench_cli.compare import _geometric_mean
from bench_cli.discriminative.types import SubjectID, SubjectProfile


@dataclass
class ParetoPoint:
    """A single point on the Pareto frontier."""

    subject_id: SubjectID
    display_name: str
    quality: float  # geometric mean of cluster correctness scores
    cost_per_sample: float | None  # USD, None = unknown
    is_free: bool
    dominated: bool = False  # True if dominated by at least one other subject
    dominates: list[str] = None  # subjects this one dominates

    def __post_init__(self) -> None:
        if self.dominates is None:
            self.dominates = []


def compute_quality(profile: SubjectProfile) -> float:
    """Compute quality score for a profile = geometric mean of cluster correctness scores.

    Uses geometric mean so that one cluster at 0.0 drags the whole score to 0.
    This is the non-compensatory principle: one zero poisons the product.
    Reuses _geometric_mean from bench_cli.compare for consistency.
    """
    scored = [cs.correct for cs in profile.cluster_scores if cs.task_count > 0]
    if not scored:
        return 0.0

    gm = _geometric_mean(scored)
    if math.isnan(gm):
        return 0.0
    return gm


def _is_dominated(
    point: ParetoPoint,
    other: ParetoPoint,
    compare_cost: bool = True,
) -> bool:
    """Check if point is dominated by other.

    Dominance: other >= point on all axes, and > on at least one.
    For free/paid comparison: cost axis is handled separately.
    """
    # Quality: higher is better
    if other.quality < point.quality:
        return False

    # Cost: lower is better (if comparing)
    if compare_cost and other.cost_per_sample is not None and point.cost_per_sample is not None:
        if other.cost_per_sample > point.cost_per_sample:
            return False  # other is more expensive
        if other.cost_per_sample == point.cost_per_sample and other.quality == point.quality:
            return False  # identical

    # Check strict improvement on at least one axis
    if other.quality > point.quality:
        return True
    if compare_cost and other.cost_per_sample is not None and point.cost_per_sample is not None:
        if other.cost_per_sample < point.cost_per_sample:
            return True
    elif other.quality == point.quality and not compare_cost:
        return True  # tied on quality

    return False


def compute_pareto_frontier(
    profiles: list[SubjectProfile],
) -> list[ParetoPoint]:
    """Compute Pareto frontier from a list of subject profiles.

    Returns list of ParetoPoint with dominated flag set.
    Free models are handled separately: they are ranked quality-only.
    """
    if not profiles:
        return []

    # Separate free and paid profiles
    free_profiles: list[SubjectProfile] = []
    paid_profiles: list[SubjectProfile] = []

    for profile in profiles:
        if profile.cost_per_sample is not None and profile.cost_per_sample < 1e-9:
            free_profiles.append(profile)
        else:
            paid_profiles.append(profile)

    # Compute quality for all profiles
    all_points: list[ParetoPoint] = []
    for profile in profiles:
        quality = compute_quality(profile)
        is_free = profile.cost_per_sample is not None and profile.cost_per_sample < 1e-9
        all_points.append(
            ParetoPoint(
                subject_id=profile.subject_id,
                display_name=profile.subject_id.display_name,
                quality=quality,
                cost_per_sample=profile.cost_per_sample,
                is_free=is_free,
            )
        )

    # Mark domination for paid models (quality vs cost)
    paid_points = [p for p in all_points if not p.is_free]
    for point in paid_points:
        point.dominates = []
        for other in paid_points:
            if other is point:
                continue
            if _is_dominated(point, other, compare_cost=True):
                point.dominated = True
            if _is_dominated(other, point, compare_cost=True):
                point.dominates.append(other.display_name)

    # Free models: quality-only comparison
    free_points = [p for p in all_points if p.is_free]
    for point in free_points:
        point.dominates = []
        for other in free_points:
            if other is point:
                continue
            if _is_dominated(point, other, compare_cost=False):
                point.dominated = True
            if _is_dominated(other, point, compare_cost=False):
                point.dominates.append(other.display_name)

    # Sort: undominated first, then by quality descending
    all_points.sort(key=lambda p: (not p.dominated, -p.quality))
    return all_points


def format_pareto_frontier(
    points: list[ParetoPoint],
    freshness: str | None = None,
) -> str:
    """Format Pareto frontier as a readable table."""
    lines: list[str] = []

    lines.append("PARETO FRONTIER" + (f" (eval data: {freshness})" if freshness else ""))
    lines.append("=" * 56)
    lines.append("")

    # Paid models frontier
    paid = [p for p in points if not p.is_free]
    free = [p for p in points if p.is_free]

    if paid:
        lines.append("PAID MODELS (quality vs cost):")
        lines.append(f"{'Status':<12} {'Model':<30} {'Quality':>8} {'Cost/sample':>12}")
        lines.append("-" * 64)
        for p in paid:
            status = "UNDOMINATED" if not p.dominated else "dominated"
            cost_str = f"${p.cost_per_sample:.4f}" if p.cost_per_sample else "N/A"
            lines.append(f"{status:<12} {p.display_name:<30} {p.quality:>8.3f} {cost_str:>12}")
        lines.append("")

    if free:
        lines.append("FREE MODELS (quality only):")
        lines.append(f"{'Status':<12} {'Model':<30} {'Quality':>8}")
        lines.append("-" * 52)
        for p in free:
            status = "UNDOMINATED" if not p.dominated else "dominated"
            lines.append(f"{status:<12} {p.display_name:<30} {p.quality:>8.3f}")
        lines.append("")

    # Summary line
    undominated = [p for p in points if not p.dominated]
    lines.append(f"\n{len(undominated)} undominated / {len(points)} total subjects")

    return "\n".join(lines)
