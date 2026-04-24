"""Comparison matrix — cross-subject side-by-side analysis.

Phase 3: given N profiles, produce a matrix showing per-cluster scores
across all subjects, with deltas and significance markers.
"""

from __future__ import annotations

from bench_cli.discriminative.ci import c_is_significant
from bench_cli.discriminative.phase3_types import (
    CompareMatrix,
    MatrixRow,
    SubjectProfile,
)


def compare_matrix(profiles: list[SubjectProfile]) -> CompareMatrix:
    """Build a comparison matrix from N subject profiles.

    Returns one MatrixRow per cluster, with scores for each subject.
    Deltas are relative to the first subject in the list (reference).

    Args:
        profiles: list of SubjectProfile from same pipeline run

    Returns:
        CompareMatrix with one row per cluster
    """
    if not profiles:
        return CompareMatrix(subjects=[], rows=[])

    subjects = [p.subject_id for p in profiles]
    reference = profiles[0]

    # Collect all cluster names
    all_clusters: set[str] = set()
    for p in profiles:
        for cs in p.cluster_scores:
            all_clusters.add(cs.name)

    rows: list[MatrixRow] = []
    for cluster_name in sorted(all_clusters):
        # Build score maps
        scores_map: dict[str, float] = {}
        ci_lows: dict[str, float] = {}
        ci_highs: dict[str, float] = {}

        for p in profiles:
            scores_map[p.subject_id.display_name] = _get_cluster_score(p, cluster_name)
            ci_lows[p.subject_id.display_name] = _get_cluster_ci(p, cluster_name, "low")
            ci_highs[p.subject_id.display_name] = _get_cluster_ci(p, cluster_name, "high")

        # Compute deltas relative to reference
        ref_score = scores_map.get(reference.subject_id.display_name, 0.0)
        deltas: dict[str, float] = {}
        for name, score in scores_map.items():
            deltas[name] = score - ref_score

        rows.append(
            MatrixRow(
                cluster_name=cluster_name,
                scores=scores_map,
                ci_lows=ci_lows,
                ci_highs=ci_highs,
                deltas=deltas,
            )
        )

    return CompareMatrix(
        subjects=subjects,
        rows=rows,
        reference_subject=subjects[0] if subjects else None,
    )


def format_matrix(matrix: CompareMatrix) -> str:
    """Format CompareMatrix as an ASCII table."""
    if not matrix.rows:
        return "No comparison data available."

    lines: list[str] = []

    # Subject header
    subject_names = [s.display_name for s in matrix.subjects]
    header = f"{'CLUSTER':<16} " + "  ".join(f"{n:<20}" for n in subject_names)
    lines.append(header)
    lines.append("-" * len(header))

    for row in matrix.rows:
        score_strs = []
        for name in subject_names:
            score = row.scores.get(name, 0.0)
            low = row.ci_lows.get(name, 0.0)
            high = row.ci_highs.get(name, 0.0)
            score_strs.append(f"{score:.2f} [{low:.2f}-{high:.2f}]")

        row_line = f"{row.cluster_name:<16} " + "  ".join(f"{s:<20}" for s in score_strs)
        lines.append(row_line)

    lines.append("")

    # Delta summary (reference vs each other subject)
    if len(matrix.subjects) >= 2:
        lines.append("CLUSTER DELTAS (vs reference):")
        ref_name = matrix.subjects[0].display_name
        for row in matrix.rows:
            delta_parts = []
            for name in subject_names:
                if name == ref_name:
                    delta_parts.append("    —     ")
                else:
                    delta = row.deltas.get(name, 0.0)
                    sig = _is_significant_row(row, name)
                    marker = " *" if sig else ""
                    sign = "+" if delta >= 0 else ""
                    delta_parts.append(f"{sign}{delta:.2f}{marker}")
            line = f"{row.cluster_name:<16} " + "  ".join(f"{d:<12}" for d in delta_parts)
            lines.append(line)

    return "\n".join(lines)


def _get_cluster_score(profile: SubjectProfile, cluster_name: str) -> float:
    for cs in profile.cluster_scores:
        if cs.name == cluster_name:
            return cs.correct
    return 0.0


def _get_cluster_ci(profile: SubjectProfile, cluster_name: str, which: str) -> float:
    for cs in profile.cluster_scores:
        if cs.name == cluster_name:
            if which == "low":
                return cs.ci_low
            return cs.ci_high
    return 0.0


def _is_significant_row(row: MatrixRow, subject_name: str) -> bool:
    """Check if delta for subject_name is significant based on CI non-overlap."""
    if subject_name not in row.ci_lows or subject_name not in row.ci_highs:
        return False
    # Reference is first subject in the display names list
    ref_name = next(iter(row.scores.keys()), None)
    if not ref_name or ref_name == subject_name:
        return False
    ref_low = row.ci_lows.get(ref_name, 0.0)
    ref_high = row.ci_highs.get(ref_name, 0.0)
    sub_low = row.ci_lows.get(subject_name, 0.0)
    sub_high = row.ci_highs.get(subject_name, 0.0)
    return c_is_significant((ref_low, ref_high), (sub_low, sub_high))
