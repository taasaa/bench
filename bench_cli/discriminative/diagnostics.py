"""Diagnostics — per-task difficulty and discrimination analysis.

This module analyzes the eval data to classify tasks as:
- CEILING: difficulty > 0.90 (too easy — all subjects pass)
- FLOOR: difficulty < 0.10 (too hard — all subjects fail)
- NON_DISCRIMINATIVE: discrimination == 0.0 (all subjects score same)
- NORMAL: neither ceiling nor floor, discriminative

Only NORMAL tasks contribute signal to cluster scores.
"""
from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

from bench_cli.discriminative.types import DiagnosticReport, TaskDiagnostics

if TYPE_CHECKING:
    from bench_cli.discriminative.types import SubjectID


# Difficulty thresholds
DIFFICULTY_CEILING = 0.90
DIFFICULTY_FLOOR = 0.10


def run_diagnostics(
    all_scores: dict["SubjectID", dict[str, float]],
    clusters: dict[str, list[str]],
) -> DiagnosticReport:
    """Compute diagnostics for all tasks across all subjects.

    Args:
        all_scores: {subject_id: {task_id: correctness_score}}
        clusters: {cluster_name: [task_ids]}

    Returns:
        DiagnosticReport with per-task diagnostics and summary lists
    """
    # Collect scores per task
    task_scores: dict[str, list[float]] = {}
    for subject_scores in all_scores.values():
        for task_id, score in subject_scores.items():
            if task_id not in task_scores:
                task_scores[task_id] = []
            task_scores[task_id].append(score)

    tasks: list[TaskDiagnostics] = []
    non_discriminative_tasks: list[str] = []
    ceiling_tasks: list[str] = []
    floor_tasks: list[str] = []

    for task_id, scores in task_scores.items():
        if not scores:
            continue

        difficulty = sum(scores) / len(scores)
        discrimination = statistics.stdev(scores) if len(scores) >= 2 else 0.0

        is_ceiling = difficulty > DIFFICULTY_CEILING
        is_floor = difficulty < DIFFICULTY_FLOOR
        is_non_discriminative = discrimination == 0.0

        tasks.append(TaskDiagnostics(
            task_id=task_id,
            difficulty=difficulty,
            discrimination=discrimination,
            is_ceiling=is_ceiling,
            is_floor=is_floor,
            is_non_discriminative=is_non_discriminative,
        ))

        if is_non_discriminative:
            non_discriminative_tasks.append(task_id)
        if is_ceiling:
            ceiling_tasks.append(task_id)
        if is_floor:
            floor_tasks.append(task_id)

    return DiagnosticReport(
        tasks=tasks,
        non_discriminative_tasks=sorted(non_discriminative_tasks),
        ceiling_tasks=sorted(ceiling_tasks),
        floor_tasks=sorted(floor_tasks),
    )


def format_diagnostic_summary(report: DiagnosticReport) -> str:
    """Format diagnostic report as readable text."""
    lines = ["DIAGNOSTIC SUMMARY", "=" * 40]
    lines.append(f"Total tasks: {len(report.tasks)}")
    lines.append(f"Non-discriminative (σ=0): {len(report.non_discriminative_tasks)}")
    lines.append(f"Ceiling (>0.90): {len(report.ceiling_tasks)}")
    lines.append(f"Floor (<0.10): {len(report.floor_tasks)}")
    lines.append("")

    if report.non_discriminative_tasks:
        lines.append(f"Non-discriminative: {', '.join(report.non_discriminative_tasks)}")
    if report.ceiling_tasks:
        lines.append(f"Ceiling: {', '.join(report.ceiling_tasks)}")
    if report.floor_tasks:
        lines.append(f"Floor: {', '.join(report.floor_tasks)}")

    return "\n".join(lines)
