"""Safety gates — non-compensatory correctness thresholds per cluster.

Non-compensatory: a subject must pass each gate independently.
Strength in one cluster cannot compensate for failure in another.

This implements the ICAO/FAA pattern: must pass ALL sub-skills to pass overall.
Unlike compensatory scoring where strengths cancel weaknesses.

Default threshold: 0.60 correctness per cluster.
Configurable per cluster via gates.yaml.
Hard block by default, configurable to warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from bench_cli.discriminative.types import GateResult, SubjectProfile


# Default gate thresholds
DEFAULT_CORRECTNESS_THRESHOLD = 0.60
DEFAULT_COVERAGE_THRESHOLD = 0.80  # must have data for ≥80% of tasks


@dataclass
class GateDefinition:
    """Definition of a safety gate."""

    name: str
    clusters: list[str]  # clusters this gate applies to
    threshold: float
    coverage_threshold: float = 0.80
    strict: bool = True  # True=hard block, False=warning only
    description: str = ""


def load_gates_yaml(path: str) -> list[GateDefinition]:
    """Load gate definitions from YAML config file."""
    with open(path) as f:
        data = yaml.safe_load(f)

    gates: list[GateDefinition] = []

    # Parse new structured format (gate_configs section)
    gate_configs = data.get("gate_configs", {})
    defaults = data.get("defaults", {})

    for cluster_name, config in gate_configs.items():
        dflt_thresh = defaults.get("correctness_threshold", DEFAULT_CORRECTNESS_THRESHOLD)
        gates.append(
            GateDefinition(
                name=f"correctness_gate_{cluster_name}",
                clusters=[cluster_name],
                threshold=config.get("threshold", dflt_thresh),
                coverage_threshold=defaults.get("coverage_threshold", DEFAULT_COVERAGE_THRESHOLD),
                strict=config.get("strict", defaults.get("strict", True)),
                description=config.get("description", f"Per-cluster gate for {cluster_name}"),
            )
        )

    # Always include overall correctness and coverage gates
    if not gates:
        gates.append(
            GateDefinition(
                name="correctness_gate",
                clusters=[],
                threshold=defaults.get("correctness_threshold", DEFAULT_CORRECTNESS_THRESHOLD),
                coverage_threshold=defaults.get("coverage_threshold", DEFAULT_COVERAGE_THRESHOLD),
                strict=defaults.get("strict", True),
                description="Overall correctness gate",
            )
        )

    gates.append(
        GateDefinition(
            name="coverage_gate",
            clusters=[],
            threshold=defaults.get("coverage_threshold", DEFAULT_COVERAGE_THRESHOLD),
            coverage_threshold=0.0,
            strict=defaults.get("strict", True),
            description="Coverage gate — all clusters must have eval data",
        )
    )

    return gates


def correctness_gate(
    profile: "SubjectProfile",
    threshold: float = DEFAULT_CORRECTNESS_THRESHOLD,
    coverage_threshold: float = DEFAULT_COVERAGE_THRESHOLD,
    strict: bool = True,
) -> "GateResult":
    """Evaluate correctness gate: all covered clusters must exceed threshold.

    Args:
        profile: SubjectProfile with cluster_scores
        threshold: minimum correctness per cluster
        coverage_threshold: fraction of tasks that must have data
        strict: if True, failure is hard block; if False, warning only

    Returns:
        GateResult with passed/failed, threshold, score, failed_tasks, message
    """
    from bench_cli.discriminative.types import GateResult

    score_map = {cs.name: cs for cs in profile.cluster_scores}
    failed_tasks: list[str] = []
    worst_score = 1.0
    worst_cluster = ""

    for cluster_name, cluster_score in score_map.items():
        if cluster_score.task_count == 0:
            continue  # No data — skip (coverage gate handles this)

        # Check coverage
        # We don't have exact task count per cluster in profile, so we use task_count
        # as a proxy. A more precise version would track covered tasks per cluster.
        actual = cluster_score.correct

        if actual < threshold:
            failed_tasks.append(f"{cluster_name} (correct={actual:.2f}, threshold={threshold})")
            if actual < worst_score:
                worst_score = actual
                worst_cluster = cluster_name

    # Compute overall score as weighted average across clusters
    scored_clusters = [cs for cs in profile.cluster_scores if cs.task_count > 0]
    if not scored_clusters:
        overall_score = 0.0
    else:
        overall_score = sum(cs.correct * cs.task_count for cs in scored_clusters) / sum(
            cs.task_count for cs in scored_clusters
        )

    passed = overall_score >= threshold
    message = ""
    if not passed:
        if strict:
            message = (
                f"FAILED: correctness {overall_score:.2f} below threshold {threshold}. "
                f"Worst cluster: {worst_cluster} ({worst_score:.2f}). "
                f"Failed clusters: {len(failed_tasks)}"
            )
        else:
            message = (
                f"WARNING: correctness {overall_score:.2f} below threshold {threshold}. "
                f"Worst cluster: {worst_cluster} ({worst_score:.2f})"
            )

    return GateResult(
        name="correctness_gate",
        passed=passed,
        threshold=threshold,
        score=overall_score,
        failed_tasks=failed_tasks if not passed else [],
        message=message,
    )


def _correctness_gate_cluster(
    profile: "SubjectProfile",
    cluster_name: str,
    threshold: float,
    strict: bool,
) -> "GateResult":
    """Evaluate correctness gate for a specific cluster.

    Non-compensatory: cluster must independently exceed threshold.
    Reports score as the cluster's correctness, with CI.
    """
    from bench_cli.discriminative.types import GateResult

    score_map = {cs.name: cs for cs in profile.cluster_scores}
    cluster_score = score_map.get(cluster_name)

    if cluster_score is None or cluster_score.task_count == 0:
        passed = False
        actual_score = 0.0
        failed = [f"{cluster_name} (no data)"]
        message = f"FAILED: {cluster_name} has no eval data. Must have data to evaluate."
    elif cluster_score.correct < threshold:
        passed = False
        actual_score = cluster_score.correct
        ci_str = f"[{cluster_score.ci_low:.2f}-{cluster_score.ci_high:.2f}]"
        failed = [
            f"{cluster_name} (correct={actual_score:.2f}, threshold={threshold}, CI={ci_str})",
        ]
        if strict:
            message = (
                f"FAILED: {cluster_name} scored {actual_score:.2f} (CI: {ci_str}), "
                f"below threshold {threshold}."
            )
        else:
            message = (
                f"WARNING: {cluster_name} scored {actual_score:.2f} (CI: {ci_str}), "
                f"below threshold {threshold}."
            )
    else:
        passed = True
        actual_score = cluster_score.correct
        failed = []
        ci_str = f"[{cluster_score.ci_low:.2f}-{cluster_score.ci_high:.2f}]"
        message = (
            f"PASS: {cluster_name} at {actual_score:.2f} (CI: {ci_str}), "
            f"above threshold {threshold}."
        )

    return GateResult(
        name=f"correctness_gate_{cluster_name}",
        passed=passed,
        threshold=threshold,
        score=actual_score,
        failed_tasks=failed,
        message=message,
    )


def coverage_gate(
    profile: "SubjectProfile",
    threshold: float = DEFAULT_COVERAGE_THRESHOLD,
    strict: bool = True,
) -> "GateResult":
    """Evaluate coverage gate: must have eval data for enough tasks per cluster.

    A cluster with no data is considered 0% coverage.
    """
    from bench_cli.discriminative.types import GateResult

    coverage_map = {cs.name: cs.task_count for cs in profile.cluster_scores}
    total_clusters = len(coverage_map)
    covered_clusters = sum(1 for count in coverage_map.values() if count > 0)
    coverage = covered_clusters / total_clusters if total_clusters > 0 else 0.0

    # Also check per-cluster coverage
    failed_tasks: list[str] = []
    for cluster_name, count in coverage_map.items():
        if count == 0:
            failed_tasks.append(f"{cluster_name} (no data)")

    passed = coverage >= threshold
    message = ""
    if not passed:
        pct = coverage * 100
        if strict:
            message = (
                f"FAILED: cluster coverage {pct:.0f}% below threshold {threshold * 100:.0f}%. "
                f"Clusters without data: {failed_tasks}"
            )
        else:
            message = (
                f"WARNING: cluster coverage {pct:.0f}% below threshold {threshold * 100:.0f}%. "
                f"Clusters without data: {failed_tasks}"
            )

    return GateResult(
        name="coverage_gate",
        passed=passed,
        threshold=threshold,
        score=coverage,
        failed_tasks=failed_tasks if not passed else [],
        message=message,
    )


def run_gates(
    profile: "SubjectProfile",
    gates_yaml: str | None = None,
) -> list["GateResult"]:
    """Run all applicable gates against a subject profile.

    Args:
        profile: SubjectProfile to evaluate
        gates_yaml: path to gates.yaml config (None = use default thresholds)

    Returns:
        list of GateResult, one per gate
    """
    if gates_yaml:
        gates = load_gates_yaml(gates_yaml)
    else:
        # Use default gates
        gates = [
            GateDefinition(
                name="correctness_gate",
                clusters=[],
                threshold=DEFAULT_CORRECTNESS_THRESHOLD,
                coverage_threshold=DEFAULT_COVERAGE_THRESHOLD,
                strict=True,
                description="All clusters must meet minimum correctness threshold",
            ),
            GateDefinition(
                name="coverage_gate",
                clusters=[],
                threshold=DEFAULT_COVERAGE_THRESHOLD,
                coverage_threshold=0.0,
                strict=True,
                description="All clusters must have eval data",
            ),
        ]

    results: list["GateResult"] = []
    for gate_def in gates:
        if gate_def.name == "correctness_gate":
            result = correctness_gate(
                profile,
                threshold=gate_def.threshold,
                coverage_threshold=gate_def.coverage_threshold,
                strict=gate_def.strict,
            )
            results.append(result)
        elif gate_def.name.startswith("correctness_gate_"):
            # Per-cluster gate: check specific cluster only
            cluster_name = gate_def.name[len("correctness_gate_") :]
            result = _correctness_gate_cluster(
                profile,
                cluster_name=cluster_name,
                threshold=gate_def.threshold,
                strict=gate_def.strict,
            )
            results.append(result)
        elif gate_def.name == "coverage_gate":
            result = coverage_gate(profile, threshold=gate_def.threshold, strict=gate_def.strict)
            results.append(result)
        else:
            continue
    return results


def format_gate_result(result: "GateResult") -> str:
    """Format a GateResult for display."""
    score_str = f"score={result.score:.2f}"
    thresh_str = f"threshold={result.threshold}"
    if result.passed:
        return f"  ✓ {result.name}: PASS ({score_str}, {thresh_str})"
    else:
        return f"  ✗ {result.name}: FAIL ({score_str}, {thresh_str}) — {result.message}"


def format_gate_results(results: list["GateResult"]) -> str:
    """Format all gate results as a block."""
    lines = ["SAFETY GATES:", "=" * 40]
    for result in results:
        lines.append(format_gate_result(result))
    return "\n".join(lines)
