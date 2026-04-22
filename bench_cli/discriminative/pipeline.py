"""Pipeline — wire diagnostics + profiles into a run_pipeline() function."""
from __future__ import annotations

from pathlib import Path

import yaml

from bench_cli.compare.core import _recalc_cost
from bench_cli.discriminative.profiles import (
    build_profile,
)
from bench_cli.discriminative.subject import get_all_log_paths, resolve_subject_from_log
from bench_cli.discriminative.types import (
    DiagnosticReport,
    GateResult,
    PipelineConfig,
    SubjectID,
    SubjectProfile,
)


def load_clusters_yaml(path: Path) -> dict[str, list[str]]:
    """Load cluster definitions from YAML file.

    Task IDs are normalized from YAML format (hyphens) to eval log format (underscores).
    E.g. 'add-tests' in YAML becomes 'add_tests' to match eval log task names.
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    clusters: dict[str, list[str]] = {}
    for cluster_key, cluster_data in data.items():
        if isinstance(cluster_data, dict) and "task_ids" in cluster_data:
            # Normalize task IDs: hyphens → underscores (eval log format)
            raw_ids = cluster_data["task_ids"]
            clusters[cluster_key] = [tid.replace("-", "_") for tid in raw_ids]
        elif isinstance(cluster_data, list):
            clusters[cluster_key] = [tid.replace("-", "_") for tid in cluster_data]

    return clusters


def _extract_pillar_data(sample) -> dict[str, float]:
    """Extract token_ratio, time_ratio, cost_ratio from a sample.

    Returns per-metric values (single sample's ratios).
    """
    import math
    result: dict[str, float] = {}

    if sample.scores:
        tr = sample.scores.get("token_ratio_scorer")
        if tr is not None:
            raw = getattr(tr, "value", None)
            val = raw if raw is not None else (float(tr) if isinstance(tr, (int, float)) else None)
            if val is not None:
                result["token_ratio"] = float(val)

        lr = sample.scores.get("time_ratio_scorer")
        if lr is not None:
            raw = getattr(lr, "value", None)
            val = raw if raw is not None else (float(lr) if isinstance(lr, (int, float)) else None)
            if val is not None:
                result["time_ratio"] = float(val)

        pr = sample.scores.get("price_ratio_scorer")
        if pr is not None:
            raw = getattr(pr, "value", None)
            val = raw if raw is not None else (float(pr) if isinstance(pr, (int, float)) else None)
            if val is not None and not math.isnan(float(val)):
                result["cost_ratio"] = float(val)

    return result


def run_pipeline(
    log_dir: Path,
    subject_id: SubjectID | None,
    config: PipelineConfig | None = None,
) -> tuple[SubjectProfile, DiagnosticReport]:
    """Run the full discriminative pipeline.

    1. Load eval logs for the subject
    2. Extract per-task scores
    3. Load clusters.yaml
    4. Compute diagnostics (discrimination, difficulty)
    5. Build profile with CIs
    6. Return (SubjectProfile, DiagnosticReport)
    """
    if config is None:
        config = PipelineConfig()

    # Step 1: load eval logs
    log_paths = get_all_log_paths(log_dir, subject_id)
    if not log_paths:
        raise ValueError(f"No eval logs found for subject: {subject_id}")

    # Step 2: extract per-task scores
    from inspect_ai.log import read_eval_log

    scores: dict[str, float] = {}
    pillar_data: dict[str, dict[str, list[float]]] = {}
    # pillar_data: {task_id: {metric: [sample0_val, sample1_val, ...]}}
    total_cost: float = 0.0
    total_latency: float = 0.0
    total_tool_calls: int = 0
    n_samples: int = 0

    for log_path in log_paths:
        try:
            el = read_eval_log(str(log_path))
        except Exception:
            continue

        if el.status != "success" or not el.results:
            continue

        task_id = el.eval.task
        task_correct: list[float] = []

        for sample in el.samples:
            n_samples += 1

            # Correctness
            if sample.scores:
                c = _get_correctness(sample.scores)
                if c is not None:
                    task_correct.append(c)

            # Pillar data — accumulate per-sample values as lists for averaging
            pd = _extract_pillar_data(sample)
            if pd:
                if task_id not in pillar_data:
                    pillar_data[task_id] = {k: [] for k in pd}
                for k, v in pd.items():
                    pillar_data[task_id].setdefault(k, []).append(v)

            # Latency
            if sample.working_time:
                total_latency += sample.working_time

            # Cost from model_usage
            if sample.model_usage:
                for model_key, usage in sample.model_usage.items():
                    if "judge" in model_key.lower():
                        continue
                    inp = getattr(usage, "input_tokens", 0) or 0
                    out = getattr(usage, "output_tokens", 0) or 0
                    cost = _recalc_cost(model_key, int(inp), int(out))
                    if cost:
                        total_cost += cost
                    break

            # Tool calls from events
            if hasattr(sample, "events"):
                try:
                    events_list = list(sample.events)
                    tool_calls = sum(1 for e in events_list if _is_tool_event(e))
                    total_tool_calls += tool_calls
                except Exception:
                    pass

        if task_correct:
            scores[task_id] = sum(task_correct) / len(task_correct)

    # Detect subject type if not provided
    if subject_id is None and log_paths:
        subject_id = resolve_subject_from_log(log_paths[0])

    # Step 3: load clusters
    clusters_path = Path(config.clusters_yaml)
    if not clusters_path.is_absolute():
        clusters_path = Path("/Users/rut/dev/bench") / clusters_path
    clusters = load_clusters_yaml(clusters_path)

    # Step 4: diagnostics
    # With N=1 subjects, discrimination is always 0 (can't measure variance with 1 subject).
    # Don't pass single-subject scores to run_diagnostics — skip discrimination filtering.
    # All tasks contribute to cluster scores for single-subject profiling.
    non_discriminative: set[str] = set()

    # Step 5: build profile
    cost_per_sample = total_cost / n_samples if n_samples > 0 else None
    latency_avg = total_latency / n_samples if n_samples > 0 else None
    tool_calls_avg = total_tool_calls / n_samples if n_samples > 0 else None

    # Handle free models
    if cost_per_sample is not None and cost_per_sample < 1e-9:
        cost_per_sample = 0.0

    profile = build_profile(
        subject_id=subject_id,
        scores=scores,
        clusters=clusters,
        non_discriminative_tasks=non_discriminative,
        pillar_data=pillar_data,
        cost_per_sample=cost_per_sample,
        latency_avg=latency_avg,
        tool_calls_avg=tool_calls_avg,
        ci_level=config.ci_level,
    )

    # Run safety gates
    gate_results = run_gates_for_profile(profile, config)
    profile.gate_results = gate_results

    return profile, DiagnosticReport(tasks=[])


def run_gates_for_profile(
    profile: SubjectProfile,
    config: PipelineConfig,
) -> list[GateResult]:
    """Run safety gates against a profile."""
    from bench_cli.discriminative import gates as gate_module

    gates_path = Path(config.gates_yaml)
    if not gates_path.is_absolute():
        gates_path = Path("/Users/rut/dev/bench") / gates_path

    return gate_module.run_gates(profile, gates_yaml=str(gates_path))


def _get_correctness(sample_scores: dict) -> float | None:
    """Extract correctness from sample scores dict."""
    import math
    # Try in order: hybrid > llm_judge > verify_sh > exact
    for key in ("hybrid_scorer", "llm_judge", "verify_sh", "exact", "includes"):
        score = sample_scores.get(key)
        if score is None:
            continue
        val = getattr(score, "value", None)
        if val is None:
            if isinstance(score, (int, float)):
                val = score
        if val is not None:
            try:
                fv = float(val)
            except (ValueError, TypeError):
                continue
            if not math.isnan(fv) and not math.isinf(fv):
                return fv
    return None


def _is_tool_event(event) -> bool:
    """Check if an event represents a tool call."""
    event_type = getattr(event, "type", None)
    if event_type and "tool" in str(event_type).lower():
        return True
    return False
