"""Outcome matrix construction from eval logs for IRT fitting."""

from __future__ import annotations

import math

from bench_cli.compare.core import CompareData, load_compare_data
from bench_cli.identity import reconcile_identities
from bench_cli.irt.types import OutcomeMatrix
from bench_cli.results.core import is_moniker_alias


def _get_pillar_map() -> dict[str, str]:
    """Return task_name -> pillar mapping from the tasks/ directory."""
    from bench_cli.inspect.core import _load_pillar_map

    return _load_pillar_map()


def build_outcome_matrix(
    log_dir: str,
    *,
    filter_monikers: bool = True,
) -> OutcomeMatrix:
    """Build the outcome matrix for IRT fitting from eval logs.

    Rows = models (respondents), columns = tasks (items).
    Values = per-(model, task) mean correctness (0.0–1.0).
    """
    data = load_compare_data(log_dir)
    # Pass pre-loaded models to avoid redundant folder scanning
    identity_map = reconcile_identities(log_dir, models=data.models)

    canonical_models_set: set[str] = set()
    for m in data.models:
        canonical = identity_map.get(m, m)
        if not (filter_monikers and is_moniker_alias(canonical)):
            canonical_models_set.add(canonical)

    models = sorted(list(canonical_models_set))
    tasks = data.tasks

    scores_by_pair: dict[str, dict[str, list[float]]] = {t: {} for t in tasks}

    for task in tasks:
        for raw_model in data.models:
            ps = data.matrix.get(task, {}).get(raw_model)
            if ps is not None and not math.isnan(ps.correctness):
                canonical = identity_map.get(raw_model, raw_model)
                if canonical in canonical_models_set:
                    scores_by_pair[task].setdefault(canonical, []).append(ps.correctness)

    matrix: list[list[float]] = []
    for model in models:
        row: list[float] = []
        for task in tasks:
            vals = scores_by_pair[task].get(model)
            if vals:
                row.append(sum(vals) / len(vals))
            else:
                row.append(float("nan"))
        matrix.append(row)

    pillars = _get_pillar_map()

    return OutcomeMatrix(
        matrix=matrix,
        models=models,
        tasks=tasks,
        pillars=pillars,
    )
