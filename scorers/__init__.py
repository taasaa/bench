"""Bench scorer package: pillars-first architecture with pluggable scorers.

Exports:
  - Pillar protocol and constants
  - Individual pillar scorers (verify_sh, llm_judge, hybrid, token/time/price ratio,
    execution_safety, output_safety, constraint, tool_call_efficiency)
  - Baseline store
"""

from scorers.baseline_store import Baseline, BaselineStore
from scorers.constraint import ConstraintRule, constraint_adherence_scorer
from scorers.execution_safety import execution_safety_scorer
from scorers.fixtures import fixtures_dir, load_fixture, load_fixture_bytes
from scorers.hybrid import hybrid_scorer
from scorers.llm_judge import llm_judge
from scorers.output_safety import pattern_output_safety_scorer
from scorers.price_ratio import price_ratio_scorer
from scorers.protocol import (
    DEFAULT_NOISE_FLOOR,
    LOOP_MESSAGE_THRESHOLD,
    MIN_RATIO_FLOOR,
    SYSTEM_DEFAULT_BUDGETS,
    PillarScorer,
    RatioSource,
    TaskBudget,
)
from scorers.time_ratio import time_ratio_scorer
from scorers.token_ratio import token_ratio_scorer
from scorers.tool_call_efficiency import tool_call_efficiency
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
    "constraint_adherence_scorer",
    "execution_safety_scorer",
    "fixtures_dir",
    "hybrid_scorer",
    "llm_judge",
    "load_fixture",
    "load_fixture_bytes",
    "pattern_output_safety_scorer",
    "price_ratio_scorer",
    "time_ratio_scorer",
    "token_ratio_scorer",
    "tool_call_efficiency",
    "verify_sh",
]
