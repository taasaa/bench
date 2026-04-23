"""Extended type definitions for Phase 3: matrix, correlation, harness change."""
from __future__ import annotations

from dataclasses import dataclass, field

from bench_cli.discriminative.types import (
    DiagnosticReport,
    SubjectID,
    SubjectProfile,
)

# ---------------------------------------------------------------------------
# Phase 3: Multi-subject pipeline
# ---------------------------------------------------------------------------

@dataclass
class MultiSubjectReport:
    profiles: list[SubjectProfile]
    diagnostic_report: DiagnosticReport


# ---------------------------------------------------------------------------
# Phase 3: Comparison matrix
# ---------------------------------------------------------------------------

@dataclass
class MatrixRow:

    """One row of the comparison matrix (one cluster, across all subjects)."""
    cluster_name: str
    scores: dict[str, float]  # {subject_display: correct_score}
    ci_lows: dict[str, float]
    ci_highs: dict[str, float]
    # Per-subject delta relative to reference subject (first in list)
    deltas: dict[str, float]  # {subject_display: delta}


@dataclass
class CompareMatrix:
    subjects: list[SubjectID]
    rows: list[MatrixRow]
    reference_subject: SubjectID | None = None


# ---------------------------------------------------------------------------
# Phase 3: Task correlation
# ---------------------------------------------------------------------------

@dataclass
class TaskCorrelation:
    task_a: str
    task_b: str
    pearson_r: float

    @property
    def interpretation(self) -> str:
        """Interpret Pearson r value."""
        r = abs(self.pearson_r)
        if r >= 0.8:
            return "Strong"
        elif r >= 0.6:
            return "Moderate"
        elif r >= 0.4:
            return "Weak"
        else:
            return "Very weak"


# ---------------------------------------------------------------------------
# Phase 3: Harness change report
# ---------------------------------------------------------------------------

@dataclass
class ClusterPillarDelta:

    """Per-pillar delta for a single cluster in a harness change report."""
    cluster_name: str
    correctness_delta: float
    token_ratio_delta: float
    time_ratio_delta: float
    cost_ratio_delta: float
    correctness_significant: bool
    token_ratio_significant: bool
    time_ratio_significant: bool
    cost_ratio_significant: bool


@dataclass
class HarnessChangeReport:

    """Structured report for a harness change (before/after of same SubjectID)."""
    subject_id: SubjectID
    before_profile: SubjectProfile
    after_profile: SubjectProfile
    cluster_deltas: list[ClusterPillarDelta]
    summary: str
    significant_changes: list[str] = field(default_factory=list)
    non_significant_changes: list[str] = field(default_factory=list)
