"""Pipeline — wire diagnostics + profiles into a run_pipeline() function."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import yaml

from bench_cli.compare.core import _recalc_cost
from bench_cli.discriminative.diagnostics import run_diagnostics
from bench_cli.discriminative.phase3_types import MultiSubjectReport
from bench_cli.discriminative.profiles import (
    build_profile,
)
from bench_cli.discriminative.subject import get_all_log_paths
from bench_cli.discriminative.types import (
    DiagnosticReport,
    GateResult,
    PipelineConfig,
    SubjectID,
    SubjectProfile,
)


def load_clusters_yaml(
    path: Path,
    custom_yaml: Path | None = None,
    known_tasks: set[str] | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """Load cluster definitions from YAML file.

    Task IDs are normalized from YAML format (hyphens) to eval log format (underscores).
    E.g. 'add-tests' in YAML becomes 'add_tests' to match eval log task names.

    Args:
        path: path to base clusters YAML (clusters.yaml)
        custom_yaml: optional path to custom clusters YAML that merges with base
        known_tasks: optional set of known task IDs for validation.
            Unknown task IDs in custom clusters produce a warning.

    Returns:
        (clusters_dict, warnings_list) where clusters_dict maps cluster_name -> [task_ids]
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

    warnings: list[str] = []

    # Merge custom clusters
    if custom_yaml is not None and custom_yaml.exists():
        with open(custom_yaml) as f:
            custom_data = yaml.safe_load(f)

        for key, value in custom_data.items():
            if key in clusters:
                warnings.append(
                    f"Custom cluster '{key}' overrides base cluster of same name."
                )

            if isinstance(value, dict):
                task_ids = value.get("task_ids", [])
            elif isinstance(value, list):
                task_ids = value
            else:
                warnings.append(f"Custom cluster '{key}' has invalid structure, skipped.")
                continue

            normalized = [tid.replace("-", "_") for tid in task_ids]
            clusters[key] = normalized

            # Validate task IDs if known_tasks provided
            if known_tasks is not None:
                for tid in normalized:
                    if tid not in known_tasks:
                        warnings.append(
                            f"Custom cluster '{key}' references unknown task '{tid}' "
                            f"(not found in eval logs). Task will be included anyway."
                        )

    return clusters, warnings


def _extract_pillar_data(sample) -> dict[str, float]:
    """Extract token_ratio, time_ratio, cost_ratio from a sample.

    Returns per-metric values (single sample's ratios).
    """
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

    profile, report = _build_profile_for_subjects(
        log_dir=log_dir,
        subject_ids=[subject_id] if subject_id else [],
        config=config,
        custom_clusters_yaml=None,
    )

    if subject_id is None:
        return profile, report

    single_profile = profile if isinstance(profile, SubjectProfile) else profile[0]
    return single_profile, report


def run_multi_pipeline(
    log_dir: Path,
    subject_ids: list[SubjectID],
    config: PipelineConfig | None = None,
    custom_clusters_yaml: Path | None = None,
) -> MultiSubjectReport:
    """Run pipeline for multiple subjects simultaneously.

    Returns a MultiSubjectReport with per-subject profiles and a shared
    DiagnosticReport computed across all subjects together.

    Args:
        log_dir: directory containing eval logs
        subject_ids: list of SubjectIDs to profile
        config: pipeline configuration
        custom_clusters_yaml: optional path to custom cluster definitions

    Returns:
        MultiSubjectReport containing list of SubjectProfiles and shared DiagnosticReport
    """
    if config is None:
        config = PipelineConfig()

    profiles, report = _build_profile_for_subjects(
        log_dir=log_dir,
        subject_ids=subject_ids,
        config=config,
        custom_clusters_yaml=custom_clusters_yaml,
    )

    return MultiSubjectReport(profiles=profiles, diagnostic_report=report)


def _build_profile_for_subjects(
    log_dir: Path,
    subject_ids: list[SubjectID],
    config: PipelineConfig,
    custom_clusters_yaml: Path | None,
) -> tuple[list[SubjectProfile], DiagnosticReport]:
    """Internal: build profiles for one or more subjects.

    Returns list of SubjectProfile and shared DiagnosticReport.
    """
    from inspect_ai.log import read_eval_log

    # Load eval logs for all subjects
    all_scores: dict[str, dict[str, float]] = {}
    all_pillar_data: dict[str, dict[str, dict[str, list[float]]]] = {}
    # all_pillar_data: {subject_key: {task_id: {metric: [val, ...]}}}

    subject_keys: list[str] = []
    for sid in subject_ids:
        key = sid.display_name
        subject_keys.append(key)

        log_paths = get_all_log_paths(log_dir, sid)
        if not log_paths:
            continue

        scores: dict[str, float] = {}
        pillar_data: dict[str, dict[str, list[float]]] = {}
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

                c = _get_correctness(sample.scores)
                if c is not None:
                    task_correct.append(c)

                pd = _extract_pillar_data(sample)
                if pd:
                    if task_id not in pillar_data:
                        pillar_data[task_id] = {k: [] for k in pd}
                    for k, v in pd.items():
                        pillar_data[task_id].setdefault(k, []).append(v)

                if sample.working_time:
                    total_latency += sample.working_time

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

                if hasattr(sample, "events"):
                    try:
                        events_list = list(sample.events)
                        tool_calls = sum(1 for e in events_list if _is_tool_event(e))
                        total_tool_calls += tool_calls
                    except Exception:
                        pass

            if task_correct:
                scores[task_id] = sum(task_correct) / len(task_correct)

        all_scores[key] = scores
        all_pillar_data[key] = pillar_data

    # Collect all known tasks from eval logs
    known_tasks: set[str] = set()
    for scores in all_scores.values():
        known_tasks.update(scores.keys())

    # Load clusters (with optional custom)
    clusters_path = Path(config.clusters_yaml)
    if not clusters_path.is_absolute():
        clusters_path = Path("/Users/rut/dev/bench") / clusters_path

    clusters, cluster_warnings = load_clusters_yaml(
        clusters_path,
        custom_yaml=custom_clusters_yaml,
        known_tasks=known_tasks,
    )

    # Print warnings to stderr
    for w in cluster_warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    # Compute diagnostics across all subjects
    # Build {subject_id_str: {task_id: score}} for run_diagnostics
    diag_scores: dict[str, dict[str, float]] = {}
    for sid in subject_ids:
        key = sid.display_name
        if key in all_scores:
            diag_scores[key] = all_scores[key]

    if len(diag_scores) >= 2:
        diagnostic_report = run_diagnostics(diag_scores, clusters)
    else:
        diagnostic_report = DiagnosticReport(tasks=[])

    # Build profiles for each subject
    profiles: list[SubjectProfile] = []
    for sid in subject_ids:
        key = sid.display_name
        scores = all_scores.get(key, {})
        pillar_data = all_pillar_data.get(key, {})

        total_cost = 0.0
        total_latency = 0.0
        total_tool_calls = 0
        n_samples = 1

        # Re-extract cost/latency from pillar_data (already computed above)
        # These are per-subject summaries
        if not profiles:
            # Use diagnostic report to identify non-discriminative tasks
            non_discriminative: set[str] = set(diagnostic_report.non_discriminative_tasks)
        else:
            non_discriminative = set(diagnostic_report.non_discriminative_tasks)

        profile = build_profile(
            subject_id=sid,
            scores=scores,
            clusters=clusters,
            non_discriminative_tasks=non_discriminative,
            pillar_data=pillar_data if pillar_data else None,
            cost_per_sample=None,
            latency_avg=None,
            tool_calls_avg=None,
            ci_level=config.ci_level,
        )

        # Run safety gates
        gate_results = run_gates_for_profile(profile, config)
        profile.gate_results = gate_results
        profiles.append(profile)

    return profiles, diagnostic_report


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
    """Extract correctness from sample scores dict.

    Tries in order: hybrid_scorer > llm_judge > verify_sh > exact > includes.
    Returns None if no valid score found.
    """
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
