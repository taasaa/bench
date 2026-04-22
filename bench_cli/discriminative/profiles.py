"""Profile building — multi-dimensional subject profiles with cluster scores."""
from __future__ import annotations

from typing import TYPE_CHECKING

from bench_cli.discriminative.ci import agresti_coull_ci, cluster_ci, c_is_significant
from bench_cli.discriminative.types import (
    ClusterScore,
    CompareResult,
    ClusterDelta,
    StrengthWeakness,
    SubjectID,
    SubjectProfile,
)

if TYPE_CHECKING:
    from bench_cli.discriminative.types import PipelineConfig


N_SAMPLES = 5  # samples per task in eval


def build_profile(
    subject_id: SubjectID,
    scores: dict[str, float],
    clusters: dict[str, list[str]],
    non_discriminative_tasks: set[str],
    pillar_data: dict[str, dict[str, float]] | None = None,
    # pillar_data: {task_id: {token_ratio, time_ratio, cost_ratio}}
    cost_per_sample: float | None = None,
    latency_avg: float | None = None,
    tool_calls_avg: float | None = None,
    ci_level: float = 0.90,
) -> SubjectProfile:
    """Build a SubjectProfile from per-task correctness scores.

    Args:
        subject_id: The subject being profiled
        scores: {task_id: correctness_score} for this subject
        clusters: {cluster_name: [task_ids]} from clusters.yaml
        non_discriminative_tasks: tasks with σ=0 to exclude from cluster scores
        pillar_data: {task_id: {token_ratio, time_ratio, cost_ratio}}
        cost_per_sample: USD per sample (None for free models)
        latency_avg: average seconds per sample
        tool_calls_avg: average tool calls per sample (agents only)
        ci_level: confidence level for CIs (default 0.90)
    """
    import statistics

    cluster_scores: list[ClusterScore] = []

    for cluster_name, task_ids in clusters.items():
        # Filter to discriminative tasks only
        discriminative_ids = [t for t in task_ids if t not in non_discriminative_tasks]
        cluster_scores_list = [scores.get(t) for t in discriminative_ids if t in scores]
        cluster_token_ratios: list[float] = []
        cluster_time_ratios: list[float] = []
        cluster_cost_ratios: list[float] = []

        if pillar_data:
            for task_id in discriminative_ids:
                pd = pillar_data.get(task_id, {})
                if "token_ratio" in pd:
                    cluster_token_ratios.append(pd["token_ratio"])
                if "time_ratio" in pd:
                    cluster_time_ratios.append(pd["time_ratio"])
                if "cost_ratio" in pd:
                    cluster_cost_ratios.append(pd["cost_ratio"])

        if not cluster_scores_list:
            # No scores for this cluster
            cluster_scores.append(ClusterScore(
                name=cluster_name,
                correct=0.0,
                token_ratio=0.0,
                time_ratio=0.0,
                cost_ratio=0.0,
                ci_low=0.0,
                ci_high=0.0,
                task_count=0,
            ))
        else:
            correct_mean = statistics.mean(cluster_scores_list)

            # Agresti-Coull CI: aggregate all per-task binary outcomes.
            # Each task contributes n_samples binary outcomes.
            # Total successes = sum(task_mean × n_samples) across tasks.
            # Total trials = len(tasks) × n_samples.
            n_tasks = len(cluster_scores_list)
            total_successes = sum(s * N_SAMPLES for s in cluster_scores_list)
            total_trials = n_tasks * N_SAMPLES
            ci_low, ci_high = agresti_coull_ci(int(total_successes), total_trials, ci_level)

            # Aggregate pillar ratios
            token_ratio = statistics.mean(cluster_token_ratios) if cluster_token_ratios else 0.0
            time_ratio = statistics.mean(cluster_time_ratios) if cluster_time_ratios else 0.0
            cost_ratio = statistics.mean(cluster_cost_ratios) if cluster_cost_ratios else 0.0

            cluster_scores.append(ClusterScore(
                name=cluster_name,
                correct=correct_mean,
                token_ratio=token_ratio,
                time_ratio=time_ratio,
                cost_ratio=cost_ratio,
                ci_low=ci_low,
                ci_high=ci_high,
                task_count=n_tasks,
            ))

    # Strengths and weaknesses
    strengths = compute_strengths(scores, n=2)
    weaknesses = compute_weaknesses(scores, n=2)

    # Verdict
    verdict = _generate_verdict(cluster_scores, cost_per_sample)

    return SubjectProfile(
        subject_id=subject_id,
        cluster_scores=cluster_scores,
        strengths=strengths,
        weaknesses=weaknesses,
        non_discriminative_tasks=sorted(non_discriminative_tasks),
        cost_per_sample=cost_per_sample,
        latency_avg=latency_avg,
        tool_calls_avg=tool_calls_avg,
        verdict=verdict,
    )


def compute_strengths(scores: dict[str, float], n: int = 2) -> list[StrengthWeakness]:
    """Return top-n highest-scoring non-zero tasks."""
    non_zero = [(t, s) for t, s in scores.items() if s > 0]
    non_zero.sort(key=lambda x: x[1], reverse=True)
    return [StrengthWeakness(task_id=t, score=s, is_strength=True) for t, s in non_zero[:n]]


def compute_weaknesses(scores: dict[str, float], n: int = 2) -> list[StrengthWeakness]:
    """Return bottom-n lowest-scoring tasks."""
    items = [(t, s) for t, s in scores.items()]
    items.sort(key=lambda x: x[1])
    return [StrengthWeakness(task_id=t, score=s, is_strength=False) for t, s in items[:n]]


def _generate_verdict(cluster_scores: list[ClusterScore], cost_per_sample: float | None) -> str:
    """Generate a plain-language verdict from cluster scores."""
    if not cluster_scores:
        return "No cluster data available."

    sorted_scores = sorted(cluster_scores, key=lambda c: c.correct, reverse=True)
    top = sorted_scores[0]
    bottom = sorted_scores[-1]

    lines = []
    lines.append(f"Strongest cluster: {top.name} ({top.correct:.0%}).")
    lines.append(f"Weakest cluster: {bottom.name} ({bottom.correct:.0%}).")

    if cost_per_sample is not None:
        if cost_per_sample == 0.0:
            lines.append("Free — cost-optimal for any use case.")
        elif cost_per_sample < 0.01:
            lines.append(f"Very low cost (${cost_per_sample:.4f}/sample).")
        else:
            lines.append(f"Cost: ${cost_per_sample:.4f}/sample.")

    return " ".join(lines)


def format_profile(profile: SubjectProfile) -> str:
    """Format SubjectProfile as the output specified in the PRD."""
    lines: list[str] = []

    # Header
    st = profile.subject_id.subject_type.value.upper()
    lines.append(f"PROFILE: {profile.subject_id.display_name} [{st}]")
    lines.append("=" * 56)
    lines.append("")

    # Cluster scores
    lines.append("CLUSTER SCORES (90% CI):")
    for cs in profile.cluster_scores:
        label = _score_label(cs.correct)
        bar = _score_bar(cs.correct)
        ci_str = f"[{cs.ci_low:.2f}-{cs.ci_high:.2f}]"
        lines.append(f"  {cs.name:<15} {cs.correct:.2f} {ci_str}  {bar}  {label}")

    lines.append("")

    # Strengths
    if profile.strengths:
        lines.append("STRENGTHS:")
        for sw in profile.strengths:
            lines.append(f"  ✓ {sw.task_id} ({sw.score:.2f})")
        lines.append("")

    # Weaknesses
    if profile.weaknesses:
        lines.append("WEAKNESSES:")
        for sw in profile.weaknesses:
            lines.append(f"  ✗ {sw.task_id} ({sw.score:.2f})")
        lines.append("")

    # Non-discriminative tasks
    if profile.non_discriminative_tasks:
        lines.append("NON-DISCRIMINATIVE TASKS (excluded from cluster scores):")
        lines.append(f"  {', '.join(profile.non_discriminative_tasks)}")
        lines.append("")

    # Cost
    if profile.cost_per_sample is not None:
        if profile.cost_per_sample == 0.0:
            lines.append("COST: $0.00/sample (FREE)")
        else:
            lines.append(f"COST: ${profile.cost_per_sample:.4f}/sample")
    if profile.latency_avg is not None:
        lines.append(f"LATENCY: {profile.latency_avg:.1f}s avg")
    if profile.tool_calls_avg is not None:
        lines.append(f"TOOL CALLS: {profile.tool_calls_avg:.1f} avg/sample")
    lines.append("")

    # Verdict
    lines.append(f"VERDICT: {profile.verdict}")

    return "\n".join(lines)


def _score_label(score: float) -> str:
    if score >= 0.90:
        return "EXCELLENT"
    if score >= 0.80:
        return "GOOD"
    if score >= 0.70:
        return "FAIR"
    if score >= 0.60:
        return "POOR"
    return "FAILING"


def _score_bar(score: float) -> str:
    filled = int(score * 10)
    return "█" * filled + "░" * (10 - filled)


def compare_subjects(
    profile_a: SubjectProfile,
    profile_b: SubjectProfile,
) -> CompareResult:
    """Compare two subject profiles and compute per-cluster deltas."""
    deltas: list[ClusterDelta] = []

    # Build lookup maps
    scores_a = {cs.name: cs for cs in profile_a.cluster_scores}
    scores_b = {cs.name: cs for cs in profile_b.cluster_scores}

    all_clusters = set(scores_a.keys()) | set(scores_b.keys())

    for cluster_name in sorted(all_clusters):
        ca = scores_a.get(cluster_name)
        cb = scores_b.get(cluster_name)

        if ca is None or cb is None:
            continue

        delta_correct = cb.correct - ca.correct
        delta_tr = cb.token_ratio - ca.token_ratio if ca.token_ratio and cb.token_ratio else 0.0
        delta_ttr = cb.time_ratio - ca.time_ratio if ca.time_ratio and cb.time_ratio else 0.0
        delta_cr = cb.cost_ratio - ca.cost_ratio if ca.cost_ratio and cb.cost_ratio else 0.0

        # Significance: CI non-overlap
        significant = c_is_significant((ca.ci_low, ca.ci_high), (cb.ci_low, cb.ci_high))

        deltas.append(ClusterDelta(
            cluster_name=cluster_name,
            delta=delta_correct,
            significant=significant,
            delta_token_ratio=delta_tr,
            delta_time_ratio=delta_ttr,
            delta_cost_ratio=delta_cr,
        ))

    cost_delta = None
    if profile_a.cost_per_sample is not None and profile_b.cost_per_sample is not None:
        cost_delta = profile_b.cost_per_sample - profile_a.cost_per_sample

    latency_delta = None
    if profile_a.latency_avg is not None and profile_b.latency_avg is not None:
        latency_delta = profile_b.latency_avg - profile_a.latency_avg

    return CompareResult(
        subject_a=profile_a.subject_id,
        subject_b=profile_b.subject_id,
        deltas=deltas,
        cost_delta=cost_delta,
        latency_delta=latency_delta,
    )
