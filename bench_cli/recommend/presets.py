"""Preset router — rank models by use-case preset."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from bench_cli.compare.core import CompareData, _aggregate_model_pillars
from bench_cli.results.core import is_moniker_alias


@dataclass
class RankedModel:
    model: str
    rank: int
    capability: float
    ci: tuple[float, float] | None
    cost_per_task: float
    time_per_task: float
    on_pareto: bool = False
    dominated_by: list[str] = field(default_factory=list)


@dataclass
class RecommendResult:
    preset: str
    models: list[RankedModel]
    used_irt: bool = False


def _has_pymc() -> bool:
    try:
        import pymc  # noqa: F401
        return True
    except ImportError:
        return False


def _gather_model_stats(
    data: CompareData,
    log_dir: str,
    *,
    use_irt: bool = True,
) -> tuple[list[dict], bool]:
    from bench_cli.identity import reconcile_identities
    # Reconcile identities to ensure consistent model cohort mapping
    identity_map = reconcile_identities(log_dir, models=data.models)

    stats: list[dict] = []
    theta_map: dict[str, float] = {}
    theta_ci_map: dict[str, tuple[float, float]] = {}
    actually_used_irt = False

    # Filter out monikers and group raw models by their canonical identities
    canonical_models_set: set[str] = set()
    for m in data.models:
        canonical = identity_map.get(m, m)
        if not is_moniker_alias(canonical):
            canonical_models_set.add(canonical)

    models_to_fit = sorted(list(canonical_models_set))

    if use_irt and _has_pymc():
        try:
            from bench_cli.irt.fit import fit_2pl
            from bench_cli.irt.types import OutcomeMatrix
            
            tasks = data.tasks
            matrix: list[list[float]] = []
            for model in models_to_fit:
                row = []
                for task in tasks:
                    vals = []
                    for raw_model in data.models:
                        if identity_map.get(raw_model, raw_model) == model:
                            ps = data.matrix.get(task, {}).get(raw_model)
                            if ps is not None and not math.isnan(ps.correctness):
                                vals.append(ps.correctness)
                    if vals:
                        row.append(sum(vals) / len(vals))
                    else:
                        row.append(float("nan"))
                matrix.append(row)
            
            outcome = OutcomeMatrix(matrix=matrix, models=models_to_fit, tasks=tasks)
            fit = fit_2pl(outcome, n_samples=1000, n_chains=2)
            if fit.converged:
                for i, m in enumerate(fit.models):
                    theta_map[m] = fit.theta[i]
                    theta_ci_map[m] = fit.theta_ci[i]
                actually_used_irt = True
        except Exception:
            pass

    # Build merged stats for each canonical model
    canonical_stats: dict[str, list[dict]] = {}
    for raw_model in data.models:
        canonical = identity_map.get(raw_model, raw_model)
        if canonical not in canonical_models_set:
            continue
        agg = _aggregate_model_pillars(data, raw_model)
        if agg is None:
            continue
        canonical_stats.setdefault(canonical, []).append({
            "correct_mean": agg["correct_mean"],
            "cost_per_task": agg["cost_per_task"],
            "time_per_task": agg["time_per_task"],
            "ci_low": agg["ci_low"],
            "ci_high": agg["ci_high"],
        })

    for model in models_to_fit:
        entries = canonical_stats.get(model, [])
        if not entries:
            continue
        
        # Merge by taking the average across raw models that mapped to this canonical name
        mean_cap = sum(e["correct_mean"] for e in entries) / len(entries)
        valid_costs = [e["cost_per_task"] for e in entries if not math.isnan(e["cost_per_task"])]
        mean_cost = sum(valid_costs) / len(valid_costs) if valid_costs else float("nan")
        valid_times = [e["time_per_task"] for e in entries if not math.isnan(e["time_per_task"])]
        mean_time = sum(valid_times) / len(valid_times) if valid_times else float("nan")

        cap = theta_map.get(model, mean_cap)
        ci = theta_ci_map.get(model, (entries[0]["ci_low"], entries[0]["ci_high"]) if entries[0]["ci_low"] is not None else None)

        stats.append({
            "model": model,
            "capability": cap,
            "ci": ci,
            "cost_per_task": mean_cost,
            "time_per_task": mean_time,
        })

    return stats, actually_used_irt


def recommend_preset(
    data: CompareData,
    preset: str,
    *,
    log_dir: str = "logs",
    use_irt: bool = True,
) -> RecommendResult:
    """Rank models by preset logic."""
    stats, actually_used_irt = _gather_model_stats(data, log_dir, use_irt=use_irt)

    if preset == "best":
        ranked = sorted(stats, key=lambda s: s["capability"], reverse=True)
        models = [
            RankedModel(
                model=s["model"], rank=i + 1,
                capability=s["capability"], ci=s["ci"],
                cost_per_task=s["cost_per_task"],
                time_per_task=s["time_per_task"],
            )
            for i, s in enumerate(ranked)
        ]
    elif preset == "cheap-fast":
        costs = [s["cost_per_task"] for s in stats if not math.isnan(s["cost_per_task"])]
        median_cost = statistics.median(costs) if costs else float("inf")
        filtered = [s for s in stats if not math.isnan(s["cost_per_task"]) and s["cost_per_task"] <= median_cost]
        ranked = sorted(filtered, key=lambda s: (s["time_per_task"], -s["capability"]))
        models = [
            RankedModel(
                model=s["model"], rank=i + 1,
                capability=s["capability"], ci=s["ci"],
                cost_per_task=s["cost_per_task"],
                time_per_task=s["time_per_task"],
            )
            for i, s in enumerate(ranked)
        ]
    elif preset == "balanced":
        from bench_cli.recommend.pareto import compute_pareto_front
        model_names = [s["model"] for s in stats]
        capabilities = [s["capability"] for s in stats]
        costs = [s["cost_per_task"] if not math.isnan(s["cost_per_task"]) else float("inf") for s in stats]
        times = [s["time_per_task"] if not math.isnan(s["time_per_task"]) else float("inf") for s in stats]
        pareto_indices, dominated_by_indices = compute_pareto_front(model_names, capabilities, costs, times)
        pareto_set = set(pareto_indices)
        pareto_models = sorted([i for i in range(len(stats)) if i in pareto_set], key=lambda i: stats[i]["capability"], reverse=True)
        dominated_models = sorted([i for i in range(len(stats)) if i not in pareto_set], key=lambda i: stats[i]["capability"], reverse=True)
        
        models = []
        for rank, i in enumerate(pareto_models + dominated_models, 1):
            s = stats[i]
            dom_models = [model_names[d] for d in dominated_by_indices[i]]
            models.append(RankedModel(
                model=s["model"], rank=rank,
                capability=s["capability"], ci=s["ci"],
                cost_per_task=s["cost_per_task"],
                time_per_task=s["time_per_task"],
                on_pareto=i in pareto_set,
                dominated_by=dom_models,
            ))
    else:
        raise ValueError(f"Unknown preset: {preset}")

    return RecommendResult(preset=preset, models=models, used_irt=actually_used_irt)
