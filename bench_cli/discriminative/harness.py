"""Harness change report — before/after analysis for the same SubjectID.

Phase 3: given two profiles of the same SubjectID taken at different times,
compute per-cluster per-pillar deltas with significance markers.
"""
from __future__ import annotations

from bench_cli.discriminative.ci import c_is_significant
from bench_cli.discriminative.phase3_types import (
    ClusterPillarDelta,
    HarnessChangeReport,
    SubjectProfile,
)


def harness_change_report(
    before: SubjectProfile,
    after: SubjectProfile,
) -> HarnessChangeReport:
    """Build a harness change report from before/after profiles of the same SubjectID.

    Both profiles must be for the same SubjectID. The function computes per-cluster
    per-pillar deltas and flags significant vs non-significant changes.
    """
    if before.subject_id != after.subject_id:
        raise ValueError(
            f"SubjectID mismatch: before={before.subject_id}, after={after.subject_id}"
        )

    # Build lookup maps
    scores_before = {cs.name: cs for cs in before.cluster_scores}
    scores_after = {cs.name: cs for cs in after.cluster_scores}

    cluster_deltas: list[ClusterPillarDelta] = []
    significant_changes: list[str] = []
    non_significant_changes: list[str] = []

    all_clusters = set(scores_before.keys()) | set(scores_after.keys())

    for cluster_name in sorted(all_clusters):
        cs_b = scores_before.get(cluster_name)
        cs_a = scores_after.get(cluster_name)

        if cs_b is None or cs_a is None:
            continue

        correctness_delta = cs_a.correct - cs_b.correct
        token_ratio_delta = cs_a.token_ratio - cs_b.token_ratio
        time_ratio_delta = cs_a.time_ratio - cs_b.time_ratio
        cost_ratio_delta = cs_a.cost_ratio - cs_b.cost_ratio

        correctness_sig = c_is_significant(
            (cs_b.ci_low, cs_b.ci_high), (cs_a.ci_low, cs_a.ci_high)
        )
        token_ratio_sig = False  # No CI on ratio metrics currently
        time_ratio_sig = False
        cost_ratio_sig = False

        cluster_deltas.append(ClusterPillarDelta(
            cluster_name=cluster_name,
            correctness_delta=correctness_delta,
            token_ratio_delta=token_ratio_delta,
            time_ratio_delta=time_ratio_delta,
            cost_ratio_delta=cost_ratio_delta,
            correctness_significant=correctness_sig,
            token_ratio_significant=token_ratio_sig,
            time_ratio_significant=time_ratio_sig,
            cost_ratio_significant=cost_ratio_sig,
        ))

        # Categorize correctness changes
        if abs(correctness_delta) > 0.01:
            marker = " (*)" if correctness_sig else " (n.s.)"
            sign = "+" if correctness_delta >= 0 else ""
            msg = f"{cluster_name}: {sign}{correctness_delta:.2f}{marker}"
            if correctness_sig:
                significant_changes.append(msg)
            else:
                non_significant_changes.append(msg)

    # Generate summary
    summary = _summarize_report(before, after, cluster_deltas, significant_changes)

    return HarnessChangeReport(
        subject_id=before.subject_id,
        before_profile=before,
        after_profile=after,
        cluster_deltas=cluster_deltas,
        summary=summary,
        significant_changes=significant_changes,
        non_significant_changes=non_significant_changes,
    )


def _summarize_report(
    before: SubjectProfile,
    after: SubjectProfile,
    cluster_deltas: list[ClusterPillarDelta],
    significant_changes: list[str],
) -> str:
    """Generate a plain-language summary."""
    if not cluster_deltas:
        return "No cluster data available for comparison."

    correctness_deltas = [d.correctness_delta for d in cluster_deltas]
    avg_delta = sum(correctness_deltas) / len(correctness_deltas) if correctness_deltas else 0.0

    sig_count = len(significant_changes)
    improving = sum(1 for d in correctness_deltas if d > 0)
    regressing = sum(1 for d in correctness_deltas if d < 0)

    lines = []
    lines.append(f"Mean correctness delta: {'+' if avg_delta >= 0 else ''}{avg_delta:.2f}.")
    lines.append(f"{improving} clusters improving, {regressing} regressing.")
    if sig_count > 0:
        lines.append(f"{sig_count} significant change(s) detected.")
    else:
        lines.append("No significant changes detected.")

    return " ".join(lines)


def format_harness_report(report: HarnessChangeReport) -> str:
    """Format HarnessChangeReport as a structured text block."""
    lines: list[str] = []

    lines.append("HARNESS CHANGE REPORT")
    lines.append(f"Subject: {report.subject_id.display_name}")
    lines.append("=" * 56)
    lines.append("")

    # Summary
    lines.append(f"SUMMARY: {report.summary}")
    lines.append("")

    # Cluster × Pillar grid
    lines.append("CLUSTER × PILLAR DELTAS:")
    header = f"{'Cluster':<16} {'CORR':>8} {'TOK_R':>8} {'TIME_R':>8} {'COST_R':>8}"
    lines.append(header)
    lines.append("-" * len(header))

    for delta in report.cluster_deltas:
        corr_str = _delta_str(delta.correctness_delta, delta.correctness_significant)
        tr_str = _delta_str(delta.token_ratio_delta, delta.token_ratio_significant)
        tm_str = _delta_str(delta.time_ratio_delta, delta.time_ratio_significant)
        cr_str = _delta_str(delta.cost_ratio_delta, delta.cost_ratio_significant)

        lines.append(
            f"{delta.cluster_name:<16} {corr_str:>8} {tr_str:>8} "
            f"{tm_str:>8} {cr_str:>8}"
        )

    lines.append("")
    lines.append("Significance: (*) = significant at 90% CI (no overlap), (n.s.) = not significant")
    lines.append("")

    # Detailed change list
    if report.significant_changes:
        lines.append("SIGNIFICANT CHANGES:")
        for ch in report.significant_changes:
            lines.append(f"  ✓ {ch}")
        lines.append("")

    if report.non_significant_changes:
        lines.append("NON-SIGNIFICANT CHANGES:")
        for ch in report.non_significant_changes:
            lines.append(f"  → {ch}")
        lines.append("")

    # Cost and latency deltas
    before_cost = report.before_profile.cost_per_sample
    after_cost = report.after_profile.cost_per_sample
    if before_cost is not None and after_cost is not None:
        cost_delta = after_cost - before_cost
        sign = "+" if cost_delta >= 0 else ""
        lines.append(f"COST DELTA: {sign}${abs(cost_delta):.4f}/sample")

    before_lat = report.before_profile.latency_avg
    after_lat = report.after_profile.latency_avg
    if before_lat is not None and after_lat is not None:
        lat_delta = after_lat - before_lat
        sign = "+" if lat_delta >= 0 else ""
        lines.append(f"LATENCY DELTA: {sign}{abs(lat_delta):.1f}s")

    return "\n".join(lines)


def _delta_str(delta: float, significant: bool) -> str:
    """Format a delta with significance marker."""
    sign = "+" if delta >= 0 else ""
    marker = " (*)" if significant else " (n.s.)"
    return f"{sign}{delta:.2f}{marker}"
