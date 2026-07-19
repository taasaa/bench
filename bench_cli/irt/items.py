"""IRT item analysis — difficulty, discrimination, and classification."""

from __future__ import annotations

from bench_cli.irt.types import IRTFit, ItemAnalysis


def classify_discrimination(
    a: float,
    *,
    high_threshold: float = 1.0,
    medium_threshold: float = 0.5,
    low_threshold: float = 0.2,
) -> str:
    """Classify discrimination parameter into bands."""
    if a >= high_threshold:
        return "high"
    if a >= medium_threshold:
        return "medium"
    if a >= low_threshold:
        return "low"
    return "cull"


def item_analysis(fit: IRTFit) -> list[ItemAnalysis]:
    """Extract per-task item parameters + credible intervals from a fitted IRT model."""
    items: list[ItemAnalysis] = []
    pillar_label = fit.pillar or "general"

    for j, task in enumerate(fit.tasks):
        a_val = fit.a[j]
        b_val = fit.b[j]
        a_ci_val = fit.a_ci[j]
        b_ci_val = fit.b_ci[j]

        items.append(ItemAnalysis(
            task=task,
            pillar=pillar_label,
            a=a_val,
            a_ci=a_ci_val,
            b=b_val,
            b_ci=b_ci_val,
            band=classify_discrimination(a_val),
        ))

    return items


def in_discriminating_band(
    b: float,
    mean_theta: float,
    tolerance: float = 0.5,
) -> bool:
    """Check if task difficulty is in the discriminating band."""
    return abs(b - mean_theta) <= tolerance
