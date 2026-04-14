"""Bench scorer package: pillars-first architecture with pluggable scorers.

Exports:
  - Pillar protocol and constants
  - Individual pillar scorers (token, time, execution_safety, constraint,
    output_safety, composite_safety, verify_sh)
  - Baseline store
  - Legacy scorers (composite, efficiency, safety) — kept for backward compat
"""

from scorers.baseline_store import Baseline, BaselineStore
from scorers.composite import composite
from scorers.composite_safety import composite_safety_scorer
from scorers.constraint import ConstraintRule, constraint_adherence_scorer
from scorers.efficiency import efficiency
from scorers.execution_safety import execution_safety_scorer
from scorers.fixtures import fixtures_dir, load_fixture, load_fixture_bytes
from scorers.llm_judge import llm_judge
from scorers.output_safety import pattern_output_safety_scorer
from scorers.protocol import (
    DEFAULT_NOISE_FLOOR,
    LOOP_MESSAGE_THRESHOLD,
    MIN_RATIO_FLOOR,
    SYSTEM_DEFAULT_BUDGETS,
    PillarScorer,
    RatioSource,
    TaskBudget,
)
from scorers.safety import safety
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer
from scorers.verify_sh import verify_sh

__all__ = [
    "DEFAULT_NOISE_FLOOR",
    "LOOP_MESSAGE_THRESHOLD",
    "MIN_RATIO_FLOOR",
    "SYSTEM_DEFAULT_BUDGETS",
    "Baseline",
    "BaselineStore",
    "ConstraintRule",
    "PillarScorer",
    "RatioSource",
    "TaskBudget",
    "composite",
    "composite_safety_scorer",
    "constraint_adherence_scorer",
    "efficiency",
    "execution_safety_scorer",
    "fixtures_dir",
    "llm_judge",
    "load_fixture",
    "load_fixture_bytes",
    "pattern_output_safety_scorer",
    "safety",
    "time_ratio_scorer",
    "token_ratio_scorer",
    "verify_sh",
]
