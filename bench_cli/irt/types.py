"""Dataclasses for IRT results — no PyMC dependency."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OutcomeMatrix:
    """Binary outcome matrix for IRT fitting.

    Rows = models (respondents), columns = tasks (items).
    Values = per-(model, task) pass@1 rate (0.0–1.0).
    """

    matrix: list[list[float]]  # shape (n_models, n_tasks)
    models: list[str]          # row labels
    tasks: list[str]           # column labels
    pillars: dict[str, str] = field(default_factory=dict)  # task -> pillar


@dataclass
class IRTFit:
    """Posterior estimates from a fitted 2PL IRT model."""

    theta: list[float]                    # posterior mean ability per model
    theta_ci: list[tuple[float, float]]   # 95% credible interval per model
    a: list[float]                        # discrimination per task
    a_ci: list[tuple[float, float]]       # 95% credible interval per task for a
    b: list[float]                        # difficulty per task
    b_ci: list[tuple[float, float]]       # 95% credible interval per task for b
    models: list[str]
    tasks: list[str]
    pillar: str | None                    # None = general (all tasks)
    converged: bool                       # False if Rhat > 1.1 for any param
    n_divergences: int


@dataclass
class ItemAnalysis:
    """Per-task IRT item parameters + discrimination classification."""

    task: str
    pillar: str
    a: float                          # discrimination (posterior mean)
    a_ci: tuple[float, float]         # 95% CI on a
    b: float                          # difficulty (posterior mean)
    b_ci: tuple[float, float]         # 95% CI on b
    band: str                         # "high", "medium", "low", "cull"
