"""Shared ratio-recomputation logic for the 4-pillar scoring system.

Single source of truth for reference-driven ratio math, used by BOTH:
  - ``bench_cli.compare.core`` (pillar comparison table, W3a/W3b)
  - ``bench_cli.results.core`` (model card generation)

Centralizing this prevents the two display paths from drifting -- which is
exactly what stale-ified the m3 model card after the m2.7 -> m3 cost
re-baseline (commit 7478db0): ``compare`` recomputed ratios from the LIVE
reference while ``results`` read BAKED-IN scorer values.

Aggregation methods (deliberate, mirror ``compare``):
  - token / time: ``ref / mean(actual)`` over samples (ratio-of-means).
    More stable than the baked-in ``mean(ref/actual_i)`` (mean-of-ratios),
    which is inflated by a few fast samples (e.g. quick failures).
  - cost: ``geometric_mean(ref_cost / actual_cost_i)`` over positive samples.

Reference resolution (W3 unified reference), same for all three:
  Tier 1: BaselineStore entry for the designated reference model (if registered).
  Tier 2: ``TaskBudget`` field (output_tokens / latency_seconds / reference_cost_usd).
  Tier 3: SYSTEM_DEFAULT_BUDGETS (tokens/latency only).
"""

from __future__ import annotations

import math

from scorers.baseline_store import BaselineStore
from scorers.protocol import RatioSource, resolve_baseline_reference, resolve_cost_reference
from scorers.task_budgets import get_task_budget


def geometric_mean(vals: list[float]) -> float:
    """Geometric mean of positive values; ``nan`` if empty or any value <= 0."""
    if not vals:
        return float("nan")
    for v in vals:
        if v <= 0:
            return float("nan")
    log_sum = math.fsum(math.log(v) for v in vals)
    return math.exp(log_sum / len(vals))


def _resolve_tiered_reference(
    baseline_store: BaselineStore | None,
    task: str,
    metric_name: str,
    budget,  # TaskBudget | None
    budget_attr: str,
) -> tuple[float, bool]:
    """Resolve a reference value with Tier-1 (BaselineStore) -> Tier-2 (budget) precedence.

    Returns ``(ref_value, source_was_baseline)``. When Tier-1 returns a BASELINE
    source, the budget is ignored (a registered reference wins for ALL subjects).
    """
    ref, source, _ = resolve_baseline_reference(baseline_store, task, "", metric_name)
    if source is not RatioSource.BASELINE and budget is not None:
        budget_val = getattr(budget, budget_attr, None)
        if budget_val is not None:
            ref = float(budget_val)
    return ref, source is RatioSource.BASELINE


def recompute_token_ratio(
    baseline_store: BaselineStore | None,
    task: str,
    avg_tokens: float,
    budget=None,  # TaskBudget | None
) -> float:
    """W3a: reference output_tokens / actual mean total tokens.

    Tier-1 BaselineStore -> Tier-2 ``task_budget.output_tokens`` ->
    Tier-3 SYSTEM_DEFAULT. ``nan`` when ``avg_tokens`` is non-positive.
    """
    if budget is None:
        budget = get_task_budget(task)
    ref, _ = _resolve_tiered_reference(
        baseline_store, task, "output_tokens", budget, "output_tokens"
    )
    return ref / avg_tokens if avg_tokens and avg_tokens > 0 else float("nan")


def recompute_time_ratio(
    baseline_store: BaselineStore | None,
    task: str,
    avg_time: float,
    budget=None,  # TaskBudget | None
) -> float:
    """W3a: reference latency_seconds / actual mean seconds.

    Tier-1 BaselineStore -> Tier-2 ``task_budget.latency_seconds`` ->
    Tier-3 SYSTEM_DEFAULT. ``nan`` when ``avg_time`` is non-positive.
    """
    if budget is None:
        budget = get_task_budget(task)
    ref, _ = _resolve_tiered_reference(
        baseline_store, task, "latency_seconds", budget, "latency_seconds"
    )
    return ref / avg_time if avg_time and avg_time > 0 else float("nan")


def recompute_price_ratio(
    baseline_store: BaselineStore | None,
    task: str,
    cost_samples: list[float | None],
    budget=None,  # TaskBudget | None
) -> float:
    """W3b: geometric mean of ``(ref_cost / actual_cost_i)`` over positive samples.

    Tier-1 BaselineStore -> Tier-2 ``task_budget.reference_cost_usd``.
    Returns ``nan`` when there is no usable cost/reference data -- notably for
    FREE models (actual_cost_usd == 0.0 is filtered out). Callers drive the
    "FREE" display from a separate flag (e.g. ``is_managed_model``), not from
    this value, so ``nan`` here is correct and keeps results <-> compare parity.
    """
    if budget is None:
        budget = get_task_budget(task)
    valid = [c for c in cost_samples if isinstance(c, (int, float)) and c > 0]
    if not valid:
        return float("nan")
    ref_cost, _src, _ref = resolve_cost_reference(baseline_store, task)
    if ref_cost is None and budget is not None:
        ref_cost = budget.reference_cost_usd
    if ref_cost is None or ref_cost <= 0:
        return float("nan")
    return geometric_mean([ref_cost / c for c in valid])
