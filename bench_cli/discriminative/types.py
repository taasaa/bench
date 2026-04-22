"""Type definitions for the discriminative eval module."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TypedDict

# ---------------------------------------------------------------------------
# Subject types
# ---------------------------------------------------------------------------

class SubjectType(Enum):
    MODEL = "model"
    AGENT = "agent"
    AGENT_HARNESS = "harness"


@dataclass(frozen=True)
class SubjectID:
    model: str
    agent: str | None = None
    agent_mode: str | None = None
    harness_id: str | None = None

    @property
    def subject_type(self) -> SubjectType:
        if self.agent is not None:
            if self.harness_id is not None:
                return SubjectType.AGENT_HARNESS
            return SubjectType.AGENT
        return SubjectType.MODEL

    @property
    def display_name(self) -> str:
        if self.agent is not None:
            base = f"{self.agent}/{self.model}"
            if self.agent_mode:
                base += f"/{self.agent_mode}"
            if self.harness_id:
                base += f"/harness:{self.harness_id}"
            return base
        return self.model


# ---------------------------------------------------------------------------
# Cluster scores
# ---------------------------------------------------------------------------

@dataclass
class ClusterScore:
    name: str
    correct: float  # mean correctness 0..1
    token_ratio: float  # mean token ratio (ref/actual)
    time_ratio: float  # mean time ratio (ref/actual)
    cost_ratio: float  # mean cost ratio (ref/actual)
    ci_low: float
    ci_high: float
    task_count: int
    alpha: float | None = None  # Cronbach's alpha (computed in Phase 2)


@dataclass
class StrengthWeakness:
    task_id: str
    score: float
    is_strength: bool


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

class TaskDiagnostics(TypedDict):
    task_id: str
    difficulty: float  # mean score across subjects (0..1)
    discrimination: float  # std of scores across subjects
    is_ceiling: bool
    is_floor: bool
    is_non_discriminative: bool


@dataclass
class DiagnosticReport:
    tasks: list[TaskDiagnostics]
    non_discriminative_tasks: list[str] = field(default_factory=list)
    ceiling_tasks: list[str] = field(default_factory=list)
    floor_tasks: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Subject profile
# ---------------------------------------------------------------------------

@dataclass
class SubjectProfile:
    subject_id: SubjectID
    cluster_scores: list[ClusterScore]
    strengths: list[StrengthWeakness]
    weaknesses: list[StrengthWeakness]
    non_discriminative_tasks: list[str]
    cost_per_sample: float | None  # USD
    latency_avg: float | None  # seconds
    tool_calls_avg: float | None  # only for agents
    verdict: str
    gate_results: list[GateResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Gate results
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    name: str
    passed: bool
    threshold: float
    score: float  # actual score achieved
    failed_tasks: list[str] = field(default_factory=list)
    message: str = ""


# ---------------------------------------------------------------------------
# Pipeline config
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    clusters_yaml: str = "bench_cli/discriminative/config/clusters.yaml"
    ci_level: float = 0.90
    discrimination_threshold: float = 0.0
    gates_yaml: str = "bench_cli/discriminative/config/gates.yaml"


# ---------------------------------------------------------------------------
# Comparison result
# ---------------------------------------------------------------------------

@dataclass
class ClusterDelta:
    cluster_name: str
    delta: float  # profile_b.correct - profile_a.correct
    significant: bool  # CI non-overlap at configured ci_level
    delta_token_ratio: float = 0.0
    delta_time_ratio: float = 0.0
    delta_cost_ratio: float = 0.0


@dataclass
class CompareResult:
    subject_a: SubjectID
    subject_b: SubjectID
    deltas: list[ClusterDelta]
    cost_delta: float | None = None
    latency_delta: float | None = None
